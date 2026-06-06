"""Tests for the closed loop: improve levers, no-leakage, determinism, frontier."""

from __future__ import annotations

import numpy as np

from cldd import SelectiveLabelsLoop, config
from cldd.eval_default import fit_observed_model, score_pd_detection
from cldd.loop import LeverMetrics
from cldd.model_pd import selection_adjusted_weights
from cldd.synthetic import SyntheticBorrowerGenerator


def _scored(cohort, sample_weight=None, seed=42):
    model = fit_observed_model(cohort, sample_weight=sample_weight, random_state=seed)
    return score_pd_detection(model, cohort)


def test_selection_bias_underestimates_decline_risk():
    """Naive train-on-approved under-predicts default on the riskier declines."""
    cohort = SyntheticBorrowerGenerator(n_applicants=5000, selection_severity=1.0, seed=42).generate_cohort()
    scored = _scored(cohort)
    declined = scored["declined"]
    # The model trained on the safe approved pool systematically under-scores the
    # high-risk declines: mean predicted PD is well below their true default rate.
    assert declined.mean_pd < declined.base_rate


def test_ipw_reweight_reduces_decline_bias():
    """IPW reweighting narrows the predicted-vs-true gap on declines.

    Tested at *moderate* severity (0.4), where selection is driven mostly by
    observed features and the approved/declined pools still overlap — the regime
    IPW is designed for. At extreme severity, selection leaks through the
    unobserved confounder and positivity breaks down, so IPW legitimately stops
    helping; that breakdown is the operating frontier the loop measures, not a
    property this test should assert away.
    """
    cohort = SyntheticBorrowerGenerator(n_applicants=5000, selection_severity=0.4, seed=42).generate_cohort()
    X = cohort["features"].to_numpy(dtype=float)
    approved = cohort["approved"]

    naive = _scored(cohort)["declined"]
    weights = selection_adjusted_weights(X, approved, random_state=42)
    reweighted = _scored(cohort, sample_weight=weights[approved])["declined"]

    naive_gap = abs(naive.mean_pd - naive.base_rate)
    reweight_gap = abs(reweighted.mean_pd - reweighted.base_rate)
    # IPW pulls the mean PD on declines back toward the truth.
    assert reweight_gap < naive_gap


def test_no_leakage_train_seed_disjoint():
    """The retrain lever fits on a seed disjoint from the measure cohort seed."""
    loop = SelectiveLabelsLoop(improve_mode="retrain", max_rounds=2, n_applicants=1500, seed=42)
    result = loop.run()
    assert result.rounds
    for r in result.rounds:
        measure_seed = loop.seed + r.iteration
        assert r.retrain_train_seed == loop.seed + loop.train_seed_offset + r.iteration
        assert r.retrain_train_seed != measure_seed


def test_loop_is_deterministic():
    def run():
        return SelectiveLabelsLoop(improve_mode="both", max_rounds=3, n_applicants=1500, seed=42).run()

    a, b = run(), run()
    assert a.frontier_severity == b.frontier_severity
    assert [round(r.control_metric, 6) for r in a.rounds] == [round(r.control_metric, 6) for r in b.rounds]


def test_frontier_is_in_range_or_none():
    loop = SelectiveLabelsLoop(improve_mode="both", max_rounds=6, n_applicants=2000, seed=42)
    result = loop.run()
    assert result.rounds
    if result.frontier_severity is not None:
        assert config.START_SEVERITY <= result.frontier_severity <= config.MAX_SEVERITY
    # The loop stops at the first failing round (or after probing the max).
    failed = [r for r in result.rounds if not r.passed]
    assert len(failed) <= 1


def test_levermetrics_from_scored_roundtrip():
    cohort = SyntheticBorrowerGenerator(n_applicants=1500, selection_severity=0.5, seed=1).generate_cohort()
    lm = LeverMetrics.from_scored(_scored(cohort))
    assert isinstance(lm.declined_ece, float)
    assert 0.0 <= lm.declined_ece <= 1.0
