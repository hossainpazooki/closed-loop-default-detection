"""Pluggable correction levers for the closed loop.

Each correction lever the loop can apply is a :class:`Corrector` subclass:
"adding a lever is adding a class". A corrector takes a cohort plus a
:class:`CorrectorContext` (the per-round scalars + a closure that mints the
disjoint train cohort) and returns a :class:`CorrectionOutcome` (its
:class:`LeverMetrics` plus a small ``info`` dict of lever-specific extras).

The four shipped correctors are verbatim extractions of the lever bodies that
used to live as ``_measure_*`` methods on ``SelectiveLabelsLoop`` — identical
numpy calls, RNG seeds, sklearn calls and ordering — so the loop's numeric
output is unchanged.

This module imports only ``config``, ``emp``, ``eval_default``, ``model_pd`` and
numpy; it must NOT import ``loop`` (loop re-exports ``LeverMetrics`` from here,
so the reverse dependency would be circular).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass, field

import numpy as np

from . import config, emp, eval_default, model_pd


@dataclass
class LeverMetrics:
    """Declined-subpopulation focus + the all-population calibration for one lever.

    EMP fields (v2 reporting axis) mirror the existing declined_*/all_ece
    pattern and are ``None`` where inapplicable (see ``SubgroupMetrics``).
    """

    declined_ece: float
    declined_auc: float
    declined_brier: float
    declined_mean_pd: float
    declined_base_rate: float
    declined_f1: float
    all_ece: float
    declined_empc: float | None = None
    declined_empc_fraction: float | None = None
    declined_emp_h: float | None = None
    declined_emp_h_fraction: float | None = None
    declined_f1_emp_cutoff: float | None = None
    all_empc: float | None = None
    all_emp_h: float | None = None

    @classmethod
    def from_scored(cls, scored: dict) -> "LeverMetrics":
        d = scored["declined"]
        a = scored["all"]
        return cls(
            declined_ece=d.ece,
            declined_auc=d.auc,
            declined_brier=d.brier,
            declined_mean_pd=d.mean_pd,
            declined_base_rate=d.base_rate,
            declined_f1=d.f1,
            all_ece=a.ece,
            declined_empc=d.empc,
            declined_empc_fraction=d.empc_fraction,
            declined_emp_h=d.emp_h,
            declined_emp_h_fraction=d.emp_h_fraction,
            declined_f1_emp_cutoff=d.f1_emp_cutoff,
            all_empc=a.empc,
            all_emp_h=a.emp_h,
        )


@dataclass(frozen=True)
class CorrectorContext:
    """Per-round scalars a corrector may need, plus the train-cohort closure.

    ``make_train_cohort`` returns ``(train_cohort, train_seed)`` — the loop
    supplies a closure over ``self._generate_train(severity, iteration)`` so the
    no-leakage disjoint-train discipline stays inside the loop.
    """

    seed: int
    policy_threshold: float
    severity: float
    iteration: int
    exploration_rate: float
    make_train_cohort: Callable[[], tuple[dict, int]]


@dataclass
class CorrectionOutcome:
    """A corrector's metrics plus its lever-specific extras.

    ``info`` is ``{}`` (naive/reweight), ``{"train_seed": int}`` (retrain), or
    ``{"n_explored": int, "explored_defaults": int, "exploration_cost": float}``
    (explore).
    """

    metrics: LeverMetrics
    info: dict = field(default_factory=dict)


class Corrector(ABC):
    """A single pluggable correction lever.

    ``name`` keys the lever in ``RoundResult.corrections``; ``control_priority``
    decides which present corrector drives loop control (highest wins; ties go to
    the first in the loop's corrector list).
    """

    name: str = ""
    control_priority: int = 0

    @abstractmethod
    def apply(self, cohort: dict, ctx: CorrectorContext) -> CorrectionOutcome:
        ...


class NaiveCorrector(Corrector):
    """The baseline detector: PD model fitted on approved rows only."""

    name = "naive"
    control_priority = 0

    def apply(self, cohort: dict, ctx: CorrectorContext) -> CorrectionOutcome:
        model = eval_default.fit_observed_model(cohort, random_state=ctx.seed)
        metrics = LeverMetrics.from_scored(
            eval_default.score_pd_detection(model, cohort, ctx.policy_threshold)
        )
        return CorrectionOutcome(metrics=metrics)


class IPWReweightCorrector(Corrector):
    """Inverse-propensity reweighting of the approved training rows."""

    name = "reweight"
    control_priority = 2

    def apply(self, cohort: dict, ctx: CorrectorContext) -> CorrectionOutcome:
        X = cohort["features"].to_numpy(dtype=float)
        approved = cohort["approved"]
        weights = model_pd.selection_adjusted_weights(X, approved, random_state=ctx.seed)
        model = eval_default.fit_observed_model(
            cohort, sample_weight=weights[approved], random_state=ctx.seed
        )
        metrics = LeverMetrics.from_scored(
            eval_default.score_pd_detection(model, cohort, ctx.policy_threshold)
        )
        return CorrectionOutcome(metrics=metrics)


class DisjointRetrainCorrector(Corrector):
    """Refit on a disjoint train cohort, score on the held-out measure cohort."""

    name = "retrain"
    control_priority = 1

    def apply(self, cohort: dict, ctx: CorrectorContext) -> CorrectionOutcome:
        train_cohort, train_seed = ctx.make_train_cohort()
        model = eval_default.fit_observed_model(train_cohort, random_state=train_seed)
        scored = eval_default.score_pd_detection(model, cohort, ctx.policy_threshold)
        metrics = LeverMetrics.from_scored(scored)
        return CorrectionOutcome(metrics=metrics, info={"train_seed": train_seed})


class ExplorationCorrector(Corrector):
    """Buy labels on a random slice of the declines and train with exact weights."""

    name = "explore"
    control_priority = 3

    def apply(self, cohort: dict, ctx: CorrectorContext) -> CorrectionOutcome:
        rng = np.random.default_rng([ctx.seed, ctx.iteration, config.EXPLORE_STREAM_LOOP])
        approved = cohort["approved"]
        explored = (~approved) & (rng.random(approved.shape[0]) < ctx.exploration_rate)
        funded = approved | explored

        X = cohort["features"].to_numpy(dtype=float)
        y = cohort["true_default"]
        # ctx.exploration_rate == 0.0 guarantees explored is all-False (the
        # comparison above never fires), so the inverse-propensity value here
        # is never actually selected by np.where -- but it is still evaluated
        # eagerly, so guard the division to avoid a ZeroDivisionError on that
        # placeholder. No effect on any exploration_rate > 0 run.
        inv_propensity = (1.0 / ctx.exploration_rate) if ctx.exploration_rate > 0.0 else 1.0
        weights = np.where(explored, inv_propensity, 1.0)
        model = model_pd.train_pd_model(
            X[funded], y[funded], sample_weight=weights[funded], random_state=ctx.seed
        )
        scored = eval_default.score_pd_detection(model, cohort, ctx.policy_threshold, funded=funded)
        metrics = LeverMetrics.from_scored(scored)
        return CorrectionOutcome(
            metrics=metrics,
            info={
                "n_explored": int(explored.sum()),
                "explored_defaults": int(y[explored].sum()),
                "exploration_cost": float(_exploration_cost(cohort, y, explored)),
            },
        )


def _exploration_cost(cohort: dict, y: np.ndarray, explored: np.ndarray) -> float:
    """Net dollar cost of the exploration budget: -(sum of realized profits on
    the EXPLORED rows), priced by ``cldd.emp`` economics (spec sec. 4).

    SCM cohorts (``'days_to_default'`` present) price each explored row by its
    own planted default timing via :func:`cldd.emp.realized_profits` (which
    also carries the decision-5 day-90 mean-body-lambda imputation). Flat
    cohorts plant no timing, so explored rows are priced by the stated
    conservative flat convention: defaulters at lambda = 1 (profit = -A),
    goods at the full-term collections (profit = A*(f + r_term)) — computed
    inline here since ``realized_profits`` has no ``default_day=None`` path.

    Positive = the exploration budget cost money net. 0.0 when nothing was
    explored (in particular, whenever exploration is off).
    """
    if not explored.any():
        return 0.0
    requested_amount = cohort["features"]["requested_amount"].to_numpy(dtype=float)
    if "days_to_default" in cohort:
        profits = emp.realized_profits(y, cohort["days_to_default"], requested_amount)
    else:
        economics = emp.LoanEconomics()
        is_default = y.astype(bool)
        profits = np.where(
            is_default,
            -requested_amount,
            requested_amount * (economics.origination_fee_rate + economics.r_term),
        )
    return -float(profits[explored].sum())
