"""Focused regression tests for the measure stage (``cldd.eval_default``).

The pure-numpy metric logic (ECE) is asserted on hand-built inputs and is exact and
version-independent; the sklearn-backed pieces use a small seeded synthetic cohort and
assert behavioral properties (subgroup partitioning, mask overrides, PASS/FAIL wiring)
rather than frozen floats. Nothing here is marked ``pinned``.
"""

from __future__ import annotations

import numpy as np

from cldd import CalibratedPDModel, config
from cldd.eval_default import (
    PdDetectionResult,
    _f1_at_approval_fraction,
    evaluate_naive,
    expected_calibration_error,
    fit_observed_model,
    score_pd_detection,
)
from cldd.scm import StructuralBorrowerGenerator
from cldd.synthetic import SyntheticBorrowerGenerator


# --- pure-numpy ECE (exact, version-independent) --------------------------- #


def test_ece_perfectly_calibrated_is_zero():
    y = np.array([0, 0, 1, 1])
    assert expected_calibration_error(y, y.astype(float)) == 0.0


def test_ece_fully_miscalibrated_known_value():
    # all predictions 0.0 while half the labels are 1 -> single bin, |0.5 - 0.0| = 0.5.
    y = np.array([0, 0, 1, 1])
    p = np.zeros(4)
    assert expected_calibration_error(y, p) == 0.5


def test_ece_empty_is_nan():
    assert np.isnan(expected_calibration_error(np.array([]), np.array([])))


# --- sklearn-backed measure stage (behavioral, seeded) --------------------- #


def _cohort(severity=0.4, n=1500, seed=42):
    return SyntheticBorrowerGenerator(
        n_applicants=n, selection_severity=severity, seed=seed
    ).generate_cohort()


def test_score_pd_detection_subgroups_partition_the_cohort():
    cohort = _cohort()
    model = fit_observed_model(cohort, random_state=42)
    scored = score_pd_detection(model, cohort)
    assert {"all", "approved", "declined", "predictions"} <= set(scored)
    n = scored["all"].n
    assert scored["approved"].n + scored["declined"].n == n
    assert scored["predictions"].shape == (n,)
    assert np.all((scored["predictions"] >= 0.0) & (scored["predictions"] <= 1.0))


def test_fit_observed_model_returns_detector_and_accepts_approved_weights():
    cohort = _cohort()
    model = fit_observed_model(cohort, random_state=42)
    assert isinstance(model, CalibratedPDModel)
    n_approved = int(cohort["approved"].sum())
    weighted = fit_observed_model(
        cohort, sample_weight=np.ones(n_approved), random_state=42
    )
    assert isinstance(weighted, CalibratedPDModel)


def test_funded_override_empties_the_declined_subgroup():
    cohort = _cohort()
    model = fit_observed_model(cohort, random_state=42)
    n = len(cohort["true_default"])
    scored = score_pd_detection(model, cohort, funded=np.ones(n, dtype=bool))
    assert scored["declined"].n == 0
    assert scored["approved"].n == n


def test_evaluate_naive_pass_fail_tracks_declined_ece():
    cohort = _cohort()
    res = evaluate_naive(cohort)
    assert isinstance(res, PdDetectionResult)
    assert res.name == "pd_default_detection"
    assert res.score == res.details["declined"].ece
    assert res.passed == (res.score <= config.TARGET_DECLINED_ECE)


# --- EMP wiring (v2 measurement axis) --------------------------------------- #


def _scm_cohort(severity=1.0, n=1500, seed=42):
    return StructuralBorrowerGenerator(
        n_applicants=n, selection_severity=severity, seed=seed
    ).generate_cohort()


def test_flat_cohort_empc_filled_emp_h_none():
    """Flat generator plants no default timing: empc is priced, emp_h stays None."""
    cohort = _cohort()
    assert "days_to_default" not in cohort
    model = fit_observed_model(cohort, random_state=42)
    scored = score_pd_detection(model, cohort)
    for key in ("all", "approved", "declined"):
        m = scored[key]
        assert isinstance(m.empc, float)
        assert m.emp_h is None
        assert m.emp_h_fraction is None
    # 'all' is large and mixed-class: empc/empc_fraction/f1_emp_cutoff are non-degenerate.
    assert np.isfinite(scored["all"].empc)
    assert scored["all"].empc_fraction is not None
    assert 0.0 <= scored["all"].empc_fraction <= 1.0
    assert scored["all"].f1_emp_cutoff is not None
    assert np.isfinite(scored["all"].f1_emp_cutoff)


def test_scm_cohort_empc_and_emp_h_both_filled():
    """SCM cohorts carry planted default timing: both EMP variants price the pool."""
    cohort = _scm_cohort()
    assert "days_to_default" in cohort
    model = fit_observed_model(cohort, random_state=42)
    scored = score_pd_detection(model, cohort)
    m = scored["all"]
    assert isinstance(m.empc, float) and np.isfinite(m.empc)
    assert m.empc_fraction is not None
    assert isinstance(m.emp_h, float) and np.isfinite(m.emp_h)
    assert m.emp_h_fraction is not None
    assert 0.0 <= m.emp_h_fraction <= 1.0


def test_f1_at_approval_fraction_matches_brute_force_scan():
    """Order-statistic F1 helper agrees with an independent per-row brute-force scan."""
    y = np.array([1, 0, 1, 0, 1, 0, 0, 1, 1, 0])
    scores = np.array([0.9, 0.1, 0.8, 0.4, 0.95, 0.05, 0.2, 0.7, 0.6, 0.3])
    n = len(y)
    for fraction in (0.0, 0.2, 0.35, 0.5, 0.7, 0.85, 1.0):
        result = _f1_at_approval_fraction(y, scores, fraction)

        n_approved = int(round(fraction * n))
        n_approved = min(max(n_approved, 0), n)
        # independent (non-vectorized) stable-sort brute force over approval counts
        order = sorted(range(n), key=lambda i: (scores[i], i))
        approved = set(order[:n_approved])
        tp = fp = fn = 0
        for i in range(n):
            pred_i = 0 if i in approved else 1
            if pred_i == 1 and y[i] == 1:
                tp += 1
            elif pred_i == 1 and y[i] == 0:
                fp += 1
            elif pred_i == 0 and y[i] == 1:
                fn += 1
        precision = tp / (tp + fp) if (tp + fp) else 0.0
        recall = tp / (tp + fn) if (tp + fn) else 0.0
        brute_f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
        assert abs(result - brute_f1) < 1e-12


def test_empc_fraction_nan_guarded_to_none(monkeypatch):
    """A degenerate (nan) EMPC optimal_fraction is guarded to None, not stored as nan."""
    from cldd import emp as emp_module

    cohort = _cohort()
    model = fit_observed_model(cohort, random_state=42)

    def fake_empc_literature(y_true, scores, params=None):
        return emp_module.EMPResult(emp=0.05, optimal_fraction=float("nan"), n=len(y_true))

    monkeypatch.setattr(emp_module, "empc_literature", fake_empc_literature)
    scored = score_pd_detection(model, cohort)
    m = scored["all"]
    assert m.empc == 0.05
    assert m.empc_fraction is None
    assert m.f1_emp_cutoff is None


def test_existing_fields_unchanged_by_emp_wiring():
    """EMP additions are strictly appended: pre-existing fields match a pre-wiring call."""
    from cldd import model_pd
    from cldd.eval_default import _subgroup_metrics

    cohort = _cohort()
    model = fit_observed_model(cohort, random_state=42)
    scored = score_pd_detection(model, cohort)

    X = cohort["features"].to_numpy(dtype=float)
    p = model_pd.predict_pd(model, X)
    y = cohort["true_default"]
    declined = ~cohort["approved"]
    # Pre-wiring call: no default_day/requested_amount, exactly the v1 call shape.
    pre = _subgroup_metrics(y[declined], p[declined], config.POLICY_PD_THRESHOLD)
    post = scored["declined"]

    assert post.n == pre.n
    assert post.base_rate == pre.base_rate
    assert post.mean_pd == pre.mean_pd
    assert post.auc == pre.auc or (np.isnan(post.auc) and np.isnan(pre.auc))
    assert post.brier == pre.brier or (np.isnan(post.brier) and np.isnan(pre.brier))
    assert post.ece == pre.ece
    assert post.f1 == pre.f1
    # Pre-wiring call never touches EMP fields.
    assert pre.empc is None
    assert pre.emp_h is None
