"""Tests for the synthetic SMB cohort generator (the generate stage)."""

from __future__ import annotations

import numpy as np
import pandas as pd

from cldd.synthetic import BANK_FEED_COLUMNS, FEATURE_COLUMNS, SyntheticBorrowerGenerator


def _cohort(severity: float, seed: int = 42, n: int = 3000) -> dict:
    return SyntheticBorrowerGenerator(n_applicants=n, selection_severity=severity, seed=seed).generate_cohort()


def test_determinism_same_seed_identical_cohort():
    a = _cohort(0.6, seed=7)
    b = _cohort(0.6, seed=7)
    pd.testing.assert_frame_equal(a["features"], b["features"])
    np.testing.assert_array_equal(a["true_default"], b["true_default"])
    np.testing.assert_array_equal(a["approved"], b["approved"])
    np.testing.assert_allclose(a["prior_score"], b["prior_score"])


def test_different_seed_differs():
    a = _cohort(0.6, seed=7)
    b = _cohort(0.6, seed=8)
    assert not np.array_equal(a["true_default"], b["true_default"])


def test_schema_and_structural_missingness():
    c = _cohort(0.5)
    df = c["features"]
    assert list(df.columns) == FEATURE_COLUMNS
    has_feed = df["has_linked_bank_feed"] > 0.5
    # Bank-feed columns are NaN exactly where no feed is linked.
    for col in BANK_FEED_COLUMNS:
        assert df.loc[~has_feed, col].isna().all()
        assert df.loc[has_feed, col].notna().all()


def test_base_rate_near_target():
    c = _cohort(0.5)
    assert 0.10 <= c["ground_truth"]["base_rate"] <= 0.25


def test_approval_rate_honored():
    c = _cohort(0.7, n=4000)
    # Lowest-risk ~60% funded (quantile cut => close to the requested fraction).
    assert abs(c["ground_truth"]["approval_rate"] - 0.60) < 0.03


def test_severity_widens_selective_label_gap():
    """Higher severity => declined pool is riskier than the approved pool."""

    def approved_vs_declined_gap(severity: float) -> float:
        c = _cohort(severity, n=5000)
        y = c["true_default"]
        approved = c["approved"]
        decline_rate = y[~approved].mean()
        approve_rate = y[approved].mean()
        return float(decline_rate - approve_rate)

    gap_low = approved_vs_declined_gap(0.0)
    gap_high = approved_vs_declined_gap(1.0)

    # At severity 0 selection is random: gap ~ 0. At severity 1 declines are the
    # high-risk tail: gap strongly positive and much larger.
    assert abs(gap_low) < 0.05
    assert gap_high > 0.10
    assert gap_high > gap_low + 0.08
