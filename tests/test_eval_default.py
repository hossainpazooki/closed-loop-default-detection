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
    evaluate_naive,
    expected_calibration_error,
    fit_observed_model,
    score_pd_detection,
)
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
