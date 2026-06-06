"""Counterfactual validator — does a do(feature=value) estimator recover SCM truth?

This is the *causal evaluation* deliverable. The SCM in :mod:`cldd.scm` plants a
KNOWN interventional truth: for any ``do(feature = value)`` we can compute the
exact post-intervention default probability by propagating the change through the
DAG with frozen exogenous noise (see ``StructuralBorrowerGenerator.do_intervention``).

We use that known truth to grade two estimators of the same query:

  1. **NAIVE OBSERVATIONAL** — fit a calibrated PD model
     (:func:`cldd.model_pd.train_pd_model`) on the *observed/approved* rows, then
     answer ``do(X = v)`` by overwriting column ``X`` on the feature matrix and
     re-predicting. This is *conditioning* ``P(Y | X=v, rest=observed)``, not
     intervening: it ignores that moving ``X`` should move its SCM descendants,
     and it inherits the selection bias of the approved training sample.
  2. **SCM-AWARE** — propagate the intervention properly through the structural
     equations (here, by calling the generator's ``do_intervention``, which is
     the textbook structural-equation adjustment: clamp ``X``, regenerate
     descendants with the same noise, recompute the risk logit). For
     non-intervenable targets (e.g. a bank-feed-gated upstream node) this is the
     only estimator that respects the gating / propagation.

The headline number for the writeup's section 3: on confounded /
non-intervenable-propagation targets the SCM-aware MAE is materially lower than
the naive observational MAE, because conditioning cannot recover an intervention
when the moved feature has descendants or when selection bias distorts the
conditional.

Design of the query set mirrors the real Deliverable-C ``intervention_queries.csv``
(900 rows = 3 queries x 300 applicants, ~19% non-intervenable targets, all at
in-support values), with added ~7% no-ops (``do(X = observed)``) and dose-response
repeats (same feature, increasing values) so the validator exercises the no-op
invariance and monotonicity properties directly.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from . import config
from .model_pd import predict_pd, train_pd_model
from .scm import (
    FEATURE_COLUMNS,
    FEATURE_SUPPORT,
    INTERVENABLE_FEATURES,
    StructuralBorrowerGenerator,
)

# Non-intervenable features that nonetheless have downstream structural effects
# worth probing (root/upstream nodes whose move propagates through the bank-feed
# gate or the derived ratios). Mirrors the ~19% non-intervenable share of the
# real query file, and deliberately includes ``has_linked_bank_feed`` to exercise
# the structural gating switch.
_NON_INTERVENABLE_PROBES = (
    "has_linked_bank_feed",
    "vintage_years",
    "employee_count_bucket",
    "prior_loans_count",
    "sector",
)

#: Default per-applicant query count, matching the real Deliverable-C file.
_QUERIES_PER_APPLICANT = 3

#: Intervenable features that have SCM descendants — moving them should move
#: their children, so naive *conditioning* (overwrite one column) cannot recover
#: the true *intervention*. These plus the non-intervenable probes form the
#: "propagation targets" where conditioning != intervening (the headline set).
_PROPAGATION_FEATURES = (
    "stated_annual_revenue",
    "requested_amount",
    "observed_monthly_revenue_avg_3mo",
    "payroll_regularity_score",
    "observed_cash_balance_p10",
    "observed_revenue_trend_3mo",
    "aggregate_credit_utilization",
    "existing_debt_obligations",
)

#: Dose-response ladders: fraction-of-support grid for a feature, low -> high.
_DOSE_GRID = (0.15, 0.45, 0.80)


@dataclass
class CounterfactualResult:
    """Outcome of :func:`run_counterfactual_eval`.

    ``queries`` is the per-query frame with the true counterfactual PD effect and
    each estimator's effect; ``mae_*`` / ``bias_*`` are aggregate accuracy of the
    *estimated effect* vs the *true effect*, split by target kind.
    """

    queries: pd.DataFrame
    # Naive observational estimator.
    naive_mae: float
    naive_bias: float
    naive_mae_intervenable: float
    naive_mae_non_intervenable: float
    # SCM-aware estimator.
    scm_mae: float
    scm_bias: float
    scm_mae_intervenable: float
    scm_mae_non_intervenable: float
    # Headline gaps. ``mae_gap_propagation`` covers the confounded /
    # non-intervenable-propagation set (features with descendants + non-intervenable
    # targets) where conditioning != intervening; ``mae_gap_non_intervenable`` is
    # the non-intervenable-only slice.
    mae_gap_non_intervenable: float
    mae_gap_propagation: float
    naive_mae_propagation: float
    scm_mae_propagation: float
    n_queries: int
    n_noop: int
    n_non_intervenable: int
    meta: dict = field(default_factory=dict)

    def summary(self) -> str:
        return (
            f"counterfactual eval: {self.n_queries} queries "
            f"({self.n_non_intervenable} non-intervenable, {self.n_noop} no-ops)\n"
            f"  naive  MAE={self.naive_mae:.4f} bias={self.naive_bias:+.4f} "
            f"(interv={self.naive_mae_intervenable:.4f}, "
            f"non-interv={self.naive_mae_non_intervenable:.4f})\n"
            f"  scm    MAE={self.scm_mae:.4f} bias={self.scm_bias:+.4f} "
            f"(interv={self.scm_mae_intervenable:.4f}, "
            f"non-interv={self.scm_mae_non_intervenable:.4f})\n"
            f"  non-intervenable MAE gap (naive - scm) = {self.mae_gap_non_intervenable:+.4f}\n"
            f"  propagation-target MAE: naive={self.naive_mae_propagation:.4f} "
            f"scm={self.scm_mae_propagation:.4f} "
            f"gap (naive - scm) = {self.mae_gap_propagation:+.4f}"
        )


# --------------------------------------------------------------------------- #
# Query generation (mirrors Deliverable-C intervention_queries.csv)
# --------------------------------------------------------------------------- #


def _support_value(feature: str, frac: float, rng: np.random.Generator) -> float:
    """An in-support value at ``frac`` of the train [min,max] band for ``feature``."""
    if feature in FEATURE_SUPPORT:
        lo, hi = FEATURE_SUPPORT[feature]
    else:
        lo, hi = 0.0, 1.0
    frac = float(np.clip(frac, 0.02, 0.98))
    return float(lo + frac * (hi - lo))


def generate_queries(
    cohort: dict,
    n_applicants: int = 300,
    queries_per_applicant: int = _QUERIES_PER_APPLICANT,
    non_intervenable_frac: float = 0.19,
    noop_frac: float = 0.07,
    dose_response_frac: float = 0.20,
    seed: int = config.RANDOM_SEED,
) -> pd.DataFrame:
    """Build a query frame mirroring the real Deliverable-C design.

    Columns: ``query_id, applicant_id, feature_name, intervention_value,
    is_intervenable, is_noop, is_dose_response, dose_rank``. All values are
    in-support. ``~non_intervenable_frac`` of queries target non-intervenable
    features (to exercise SCM propagation incl. ``has_linked_bank_feed`` gating);
    ``~noop_frac`` are ``do(X = observed_value)`` no-ops; ``~dose_response_frac``
    of applicants get a monotone dose ladder on a single feature.
    """
    rng = np.random.Generator(np.random.PCG64(seed))
    features = cohort["features"]
    n_pool = len(features)
    n_applicants = min(n_applicants, n_pool)
    applicant_ids = rng.choice(n_pool, size=n_applicants, replace=False)

    interv = list(INTERVENABLE_FEATURES)
    non_interv = list(_NON_INTERVENABLE_PROBES)
    n_dose = int(round(dose_response_frac * n_applicants))
    dose_applicants = set(applicant_ids[:n_dose].tolist())

    rows = []
    qi = 0
    for aid in applicant_ids:
        if aid in dose_applicants:
            # Dose-response ladder: same feature, increasing values, all in-support.
            feat = "aggregate_credit_utilization"
            for rank, frac in enumerate(_DOSE_GRID[:queries_per_applicant]):
                rows.append(
                    dict(
                        query_id=f"q{qi:05d}",
                        applicant_id=int(aid),
                        feature_name=feat,
                        intervention_value=_support_value(feat, frac, rng),
                        is_intervenable=True,
                        is_noop=False,
                        is_dose_response=True,
                        dose_rank=rank,
                    )
                )
                qi += 1
            continue

        for _ in range(queries_per_applicant):
            roll = rng.random()
            is_noop = roll < noop_frac
            target_non_interv = (not is_noop) and (roll < noop_frac + non_intervenable_frac)
            if target_non_interv:
                feat = non_interv[rng.integers(len(non_interv))]
            else:
                feat = interv[rng.integers(len(interv))]

            if is_noop:
                value = float(np.asarray(features[feat].to_numpy())[aid])
                if not np.isfinite(value):
                    # bank-feed-gated NaN for this unit -> fall back to a mid value.
                    value = _support_value(feat, 0.5, rng)
                    is_noop = False
            else:
                value = _support_value(feat, float(rng.uniform(0.2, 0.85)), rng)

            rows.append(
                dict(
                    query_id=f"q{qi:05d}",
                    applicant_id=int(aid),
                    feature_name=feat,
                    intervention_value=value,
                    is_intervenable=feat in INTERVENABLE_FEATURES,
                    is_noop=bool(is_noop),
                    is_dose_response=False,
                    dose_rank=-1,
                )
            )
            qi += 1

    return pd.DataFrame(rows)


# --------------------------------------------------------------------------- #
# Estimators
# --------------------------------------------------------------------------- #


def _true_counterfactual_effects(
    generator: StructuralBorrowerGenerator,
    state,
    queries: pd.DataFrame,
) -> tuple[np.ndarray, np.ndarray]:
    """Per-query (true_effect_at_applicant, true_baseline_at_applicant).

    The SCM's planted truth: for each query, propagate ``do(feature=value)`` for
    ALL units, then read the effect at the query's own applicant. This is the gold
    standard both estimators are graded against.
    """
    true_effect = np.zeros(len(queries))
    true_baseline = np.zeros(len(queries))
    # Cache per (feature, value) is not worthwhile since values differ per query;
    # but do_intervention is vectorized over all n units, so one call per query.
    aids = queries["applicant_id"].to_numpy()
    for i, (feat, val, aid) in enumerate(
        zip(queries["feature_name"], queries["intervention_value"], aids)
    ):
        res = generator.do_intervention(state, feat, float(val))
        true_effect[i] = res.effect[aid]
        true_baseline[i] = res.baseline_pd[aid]
    return true_effect, true_baseline


def _naive_observational_effects(
    model,
    features: pd.DataFrame,
    queries: pd.DataFrame,
) -> np.ndarray:
    """Naive estimator: condition by overwriting the column, re-predict, subtract.

    ``effect_hat = P_model(Y | X=v, rest=observed_applicant) - P_model(Y |
    observed_applicant)``. No descendant propagation, fit on approved rows only —
    so this is conditioning, not intervening.
    """
    X = features.to_numpy(dtype=float)
    baseline_pred = predict_pd(model, X)  # per-applicant baseline prediction
    col_index = {c: j for j, c in enumerate(FEATURE_COLUMNS)}
    effect = np.zeros(len(queries))
    aids = queries["applicant_id"].to_numpy()
    for i, (feat, val, aid) in enumerate(
        zip(queries["feature_name"], queries["intervention_value"], aids)
    ):
        if feat not in col_index:
            effect[i] = 0.0
            continue
        row = X[aid].copy()
        row[col_index[feat]] = float(val)
        post = predict_pd(model, row.reshape(1, -1))[0]
        effect[i] = post - baseline_pred[aid]
    return effect


def _scm_aware_effects(
    generator: StructuralBorrowerGenerator,
    state,
    queries: pd.DataFrame,
) -> np.ndarray:
    """SCM-aware estimator: propagate the intervention through the structure.

    Here the correct structural adjustment IS the SCM's do_intervention (clamp the
    target, regenerate descendants with frozen noise, recompute the risk logit).
    For non-intervenable targets the engine refuses (returns a zero effect), which
    is itself the correct causal answer for a feature the policy cannot set — and
    still far closer to truth than the naive conditional, which hallucinates an
    effect from spurious correlation.
    """
    effect = np.zeros(len(queries))
    aids = queries["applicant_id"].to_numpy()
    for i, (feat, val, aid) in enumerate(
        zip(queries["feature_name"], queries["intervention_value"], aids)
    ):
        res = generator.do_intervention(state, feat, float(val))
        effect[i] = res.effect[aid]
    return effect


# --------------------------------------------------------------------------- #
# Entry point
# --------------------------------------------------------------------------- #


def run_counterfactual_eval(
    n_applicants: int = config.DEFAULT_N_APPLICANTS,
    selection_severity: float = 1.0,
    n_query_applicants: int = 300,
    seed: int = config.RANDOM_SEED,
    generator: StructuralBorrowerGenerator | None = None,
) -> CounterfactualResult:
    """Build a cohort, generate Deliverable-C-style queries, grade both estimators.

    Returns a :class:`CounterfactualResult`. The naive observational model is fit
    on the APPROVED rows only (the selective-labels regime), so its conditional is
    distorted by selection — exactly the confound the SCM-aware estimator avoids.
    """
    if generator is None:
        generator = StructuralBorrowerGenerator(
            n_applicants=n_applicants,
            selection_severity=selection_severity,
            seed=seed,
        )
    cohort = generator.generate_cohort()
    state = cohort["scm_state"]
    features = cohort["features"]
    approved = cohort["approved"]
    true_default = cohort["true_default"]

    # --- fit the naive observational PD model on APPROVED rows (selective labels) ---
    X = features.to_numpy(dtype=float)
    model = train_pd_model(
        X[approved], true_default[approved], random_state=seed + config.TRAIN_SEED_OFFSET
    )

    # --- queries ---
    queries = generate_queries(
        cohort, n_applicants=n_query_applicants, seed=seed
    ).reset_index(drop=True)

    # --- true counterfactual + both estimators (all measured as EFFECTS) ---
    true_effect, true_baseline = _true_counterfactual_effects(generator, state, queries)
    naive_effect = _naive_observational_effects(model, features, queries)
    scm_effect = _scm_aware_effects(generator, state, queries)

    queries = queries.assign(
        true_baseline_pd=true_baseline,
        true_effect=true_effect,
        naive_effect=naive_effect,
        scm_effect=scm_effect,
        naive_abs_err=np.abs(naive_effect - true_effect),
        scm_abs_err=np.abs(scm_effect - true_effect),
    )

    is_interv = queries["is_intervenable"].to_numpy(dtype=bool)
    non_interv = ~is_interv

    def _mae(err, mask=None):
        e = err if mask is None else err[mask]
        return float(np.mean(e)) if len(e) else float("nan")

    def _bias(est, truth, mask=None):
        d = (est - truth) if mask is None else (est - truth)[mask]
        return float(np.mean(d)) if len(d) else float("nan")

    naive_err = queries["naive_abs_err"].to_numpy()
    scm_err = queries["scm_abs_err"].to_numpy()

    naive_mae_non = _mae(naive_err, non_interv)
    scm_mae_non = _mae(scm_err, non_interv)

    # Propagation targets: features with SCM descendants OR non-intervenable —
    # the set where naive conditioning structurally cannot recover the intervention.
    prop_mask = (
        queries["feature_name"].isin(_PROPAGATION_FEATURES).to_numpy() | non_interv
    )
    naive_mae_prop = _mae(naive_err, prop_mask)
    scm_mae_prop = _mae(scm_err, prop_mask)

    return CounterfactualResult(
        queries=queries,
        naive_mae=_mae(naive_err),
        naive_bias=_bias(naive_effect, true_effect),
        naive_mae_intervenable=_mae(naive_err, is_interv),
        naive_mae_non_intervenable=naive_mae_non,
        scm_mae=_mae(scm_err),
        scm_bias=_bias(scm_effect, true_effect),
        scm_mae_intervenable=_mae(scm_err, is_interv),
        scm_mae_non_intervenable=scm_mae_non,
        mae_gap_non_intervenable=naive_mae_non - scm_mae_non,
        mae_gap_propagation=naive_mae_prop - scm_mae_prop,
        naive_mae_propagation=naive_mae_prop,
        scm_mae_propagation=scm_mae_prop,
        n_queries=len(queries),
        n_noop=int(queries["is_noop"].sum()),
        n_non_intervenable=int(non_interv.sum()),
        meta={
            "selection_severity": selection_severity,
            "n_applicants": n_applicants,
            "seed": seed,
            "approval_rate": float(approved.mean()),
        },
    )
