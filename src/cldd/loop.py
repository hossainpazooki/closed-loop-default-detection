"""CLUE-style closed loop for selective-labels default detection.

Ports ``upstream-label-correction/clue/loop.py`` to the SMB lending domain. Each
round:

1. **Generate** a synthetic cohort at the round's ``selection_severity`` (planted
   default ground truth for every applicant; outcomes hidden for declines). The
   cohort generator is pluggable: ``generator="flat"`` (default) keeps the
   original single-layer ``SyntheticBorrowerGenerator``; ``generator="scm"``
   drives the loop with the fitted layered ``StructuralBorrowerGenerator``.
2. **Measure** the naive detector — PD model trained on the approved rows only —
   against the planted truth, focusing on the **declined** subpopulation real
   data can never score.
3. **Improve** via the configured ``improve_mode`` lever(s):

   * ``"reweight"`` — inverse-propensity (IPW) reweighting of the approved
     training rows to undo prior-approval selection bias.
   * ``"retrain"`` — refit on a **disjoint** train cohort (same severity/geometry,
     a seed offset by ``train_seed_offset``) and score on the held-out measure
     cohort, so the metric is honest and never leaks.
   * ``"both"`` — run both and report each.

   Orthogonal to ``improve_mode``, ``exploration_rate=eps > 0`` adds the
   **exploration lever**: approve a random ``eps``-fraction of the policy's
   declines so their outcomes become observed, then train on all funded rows
   with *exact* labeled-propensity weights (policy approvals are labeled with
   probability 1, explored declines with probability ``eps``). Unlike the IPW
   lever, these weights are known by construction rather than fitted, so the
   unobserved confounder — the mechanism FABLE.md identifies behind both
   frontier failures — cannot leak into them. This is the only lever that buys
   *identification* instead of reweighting what is already identified, at an
   explicit cost the lender can see: the explored loans' realized defaults.

4. **Feed back**: if the corrected detector still clears the target calibration
   on declines, raise the severity to probe a harder selection regime real data
   cannot reach; if it can no longer clear it, stop and report the detector's
   **operating frontier** (the highest severity still passing).

Loop *control* is keyed on the primary lever's declined-subpopulation ECE
(``reweight`` when present, else ``retrain``, else naive); the other levers are
reported alongside. Everything is deterministic for a given seed.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from . import config, eval_default, model_pd
from .diagnostics import PositivityDiagnostics, positivity_diagnostics
from .scm import StructuralBorrowerGenerator
from .synthetic import SyntheticBorrowerGenerator

#: Valid improve levers.
IMPROVE_MODES = ("reweight", "retrain", "both")

#: Valid cohort generators. ``"flat"`` is the original single-layer
#: ``SyntheticBorrowerGenerator`` (the default; existing artifacts and tests are
#: unchanged). ``"scm"`` is the fitted layered ``StructuralBorrowerGenerator``
#: with ``independent_selection_noise=True`` so severity keeps the same meaning
#: in both worlds (sev 0 == selection-at-random no propensity model can explain).
GENERATORS = ("flat", "scm")


def make_generator(
    generator: str,
    *,
    severity: float,
    seed: int,
    n_applicants: int,
    approval_rate: float,
):
    """Fresh single-shot cohort generator (shared by this loop and ``feedback``).

    A fresh instance per cohort is required for determinism — both generator
    classes consume their own ``Generator(PCG64(seed))`` on ``generate_cohort``,
    so reusing an instance would silently shift streams. The SCM path always
    sets ``independent_selection_noise=True`` (see ``GENERATORS`` note).
    """
    if generator not in GENERATORS:
        raise ValueError(f"generator must be one of {GENERATORS}; got {generator!r}")
    if generator == "scm":
        # independent_selection_noise=True: the SCM's default selection blend
        # reuses the exogenous draw behind the OBSERVED prior_underwriter_score
        # column, which would make low-severity selection explainable by the
        # propensity model and invert the IPW lever's narrative. The dedicated
        # frozen draw keeps severity semantics aligned with the flat world.
        # The SCM matrix still exposes the prior-policy columns
        # (prior_underwriter_score / prior_decision / prior_approved_amount) —
        # intentional observed-policy features; with the independent draw they
        # no longer encode this loop's selection mechanism.
        return StructuralBorrowerGenerator(
            n_applicants=n_applicants,
            selection_severity=severity,
            approval_rate=approval_rate,
            seed=seed,
            independent_selection_noise=True,
        )
    return SyntheticBorrowerGenerator(
        n_applicants=n_applicants,
        selection_severity=severity,
        approval_rate=approval_rate,
        seed=seed,
    )


@dataclass
class LeverMetrics:
    """Declined-subpopulation focus + the all-population calibration for one lever."""

    declined_ece: float
    declined_auc: float
    declined_brier: float
    declined_mean_pd: float
    declined_base_rate: float
    declined_f1: float
    all_ece: float

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
        )


@dataclass
class RoundResult:
    """Outcome of one generate -> measure -> improve round."""

    iteration: int
    selection_severity: float
    base_rate: float
    approval_rate: float
    naive: LeverMetrics
    control_metric: float          # the declined ECE that drives loop control
    passed: bool
    improve_mode: str
    reweight: LeverMetrics | None = None
    retrain: LeverMetrics | None = None
    #: Seed of the disjoint train cohort the retrain lever fitted on — makes the
    #: train/measure separation auditable. ``None`` when not retraining.
    retrain_train_seed: int | None = None
    #: Exploration lever (``exploration_rate > 0`` only). Its ``declined_*``
    #: metrics are computed on the *unexplored* declines — still a uniform random
    #: subsample of the policy's declines, and never in the training set.
    explore: LeverMetrics | None = None
    #: Labels bought / defaults incurred by exploration this round. Both are
    #: observable to a real lender (explored loans were funded).
    n_explored: int = 0
    explored_defaults: int = 0
    #: Observable-only positivity diagnostics for the prior policy's selection
    #: (see :mod:`cldd.diagnostics`). Computed every round; needs no labels.
    diagnostics: PositivityDiagnostics | None = None


@dataclass
class LoopResult:
    """Full history of a loop run plus the detector's operating frontier."""

    rounds: list[RoundResult] = field(default_factory=list)
    target_declined_ece: float = 0.0
    #: Highest selection severity at which the corrected detector still cleared the
    #: target calibration, or ``None`` if it never did.
    frontier_severity: float | None = None
    improve_mode: str = "both"
    exploration_rate: float = 0.0

    @property
    def best_round(self) -> RoundResult | None:
        return min(self.rounds, key=lambda r: r.control_metric) if self.rounds else None


class SelectiveLabelsLoop:
    """Drive the closed loop until the PD model reaches its operating frontier."""

    def __init__(
        self,
        *,
        target_declined_ece: float = config.TARGET_DECLINED_ECE,
        start_severity: float = config.START_SEVERITY,
        severity_step: float = config.SEVERITY_STEP,
        max_severity: float = config.MAX_SEVERITY,
        max_rounds: int = config.MAX_ROUNDS,
        n_applicants: int = config.DEFAULT_N_APPLICANTS,
        approval_rate: float = config.DEFAULT_APPROVAL_RATE,
        seed: int = config.RANDOM_SEED,
        improve_mode: str = "both",
        train_seed_offset: int = config.TRAIN_SEED_OFFSET,
        policy_threshold: float = config.POLICY_PD_THRESHOLD,
        generator: str = "flat",
        exploration_rate: float = 0.0,
    ) -> None:
        if improve_mode not in IMPROVE_MODES:
            raise ValueError(f"improve_mode must be one of {IMPROVE_MODES}; got {improve_mode!r}")
        if generator not in GENERATORS:
            raise ValueError(f"generator must be one of {GENERATORS}; got {generator!r}")
        if not 0.0 <= exploration_rate < 1.0:
            raise ValueError(f"exploration_rate must be in [0, 1); got {exploration_rate!r}")
        self.generator = generator
        self.exploration_rate = exploration_rate
        self.target_declined_ece = target_declined_ece
        self.start_severity = start_severity
        self.severity_step = severity_step
        self.max_severity = max_severity
        self.max_rounds = max_rounds
        self.n_applicants = n_applicants
        self.approval_rate = approval_rate
        self.seed = seed
        self.improve_mode = improve_mode
        self.train_seed_offset = train_seed_offset
        self.policy_threshold = policy_threshold

    # ------------------------------------------------------------------ #
    # Cohort generation
    # ------------------------------------------------------------------ #

    def _new_generator(self, severity: float, seed: int):
        """Fresh single-shot generator for one cohort.

        Both ``_generate`` and ``_generate_train`` MUST route through here so the
        measure and retrain cohorts always come from the same generator class
        (mixing them raises an sklearn n_features mismatch: 12 flat vs 28 SCM
        columns). Delegates to :func:`make_generator` (shared with ``feedback``).
        """
        return make_generator(
            self.generator,
            severity=severity,
            seed=seed,
            n_applicants=self.n_applicants,
            approval_rate=self.approval_rate,
        )

    def _generate(self, severity: float, iteration: int) -> dict:
        # a fresh cohort each round, still deterministic
        return self._new_generator(severity, self.seed + iteration).generate_cohort()

    def _generate_train(self, severity: float, iteration: int) -> tuple[dict, int]:
        """DISJOINT train cohort for the retrain lever (no-leakage rule).

        Same severity, geometry, and generator class as the measure cohort but a
        seed offset by ``train_seed_offset`` so neither its applicants nor its RNG
        stream overlap the measure cohort (seed ``self.seed + iteration``).
        """
        train_seed = self.seed + self.train_seed_offset + iteration
        cohort = self._new_generator(severity, train_seed).generate_cohort()
        return cohort, train_seed

    # ------------------------------------------------------------------ #
    # Improve levers
    # ------------------------------------------------------------------ #

    def _measure_naive(self, cohort: dict) -> LeverMetrics:
        model = eval_default.fit_observed_model(cohort, random_state=self.seed)
        return LeverMetrics.from_scored(eval_default.score_pd_detection(model, cohort, self.policy_threshold))

    def _measure_reweight(self, cohort: dict) -> LeverMetrics:
        X = cohort["features"].to_numpy(dtype=float)
        approved = cohort["approved"]
        weights = model_pd.selection_adjusted_weights(X, approved, random_state=self.seed)
        model = eval_default.fit_observed_model(cohort, sample_weight=weights[approved], random_state=self.seed)
        return LeverMetrics.from_scored(eval_default.score_pd_detection(model, cohort, self.policy_threshold))

    def _measure_retrain(self, measure_cohort: dict, severity: float, iteration: int) -> tuple[LeverMetrics, int]:
        train_cohort, train_seed = self._generate_train(severity, iteration)
        model = eval_default.fit_observed_model(train_cohort, random_state=train_seed)
        scored = eval_default.score_pd_detection(model, measure_cohort, self.policy_threshold)
        return LeverMetrics.from_scored(scored), train_seed

    def _measure_explore(self, cohort: dict, iteration: int) -> tuple[LeverMetrics, int, int]:
        """Exploration lever: buy labels on a random slice of the declines.

        A dedicated RNG stream (seeded ``[seed, iteration, EXPLORE_STREAM_LOOP]``)
        draws the explored set, so generator streams and the default path are
        untouched. Training uses *exact* labeled-propensity weights: policy
        approvals are labeled with probability 1 (weight 1), explored declines
        with probability ``exploration_rate`` (weight ``1/rate``) — no fitted
        propensity model, hence nothing the unobserved confounder can distort.
        Scoring funds the explored rows (they really were funded), so the
        ``declined`` slice is the unexplored declines: still a uniform random
        subsample of the policy's declines, and never seen in training.
        """
        rng = np.random.default_rng([self.seed, iteration, config.EXPLORE_STREAM_LOOP])
        approved = cohort["approved"]
        explored = (~approved) & (rng.random(approved.shape[0]) < self.exploration_rate)
        funded = approved | explored

        X = cohort["features"].to_numpy(dtype=float)
        y = cohort["true_default"]
        weights = np.where(explored, 1.0 / self.exploration_rate, 1.0)
        model = model_pd.train_pd_model(
            X[funded], y[funded], sample_weight=weights[funded], random_state=self.seed
        )
        scored = eval_default.score_pd_detection(model, cohort, self.policy_threshold, funded=funded)
        return LeverMetrics.from_scored(scored), int(explored.sum()), int(y[explored].sum())

    # ------------------------------------------------------------------ #
    # Run
    # ------------------------------------------------------------------ #

    def run(self) -> LoopResult:
        """Run the loop and return its history + frontier."""
        result = LoopResult(
            target_declined_ece=self.target_declined_ece,
            improve_mode=self.improve_mode,
            exploration_rate=self.exploration_rate,
        )
        severity = round(self.start_severity, 4)

        for iteration in range(self.max_rounds):
            cohort = self._generate(severity, iteration)
            gt = cohort["ground_truth"]

            naive = self._measure_naive(cohort)
            reweight = retrain = explore = None
            train_seed = None
            n_explored = explored_defaults = 0

            if self.improve_mode in ("reweight", "both"):
                reweight = self._measure_reweight(cohort)
            if self.improve_mode in ("retrain", "both"):
                retrain, train_seed = self._measure_retrain(cohort, severity, iteration)
            if self.exploration_rate > 0.0:
                explore, n_explored, explored_defaults = self._measure_explore(cohort, iteration)

            # Observable-only diagnostics on the prior policy's selection — what a
            # real lender could monitor instead of the planted-truth ECE.
            diag = positivity_diagnostics(
                cohort["features"].to_numpy(dtype=float),
                cohort["approved"],
                random_state=self.seed,
            )

            # Control keys on the primary lever: exploration (the only lever that
            # buys identification) when active, else reweight (the SMB
            # selection-bias correction), else retrain, else the naive baseline.
            if explore is not None:
                primary = explore
            elif reweight is not None:
                primary = reweight
            else:
                primary = retrain if retrain is not None else naive
            control_metric = primary.declined_ece
            passed = control_metric <= self.target_declined_ece

            result.rounds.append(
                RoundResult(
                    iteration=iteration,
                    selection_severity=severity,
                    base_rate=gt["base_rate"],
                    approval_rate=gt["approval_rate"],
                    naive=naive,
                    reweight=reweight,
                    retrain=retrain,
                    retrain_train_seed=train_seed,
                    explore=explore,
                    n_explored=n_explored,
                    explored_defaults=explored_defaults,
                    diagnostics=diag,
                    control_metric=control_metric,
                    passed=passed,
                    improve_mode=self.improve_mode,
                )
            )

            if not passed:
                # Frontier reached: correction can no longer hold calibration here.
                break

            result.frontier_severity = severity
            next_severity = round(severity + self.severity_step, 4)
            if next_severity > self.max_severity:
                break  # probed as hard as configured; detector still holding
            severity = next_severity

        return result
