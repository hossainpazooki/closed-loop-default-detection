"""Counterfactual validator — does a *deployable* causal estimator recover SCM truth?

This is the *causal evaluation* deliverable. The SCM in :mod:`cldd.scm` plants a
KNOWN interventional truth: for any ``do(feature = value)`` we can compute the
exact post-intervention default probability by propagating the change through the
DAG with frozen exogenous noise (see ``StructuralBorrowerGenerator.do_intervention``).
We use that known truth ONLY as the **gold-standard reference** to grade two
estimators that a real lender could actually ship:

  1. **NAIVE OBSERVATIONAL** — fit a calibrated PD model
     (:func:`cldd.model_pd.train_pd_model`) on the *observed/approved* rows, then
     answer ``do(X = v)`` by overwriting column ``X`` on the feature matrix and
     re-predicting. This is *conditioning* ``P(Y | X=v, rest=observed)``, not
     intervening: it ignores that moving ``X`` should move its SCM descendants,
     and it inherits the selection bias of the approved training sample.
  2. **G-COMPUTATION (standardization / backdoor adjustment)** — the deployable
     causal estimator. It is fit from the OBSERVED (approved) rows ONLY and uses
     **no SCM coefficients** — only (a) the DAG *topology* exposed by
     :func:`cldd.scm.dag_children` / :func:`cldd.scm.dag_parents` and (b) observed
     feature values + observed default outcomes. For each non-root node it fits a
     regressor ``child ~ parents``; it fits an outcome model ``E[default | features]``;
     then for ``do(X = v)`` it clamps ``X``, propagates the change to ``X``'s
     descendants through the *fitted* child mechanisms (expected values, in
     topological order), and reads the outcome model. This is the textbook
     g-formula / standardization, learned end-to-end from data.

The SCM's own ``do_intervention`` is **NOT an estimator** here — it *defines* the
truth, so grading it against itself would give MAE 0 by construction. We keep it
in the comparison ONLY as an explicit, clearly-labelled **truth reference**
(``oracle_*``) so the writeup can show how close the deployable g-computation gets
to the ceiling. The honest, non-tautological headline for §3 is: *g-computation
recovers the intervention materially better than naive conditioning* — measured,
not assumed — especially on the propagation slice (features whose interventions
move SCM descendants, plus the bank-feed gating trap) where conditioning
structurally cannot follow the change.

Design of the query set mirrors the real Deliverable-C ``intervention_queries.csv``
(900 rows = 3 queries x 300 applicants, ~19% non-intervenable targets, all at
in-support values), with added ~7% no-ops (``do(X = observed)``) and dose-response
repeats (same feature, increasing values) so the validator exercises the no-op
invariance and monotonicity properties directly. ``has_linked_bank_feed`` is in
the non-intervenable / propagation slice so the gating trap is measured.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor

from . import config
from .model_pd import predict_pd, train_pd_model
from .scm import (
    BANK_FEED_COLUMNS,
    FEATURE_COLUMNS,
    FEATURE_SUPPORT,
    INTERVENABLE_FEATURES,
    StructuralBorrowerGenerator,
    dag_children,
    dag_parents,
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

def _features_with_descendants() -> tuple[str, ...]:
    """Intervenable features that have >=1 SCM descendant in the DAG topology.

    Derived purely from :func:`cldd.scm.dag_children` (no SCM coefficients): a
    feature is a "propagation target" when moving it should move at least one
    child, so naive *conditioning* (overwrite one column, hold the rest) cannot
    recover the true *intervention*, whereas g-computation propagates through the
    fitted child mechanisms. This is the headline slice where a deployable causal
    method is expected to beat naive conditioning.
    """
    children = dag_children()

    def has_descendant(node: str) -> bool:
        stack = list(children.get(node, []))
        seen: set[str] = set()
        while stack:
            c = stack.pop()
            if c in seen:
                continue
            seen.add(c)
            stack.extend(children.get(c, []))
        return len(seen) > 0

    return tuple(
        f for f in INTERVENABLE_FEATURES if has_descendant(f)
    )


#: Intervenable features that have SCM descendants — moving them should move
#: their children, so naive *conditioning* (overwrite one column) cannot recover
#: the true *intervention*. Derived from the DAG topology. These plus the
#: non-intervenable probes form the "propagation targets" where conditioning !=
#: intervening (the headline set for the g-computation win).
_PROPAGATION_FEATURES = _features_with_descendants()

#: The strongest sub-slice: intervenable features whose interventions cascade to
#: MULTIPLE descendants (>=2 transitive children). On this slice naive
#: overwrite-one-column is most structurally wrong and the g-computation
#: propagation advantage is largest and most stable across seeds.
def _features_with_multi_descendants() -> tuple[str, ...]:
    children = dag_children()

    def n_descendants(node: str) -> int:
        stack = list(children.get(node, []))
        seen: set[str] = set()
        while stack:
            c = stack.pop()
            if c in seen:
                continue
            seen.add(c)
            stack.extend(children.get(c, []))
        return len(seen)

    return tuple(f for f in INTERVENABLE_FEATURES if n_descendants(f) >= 2)


_MULTI_DESCENDANT_FEATURES = _features_with_multi_descendants()

#: Dose-response ladders: fraction-of-support grid for a feature, low -> high.
_DOSE_GRID = (0.15, 0.45, 0.80)


@dataclass
class CounterfactualResult:
    """Outcome of :func:`run_counterfactual_eval`.

    ``queries`` is the per-query frame with the true counterfactual PD effect and
    each estimator's effect; ``*_mae`` / ``*_bias`` are aggregate accuracy of the
    *estimated effect* vs the *true effect*, split by target kind. The two graded
    estimators are ``naive`` (observational conditioning) and ``gcomp``
    (g-computation / standardization — the deployable causal method). ``oracle_*``
    is the SCM's own ``do_intervention`` kept ONLY as a truth reference (its MAE is
    ~0 by construction — it is NOT a competing estimator).
    """

    queries: pd.DataFrame
    # Naive observational estimator.
    naive_mae: float
    naive_bias: float
    naive_mae_intervenable: float
    naive_mae_non_intervenable: float
    naive_mae_propagation: float
    # G-computation estimator (the deployable causal method).
    gcomp_mae: float
    gcomp_bias: float
    gcomp_mae_intervenable: float
    gcomp_mae_non_intervenable: float
    gcomp_mae_propagation: float
    # Oracle TRUTH REFERENCE (SCM do_intervention graded against itself ~ 0).
    # Kept only to show the ceiling; NOT presented as a recovering estimator.
    oracle_mae: float
    oracle_mae_propagation: float
    # Strong descendant-propagation slice: intervenable features with >=2 SCM
    # descendants — the cleanest case where naive overwrite-one-column is
    # structurally wrong and g-computation's propagation advantage is largest.
    naive_mae_strong_propagation: float
    gcomp_mae_strong_propagation: float
    # Headline gaps (naive - gcomp): how much the deployable causal method beats
    # naive conditioning, overall and on the propagation / non-intervenable slices.
    mae_gap_overall: float
    mae_gap_non_intervenable: float
    mae_gap_propagation: float
    mae_gap_strong_propagation: float
    n_queries: int
    n_noop: int
    n_non_intervenable: int
    n_strong_propagation: int
    meta: dict = field(default_factory=dict)

    def summary(self) -> str:
        return (
            f"counterfactual eval: {self.n_queries} queries "
            f"({self.n_non_intervenable} non-intervenable, {self.n_noop} no-ops)\n"
            f"  naive  MAE={self.naive_mae:.4f} bias={self.naive_bias:+.4f} "
            f"(interv={self.naive_mae_intervenable:.4f}, "
            f"non-interv={self.naive_mae_non_intervenable:.4f}, "
            f"propagation={self.naive_mae_propagation:.4f})\n"
            f"  gcomp  MAE={self.gcomp_mae:.4f} bias={self.gcomp_bias:+.4f} "
            f"(interv={self.gcomp_mae_intervenable:.4f}, "
            f"non-interv={self.gcomp_mae_non_intervenable:.4f}, "
            f"propagation={self.gcomp_mae_propagation:.4f})\n"
            f"  oracle (truth ref, ~0 by construction) MAE={self.oracle_mae:.4f} "
            f"(propagation={self.oracle_mae_propagation:.4f})\n"
            f"  strong-propagation ({self.n_strong_propagation} q): "
            f"naive={self.naive_mae_strong_propagation:.4f} "
            f"gcomp={self.gcomp_mae_strong_propagation:.4f} "
            f"gap={self.mae_gap_strong_propagation:+.4f}\n"
            f"  g-comp vs naive MAE gap (naive - gcomp): "
            f"overall={self.mae_gap_overall:+.4f} "
            f"non-interv={self.mae_gap_non_intervenable:+.4f} "
            f"propagation={self.mae_gap_propagation:+.4f} "
            f"strong-propagation={self.mae_gap_strong_propagation:+.4f}"
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
# G-computation (standardization) estimator — the deployable causal method
# --------------------------------------------------------------------------- #


def _topo_order(parents: dict[str, list[str]]) -> list[str]:
    """Kahn topological order over the DAG nodes (parents -> children)."""
    # Build child adjacency over the union of all referenced nodes.
    nodes: set[str] = set(parents)
    for ps in parents.values():
        nodes.update(ps)
    indeg = {n: 0 for n in nodes}
    children: dict[str, list[str]] = {n: [] for n in nodes}
    for node, ps in parents.items():
        for p in ps:
            children[p].append(node)
            indeg[node] += 1
    # Stable: pop in sorted name order so the result is deterministic.
    ready = sorted(n for n in nodes if indeg[n] == 0)
    order: list[str] = []
    while ready:
        n = ready.pop(0)
        order.append(n)
        for c in sorted(children[n]):
            indeg[c] -= 1
            if indeg[c] == 0:
                ready.append(c)
        ready.sort()
    return order


class GComputationEstimator:
    """G-computation / standardization estimator of ``do(feature = value)``.

    Learned from OBSERVED (approved) rows ONLY. It uses **no SCM coefficients** —
    only the DAG *topology* (:func:`cldd.scm.dag_parents` /
    :func:`cldd.scm.dag_children`) and observed (feature, default) data. The pieces:

      * one :class:`~sklearn.ensemble.HistGradientBoostingRegressor` per non-root
        node, fit to predict ``node ~ parents`` (HistGBT handles NaN natively; the
        bank-feed block nodes are fit on feed-linked rows where the block is
        observed);
      * an outcome PD model ``E[default | features]`` reusing
        :func:`cldd.model_pd.train_pd_model`.

    To answer ``do(X = v)`` for a single applicant row: clamp ``X = v``, walk the
    topological order re-imputing every descendant of ``X`` from the fitted child
    mechanisms (expected value given the updated parents), then score the outcome
    model; the effect is ``post - baseline``. For the structural target
    ``has_linked_bank_feed`` it flips the gate and re-imputes the 6-node bank-feed
    block from the fitted child models (mirroring the SCM's information switch),
    rather than overwriting a single column.
    """

    def __init__(self, random_state: int = config.RANDOM_SEED):
        self.random_state = int(random_state)
        self.parents = dag_parents()
        self.children = dag_children()
        self.topo = _topo_order(self.parents)
        # Non-root modeled nodes that also appear as columns we can predict.
        self.node_models: dict[str, HistGradientBoostingRegressor] = {}
        self.outcome_model = None
        self.col_index = {c: j for j, c in enumerate(FEATURE_COLUMNS)}
        self._fitted = False

    # -- which nodes get a fitted child mechanism --------------------------- #
    def _modeled_children(self) -> list[str]:
        """Non-root nodes that are real feature columns we can fit and impute."""
        out = []
        for node, ps in self.parents.items():
            if not ps:
                continue
            if node not in self.col_index:
                continue
            # Only fit when every parent is also a usable column.
            if all(p in self.col_index for p in ps):
                out.append(node)
        return out

    def fit(self, features: pd.DataFrame, default: np.ndarray, approved: np.ndarray):
        """Fit child mechanisms + outcome model on the APPROVED rows only."""
        approved = np.asarray(approved, dtype=bool)
        X_full = features.to_numpy(dtype=float)
        Xa = X_full[approved]
        ya = np.asarray(default, dtype=int)[approved]
        feed_col = self.col_index["has_linked_bank_feed"]
        feed_a = Xa[:, feed_col] > 0.5

        block = set(BANK_FEED_COLUMNS)
        for node in self._modeled_children():
            ps = self.parents[node]
            pj = [self.col_index[p] for p in ps]
            # Bank-feed block nodes (and any node parented by them) are only
            # observed when a feed is linked — fit on the feed-linked rows so the
            # mechanism is learned where the block exists.
            needs_feed = (node in block) or any(p in block for p in ps)
            rows = feed_a if needs_feed else np.ones(len(Xa), dtype=bool)
            Xp = Xa[rows][:, pj]
            yt = Xa[rows][:, self.col_index[node]]
            ok = np.isfinite(yt)
            if ok.sum() < 20:
                continue
            reg = HistGradientBoostingRegressor(
                random_state=self.random_state,
                max_depth=3,
                max_iter=200,
                learning_rate=0.06,
                l2_regularization=1.0,
            )
            reg.fit(Xp[ok], yt[ok])
            self.node_models[node] = reg

        self.outcome_model = train_pd_model(
            Xa, ya, random_state=self.random_state
        )
        self._fitted = True
        return self

    # -- propagate a do() on a batch of applicant rows ---------------------- #
    def _predict_rows(self, X: np.ndarray) -> np.ndarray:
        return predict_pd(self.outcome_model, X)

    def _impute_descendants(self, X: np.ndarray, changed: set[str]) -> np.ndarray:
        """Re-impute, in topo order, every node downstream of ``changed`` using the
        fitted child mechanisms. ``X`` is a copy that already has the clamp applied;
        ``changed`` is the set of nodes whose value was set/updated."""
        for node in self.topo:
            if node not in self.node_models:
                continue
            ps = self.parents[node]
            if not any(p in changed for p in ps):
                continue
            pj = [self.col_index[p] for p in ps]
            X[:, self.col_index[node]] = self.node_models[node].predict(X[:, pj])
            changed.add(node)
        return X

    def effect(
        self,
        features: pd.DataFrame,
        feature: str,
        value,
        applicant_ids: np.ndarray,
    ) -> np.ndarray:
        """Estimated per-query effect of ``do(feature = value)`` at each applicant.

        ``value`` is a scalar (broadcast) or per-query array aligned with
        ``applicant_ids``. Returns ``post_pd - baseline_pd`` at each queried row.
        """
        if not self._fitted:
            raise RuntimeError("GComputationEstimator must be fit() before use")
        X_full = features.to_numpy(dtype=float)
        aids = np.asarray(applicant_ids)
        vals = np.broadcast_to(np.asarray(value, dtype=float), (len(aids),))

        if feature == "has_linked_bank_feed":
            base_rows = X_full[aids].copy()
            baseline = self._predict_rows(base_rows)
            return self._effect_feed_switch(X_full[aids].copy(), vals, baseline)

        if feature not in self.col_index:
            # Identity / unmodeled non-intervenable node: g-computation also
            # refuses (no fitted mechanism, no column) -> zero effect.
            return np.zeros(len(aids))

        # Baseline = the deployed model's prediction on the FACTUAL row (observed
        # descendants, no imputation). Post arm = clamp the target, then propagate
        # the change to its descendants through the fitted child mechanisms
        # (standardization / g-formula). The contrast keeps the full descendant
        # contribution (it is NOT cancelled by also imputing the baseline), which
        # is exactly the propagation that naive overwrite-one-column misses.
        col = self.col_index[feature]
        observed = X_full[aids, col].copy()
        base_rows = X_full[aids].copy()
        baseline = self._predict_rows(base_rows)

        post_rows = X_full[aids].copy()
        post_rows[:, col] = vals
        post_rows = self._impute_descendants(post_rows, changed={feature})
        post = self._predict_rows(post_rows)
        effect = post - baseline
        # Per-unit no-op invariance: where the clamp equals the observed value the
        # intervention is a no-op, so the effect is exactly 0 (no spurious
        # mechanism-reconstruction error leaks in). Matches the SCM's exact no-op.
        is_noop_unit = (vals == observed) | (~np.isfinite(vals) & ~np.isfinite(observed))
        effect[is_noop_unit] = 0.0
        return effect

    def _effect_feed_switch(
        self, post_rows: np.ndarray, vals: np.ndarray, baseline: np.ndarray
    ) -> np.ndarray:
        """do(has_linked_bank_feed = v): flip the gate and re-impute the block.

        Mirrors the SCM's structural switch — turning a feed ON reveals the 6-node
        bank-feed block (imputed from the fitted child mechanisms), turning it OFF
        hides it (set the block to NaN, which the NaN-native outcome model accepts).
        Where the feed status does not flip, the row is unchanged (exact no-op).
        """
        feed_col = self.col_index["has_linked_bank_feed"]
        new_feed = vals > 0.5
        cur_feed = post_rows[:, feed_col] > 0.5
        flips = new_feed != cur_feed
        block_cols = [self.col_index[c] for c in BANK_FEED_COLUMNS]
        # DIAG(leak-fix a): the revenue-derived ratio is gated with the block, so a
        # feed-OFF flip must hide it too (turning feed ON re-imputes it via the
        # observed-revenue child mechanism already, since it is a feed-parented node).
        if "requested_amount_to_observed_revenue" in self.col_index:
            block_cols = block_cols + [self.col_index["requested_amount_to_observed_revenue"]]

        post_rows[:, feed_col] = new_feed.astype(float)
        # Turn feeds OFF -> hide the block (structural missingness).
        off = flips & (~new_feed)
        if off.any():
            for j in block_cols:
                post_rows[np.ix_(off, [j])] = np.nan
        # Turn feeds ON -> reveal/impute the block from fitted child mechanisms.
        on = flips & new_feed
        if on.any():
            self._impute_descendants(
                post_rows, changed={"has_linked_bank_feed"} | set(BANK_FEED_COLUMNS)
            )
        post = self._predict_rows(post_rows)
        effect = post - baseline
        # Exact no-op for unflipped units (mirror the SCM invariance).
        effect[~flips] = 0.0
        return effect


# --------------------------------------------------------------------------- #
# Reference + naive estimators
# --------------------------------------------------------------------------- #


def _true_counterfactual_effects(
    generator: StructuralBorrowerGenerator,
    state,
    queries: pd.DataFrame,
) -> tuple[np.ndarray, np.ndarray]:
    """Per-query (true_effect_at_applicant, true_baseline_at_applicant).

    The SCM's planted truth: for each query, propagate ``do(feature=value)`` for
    ALL units, then read the effect at the query's own applicant. This is the gold
    standard all estimators are graded against.
    """
    true_effect = np.zeros(len(queries))
    true_baseline = np.zeros(len(queries))
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


def _oracle_effects(
    generator: StructuralBorrowerGenerator,
    state,
    queries: pd.DataFrame,
) -> np.ndarray:
    """TRUTH REFERENCE (NOT an estimator): the SCM's own ``do_intervention``.

    This calls the exact same structural propagation that *defines* the gold
    standard, so its MAE is ~0 by construction. It is reported only to mark the
    ceiling the deployable g-computation estimator is reaching toward — it is never
    presented as a method that "recovers" an unknown truth.
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
    """Build a cohort, generate Deliverable-C-style queries, grade the estimators.

    Three-way comparison against the SCM's planted truth:

    * **naive** observational conditioning,
    * **gcomp** g-computation / standardization (the deployable causal estimator),
    * **oracle** = the SCM's own ``do_intervention`` kept ONLY as a truth reference.

    Both deployable estimators are fit on the APPROVED rows only (selective-labels
    regime), so their conditionals are distorted by selection — exactly the
    confound g-computation's backdoor adjustment is meant to repair.
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
    train_rs = seed + config.TRAIN_SEED_OFFSET
    model = train_pd_model(X[approved], true_default[approved], random_state=train_rs)

    # --- fit the deployable g-computation estimator on APPROVED rows ---
    gcomp = GComputationEstimator(random_state=train_rs).fit(
        features, true_default, approved
    )

    # --- queries ---
    queries = generate_queries(
        cohort, n_applicants=n_query_applicants, seed=seed
    ).reset_index(drop=True)

    # --- true counterfactual + estimators (all measured as EFFECTS) ---
    true_effect, true_baseline = _true_counterfactual_effects(generator, state, queries)
    naive_effect = _naive_observational_effects(model, features, queries)
    oracle_effect = _oracle_effects(generator, state, queries)

    # g-computation, grouped by (feature, value) so each do() is a single vector op.
    aids_all = queries["applicant_id"].to_numpy()
    gcomp_effect = np.zeros(len(queries))
    for (feat, val), grp in queries.groupby(
        ["feature_name", "intervention_value"], sort=False
    ):
        idx = grp.index.to_numpy()
        gcomp_effect[idx] = gcomp.effect(features, feat, float(val), aids_all[idx])

    queries = queries.assign(
        true_baseline_pd=true_baseline,
        true_effect=true_effect,
        naive_effect=naive_effect,
        gcomp_effect=gcomp_effect,
        oracle_effect=oracle_effect,
        naive_abs_err=np.abs(naive_effect - true_effect),
        gcomp_abs_err=np.abs(gcomp_effect - true_effect),
        oracle_abs_err=np.abs(oracle_effect - true_effect),
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
    gcomp_err = queries["gcomp_abs_err"].to_numpy()
    oracle_err = queries["oracle_abs_err"].to_numpy()

    # Propagation targets: features with SCM descendants OR non-intervenable —
    # the set where naive conditioning structurally cannot recover the intervention
    # (includes has_linked_bank_feed via the non-intervenable mask).
    prop_mask = (
        queries["feature_name"].isin(_PROPAGATION_FEATURES).to_numpy() | non_interv
    )

    # Strong descendant-propagation slice: intervenable features with >=2 SCM
    # descendants. This is the cleanest, most stable case where naive
    # overwrite-one-column is structurally wrong (the moved cause has several
    # risk-bearing children it fails to update) and g-computation propagates them.
    strong_mask = queries["feature_name"].isin(_MULTI_DESCENDANT_FEATURES).to_numpy()

    naive_mae_non = _mae(naive_err, non_interv)
    gcomp_mae_non = _mae(gcomp_err, non_interv)
    naive_mae_prop = _mae(naive_err, prop_mask)
    gcomp_mae_prop = _mae(gcomp_err, prop_mask)
    naive_mae_strong = _mae(naive_err, strong_mask)
    gcomp_mae_strong = _mae(gcomp_err, strong_mask)
    naive_mae_all = _mae(naive_err)
    gcomp_mae_all = _mae(gcomp_err)

    return CounterfactualResult(
        queries=queries,
        naive_mae=naive_mae_all,
        naive_bias=_bias(naive_effect, true_effect),
        naive_mae_intervenable=_mae(naive_err, is_interv),
        naive_mae_non_intervenable=naive_mae_non,
        naive_mae_propagation=naive_mae_prop,
        gcomp_mae=gcomp_mae_all,
        gcomp_bias=_bias(gcomp_effect, true_effect),
        gcomp_mae_intervenable=_mae(gcomp_err, is_interv),
        gcomp_mae_non_intervenable=gcomp_mae_non,
        gcomp_mae_propagation=gcomp_mae_prop,
        oracle_mae=_mae(oracle_err),
        oracle_mae_propagation=_mae(oracle_err, prop_mask),
        naive_mae_strong_propagation=naive_mae_strong,
        gcomp_mae_strong_propagation=gcomp_mae_strong,
        mae_gap_overall=naive_mae_all - gcomp_mae_all,
        mae_gap_non_intervenable=naive_mae_non - gcomp_mae_non,
        mae_gap_propagation=naive_mae_prop - gcomp_mae_prop,
        mae_gap_strong_propagation=naive_mae_strong - gcomp_mae_strong,
        n_queries=len(queries),
        n_noop=int(queries["is_noop"].sum()),
        n_non_intervenable=int(non_interv.sum()),
        n_strong_propagation=int(strong_mask.sum()),
        meta={
            "selection_severity": selection_severity,
            "n_applicants": n_applicants,
            "seed": seed,
            "approval_rate": float(approved.mean()),
        },
    )
