"""Closing the loop for real: the model's own decisions create its training data.

``SelectiveLabelsLoop`` measures a *static* question — how well levers correct
selection imposed by a fixed prior policy. But the lesson of the hackathon
harness (FABLE.md) is dynamic: once a PD model is deployed, **its own approvals
decide which outcomes the next model generation gets to learn from**. That
feedback has a structural property no severity knob reaches: a deterministic
model policy (fund the lowest-PD fraction) makes selection a *function* of the
features, so the funded and declined pools stop overlapping **by construction**
— positivity is not merely strained, it is gone, and every observational
correction (IPW, retrain) is undefined on the declined side.

``FeedbackLoop`` simulates that regime:

* **Generation 0** funds via the prior underwriter policy at the configured
  ``selection_severity`` (exactly the world the static loop measures) and trains
  the first model on those labels.
* **Generation t >= 1** draws a *fresh* applicant cohort, funds the
  ``approval_rate`` fraction the previous generation's model scores safest,
  observes outcomes for funded rows only, and trains the next model on them.
* With ``exploration_rate=eps > 0``, each generation additionally funds a random
  ``eps``-fraction of its declines (dedicated RNG stream) and trains with exact
  labeled-propensity weights — the identification-buying lever from the static
  loop, now acting as a *stabilizer* of the feedback dynamics.

Per generation we record the planted-truth calibration on the declined (never
labeled) side, the *observable* funded-book performance, and the observable
positivity diagnostics — so the harness can show whether the loop's blind spot
grows while everything a real lender watches still looks healthy.

Design choice: each generation trains on its own cohort's funded rows only (no
label accumulation across generations). This isolates the selection mechanism —
any drift is attributable to *who got funded*, not to a growing training set.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from . import config, eval_default, model_pd
from .diagnostics import PositivityDiagnostics, positivity_diagnostics
from .loop import LeverMetrics, make_generator


@dataclass
class GenerationResult:
    """One generation of the deployed-model feedback simulation."""

    generation: int
    #: ``"prior"`` (generation 0) or ``"model"`` (the previous generation's model
    #: made the funding decisions).
    policy: str
    funded_rate: float
    #: Observable portfolio performance: realized default rate of the funded book
    #: (including explored loans — they were funded too).
    funded_default_rate: float
    #: Planted-truth metrics for this generation's model on ITS OWN blind spot —
    #: the rows its training never saw. ``declined_*`` = unfunded rows.
    metrics: LeverMetrics
    #: Observable positivity diagnostics of the *policy* selection (before
    #: exploration), i.e. what monitoring would see.
    diagnostics: PositivityDiagnostics
    n_explored: int = 0
    explored_defaults: int = 0


@dataclass
class FeedbackResult:
    """Full trajectory of a feedback run."""

    generations: list[GenerationResult] = field(default_factory=list)
    selection_severity: float = 0.0
    exploration_rate: float = 0.0
    generator: str = "scm"

    @property
    def declined_ece_trajectory(self) -> list[float]:
        return [g.metrics.declined_ece for g in self.generations]


class FeedbackLoop:
    """Simulate model-in-the-loop selective labels across deployment generations."""

    def __init__(
        self,
        *,
        selection_severity: float = 0.4,
        n_generations: int = 6,
        exploration_rate: float = 0.0,
        generator: str = "scm",
        n_applicants: int = config.DEFAULT_N_APPLICANTS,
        approval_rate: float = config.DEFAULT_APPROVAL_RATE,
        seed: int = config.RANDOM_SEED,
        policy_threshold: float = config.POLICY_PD_THRESHOLD,
    ) -> None:
        if not 0.0 <= exploration_rate < 1.0:
            raise ValueError(f"exploration_rate must be in [0, 1); got {exploration_rate!r}")
        if n_generations < 1:
            raise ValueError(f"n_generations must be >= 1; got {n_generations!r}")
        self.selection_severity = selection_severity
        self.n_generations = n_generations
        self.exploration_rate = exploration_rate
        self.generator = generator
        self.n_applicants = n_applicants
        self.approval_rate = approval_rate
        self.seed = seed
        self.policy_threshold = policy_threshold

    # ------------------------------------------------------------------ #

    def _model_policy(self, model: model_pd.CalibratedPDModel, X: np.ndarray) -> np.ndarray:
        """Deterministic deployed policy: fund exactly the ``approval_rate``
        fraction with the lowest predicted PD.

        Rank-based top-k rather than a quantile cutoff: the isotonic calibrator
        makes predictions stepwise-constant, so ``p <= quantile(p, rate)`` can
        fund far more than ``rate`` through ties (observed: 84% at rate 0.6).
        ``argsort(kind="stable")`` breaks ties by row order — deterministic.
        """
        p = model_pd.predict_pd(model, X)
        k = int(round(self.approval_rate * len(p)))
        funded = np.zeros(len(p), dtype=bool)
        funded[np.argsort(p, kind="stable")[:k]] = True
        return funded

    def _explore(self, policy_funded: np.ndarray, generation: int) -> np.ndarray:
        if self.exploration_rate <= 0.0:
            return np.zeros_like(policy_funded)
        rng = np.random.default_rng([self.seed, generation, config.EXPLORE_STREAM_FEEDBACK])
        return (~policy_funded) & (rng.random(policy_funded.shape[0]) < self.exploration_rate)

    # ------------------------------------------------------------------ #

    def run(self) -> FeedbackResult:
        result = FeedbackResult(
            selection_severity=self.selection_severity,
            exploration_rate=self.exploration_rate,
            generator=self.generator,
        )
        model: model_pd.CalibratedPDModel | None = None

        for generation in range(self.n_generations):
            cohort = make_generator(
                self.generator,
                severity=self.selection_severity,
                seed=self.seed + generation,
                n_applicants=self.n_applicants,
                approval_rate=self.approval_rate,
            ).generate_cohort()
            X = cohort["features"].to_numpy(dtype=float)
            y = cohort["true_default"]

            if model is None:
                policy_funded = cohort["approved"]
                policy = "prior"
            else:
                policy_funded = self._model_policy(model, X)
                policy = "model"

            explored = self._explore(policy_funded, generation)
            funded = policy_funded | explored

            # Diagnose the POLICY selection (pre-exploration): that is the
            # selection a deployment would be monitoring.
            diag = positivity_diagnostics(X, policy_funded, random_state=self.seed + generation)

            if self.exploration_rate > 0.0:
                weights = np.where(explored, 1.0 / self.exploration_rate, 1.0)[funded]
            else:
                weights = None
            model = model_pd.train_pd_model(
                X[funded], y[funded], sample_weight=weights, random_state=self.seed + generation
            )

            scored = eval_default.score_pd_detection(model, cohort, self.policy_threshold, funded=funded)
            result.generations.append(
                GenerationResult(
                    generation=generation,
                    policy=policy,
                    funded_rate=float(funded.mean()),
                    funded_default_rate=float(y[funded].mean()),
                    metrics=LeverMetrics.from_scored(scored),
                    diagnostics=diag,
                    n_explored=int(explored.sum()),
                    explored_defaults=int(y[explored].sum()),
                )
            )

        return result
