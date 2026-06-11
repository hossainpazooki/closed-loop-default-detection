"""Observable positivity diagnostics: determinism, degenerate cases, and the
regime separation they were calibrated for (see config.DIAG_* notes).

The thresholds are calibrated at n=4000 — the in-sample propensity AUC inflates
at smaller n (GBT overfit on fewer rows), so the "healthy" assertions here run
at the calibration scale on purpose.
"""

from __future__ import annotations

import math

import numpy as np

from cldd.diagnostics import positivity_diagnostics
from cldd.synthetic import SyntheticBorrowerGenerator


def _flat_cohort(severity: float, n: int = 4000, seed: int = 42):
    c = SyntheticBorrowerGenerator(
        n_applicants=n, selection_severity=severity, seed=seed
    ).generate_cohort()
    return c["features"].to_numpy(dtype=float), c["approved"]


def test_diagnostics_deterministic():
    X, approved = _flat_cohort(0.4, n=1500)
    a = positivity_diagnostics(X, approved, random_state=42)
    b = positivity_diagnostics(X, approved, random_state=42)
    assert a == b


def test_degenerate_selection_abstains():
    """All-funded (or none) leaves nothing to compare — flag, don't guess."""
    X, _ = _flat_cohort(0.0, n=500)
    d = positivity_diagnostics(X, np.ones(len(X), dtype=bool), random_state=42)
    assert d.flagged
    assert math.isnan(d.propensity_auc)


def test_healthy_selection_not_flagged():
    """Inside the measured frontier (severity <= 0.4) the flag stays quiet."""
    for severity in (0.0, 0.4):
        X, approved = _flat_cohort(severity)
        d = positivity_diagnostics(X, approved, random_state=42)
        assert not d.flagged, (severity, d)
        assert d.ess_ratio > 0.875
        assert d.unfunded_below_floor <= 0.01


def test_broken_selection_flagged():
    """Beyond the frontier (severity >= 0.6) every component deteriorates and
    the flag fires — the observable counterpart of the hidden ECE failure."""
    healthy = positivity_diagnostics(*_flat_cohort(0.4), random_state=42)
    for severity in (0.6, 1.0):
        X, approved = _flat_cohort(severity)
        d = positivity_diagnostics(X, approved, random_state=42)
        assert d.flagged, (severity, d)
        assert d.propensity_auc > healthy.propensity_auc
        assert d.ess_ratio < healthy.ess_ratio
        assert d.unfunded_below_floor > healthy.unfunded_below_floor


def test_deterministic_policy_is_worst_case():
    """Selection that is a function of the features (what a deployed model does)
    destroys positivity by construction; the diagnostics must scream."""
    X, _ = _flat_cohort(0.0, n=2000)
    funded = X[:, 0] < np.median(X[:, 0])
    d = positivity_diagnostics(X, funded, random_state=42)
    assert d.flagged
    assert d.propensity_auc > 0.99
    assert d.unfunded_below_floor > 0.9
