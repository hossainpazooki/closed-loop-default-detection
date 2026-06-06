"""Tests for the counterfactual validator (cldd.counterfactual).

These assert the three properties the writeup's section 3 leans on:
  (a) no-op invariance — do(X = observed) leaves the TRUE PD unchanged (exact);
  (b) dose-response monotonicity — raising aggregate_credit_utilization raises
      the true post-intervention PD;
  (c) the headline causal result — on confounded / non-intervenable-propagation
      targets the SCM-aware estimator's MAE beats the naive observational one.
"""

from __future__ import annotations

import numpy as np

from cldd.counterfactual import (
    CounterfactualResult,
    generate_queries,
    run_counterfactual_eval,
)
from cldd.scm import StructuralBorrowerGenerator


def _generator(seed: int = 42, n: int = 2000, severity: float = 1.0):
    return StructuralBorrowerGenerator(
        n_applicants=n, selection_severity=severity, seed=seed
    )


# --------------------------------------------------------------------------- #
# (a) No-op invariance: do(X = observed_value) is exactly the baseline.
# --------------------------------------------------------------------------- #


def test_noop_invariance_true_scm_exact():
    """do(X = observed) reproduces the baseline true PD to machine precision."""
    gen = _generator(seed=11)
    cohort = gen.generate_cohort()
    state = cohort["scm_state"]

    for feat in ("aggregate_credit_utilization", "observed_cash_balance_p10",
                 "requested_amount", "invoice_payment_delinquency_rate"):
        # The per-unit observed value is the UNGATED state value (the gated
        # DataFrame carries NaN for no-feed rows, which is not the SCM's realized
        # value). do(X = realized observed) must be an exact no-op.
        observed = np.asarray(state.values[feat], dtype=float)
        res = gen.do_intervention(state, feat, observed)
        assert res.is_noop, f"{feat}: do(X=observed) should be a no-op"
        assert np.max(np.abs(res.effect)) < 1e-10, f"{feat}: no-op effect not ~0"
        np.testing.assert_allclose(res.true_pd, res.baseline_pd, atol=1e-10)


def test_noop_queries_have_zero_true_effect():
    """Queries flagged is_noop carry ~zero true counterfactual effect."""
    res = run_counterfactual_eval(
        n_applicants=2000, n_query_applicants=200, seed=42
    )
    noops = res.queries[res.queries["is_noop"]]
    assert len(noops) > 0, "expected some no-op queries in the Deliverable-C design"
    assert noops["true_effect"].abs().max() < 1e-9


# --------------------------------------------------------------------------- #
# (b) Dose-response monotonicity on aggregate_credit_utilization.
# --------------------------------------------------------------------------- #


def test_dose_response_monotone_true_pd():
    """Raising aggregate_credit_utilization raises the mean true post-do PD."""
    gen = _generator(seed=5)
    state = gen.generate_cohort()["scm_state"]
    feat = "aggregate_credit_utilization"
    # In-support ladder from low to high utilization.
    levels = [0.05, 0.25, 0.50, 0.75, 0.95]
    means = [float(gen.do_intervention(state, feat, v).true_pd.mean()) for v in levels]
    # Strictly increasing mean true PD.
    assert all(b > a for a, b in zip(means, means[1:])), f"non-monotone: {means}"
    # And the top level should be materially riskier than the bottom.
    assert means[-1] - means[0] > 0.10


def test_dose_response_queries_monotone_in_frame():
    """The generated dose-response ladder yields increasing true effect by rank."""
    gen = _generator(seed=9)
    cohort = gen.generate_cohort()
    queries = generate_queries(cohort, n_applicants=120, seed=9)
    dose = queries[queries["is_dose_response"]]
    assert len(dose) > 0
    # Within each applicant ladder, value increases with dose_rank.
    for aid, grp in dose.groupby("applicant_id"):
        g = grp.sort_values("dose_rank")
        vals = g["intervention_value"].to_numpy()
        assert np.all(np.diff(vals) > 0), f"applicant {aid} ladder not increasing"


# --------------------------------------------------------------------------- #
# (c) Headline: SCM-aware beats naive observational on propagation targets.
# --------------------------------------------------------------------------- #


def test_scm_aware_beats_naive_on_propagation_targets():
    """On confounded / non-intervenable-propagation targets, SCM-aware MAE < naive."""
    res = run_counterfactual_eval(
        n_applicants=2500, n_query_applicants=250, selection_severity=1.0, seed=42
    )
    assert isinstance(res, CounterfactualResult)
    # SCM-aware is the truth-propagating estimator: near-exact on the propagation set.
    assert res.scm_mae_propagation < res.naive_mae_propagation
    # The gap is large, not marginal — the headline number for the writeup.
    assert res.mae_gap_propagation > 0.02
    # SCM-aware never worse than naive on the non-intervenable slice either.
    assert res.scm_mae_non_intervenable <= res.naive_mae_non_intervenable + 1e-9


def test_scm_aware_beats_naive_overall_and_on_intervenable():
    """The naive conditional fails on intervenable features WITH descendants."""
    res = run_counterfactual_eval(
        n_applicants=2500, n_query_applicants=250, selection_severity=1.0, seed=7
    )
    assert res.scm_mae < res.naive_mae
    # The intervenable-with-descendants failure mode is where naive is worst.
    assert res.naive_mae_intervenable > res.scm_mae_intervenable


def test_determinism_same_seed():
    a = run_counterfactual_eval(n_applicants=1500, n_query_applicants=150, seed=3)
    b = run_counterfactual_eval(n_applicants=1500, n_query_applicants=150, seed=3)
    assert a.naive_mae == b.naive_mae
    assert a.scm_mae == b.scm_mae
    assert a.mae_gap_propagation == b.mae_gap_propagation
