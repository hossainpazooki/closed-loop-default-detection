"""Unit tests for cldd.selection (Option C policy primitives).

Closed-form checks over constructed arrays; no model fit, no stored floats,
so NOT ``pinned``.
"""
from __future__ import annotations

import numpy as np
import pytest

from cldd.selection import (
    SegmentedSelection,
    apply_segmented,
    knockout_rates,
    segment_index,
    validate_policy,
)


def test_knockout_rates_preserve_the_overall_rate():
    for depth in (0.0, 0.25, 0.5, 1.0):
        rates = knockout_rates(depth, approval_rate=0.6, n_segments=5)
        assert len(rates) == 5
        assert np.mean(rates) == pytest.approx(0.6, abs=1e-12)


def test_knockout_rates_endpoints():
    assert knockout_rates(0.0, 0.6) == (0.6, 0.6, 0.6, 0.6, 0.6)
    full = knockout_rates(1.0, 0.6)
    assert full[0] == 0.0
    assert full[1:] == pytest.approx((0.75, 0.75, 0.75, 0.75))


def test_knockout_rates_rejects_infeasible_depth():
    # approval 0.9, 5 segments: a full knockout needs the rest at 1.125
    with pytest.raises(ValueError):
        knockout_rates(1.0, approval_rate=0.9, n_segments=5)


def test_policy_validates_its_fields():
    with pytest.raises(ValueError):
        SegmentedSelection("vintage_years", (0.6,))
    with pytest.raises(ValueError):
        SegmentedSelection("vintage_years", (1.2, 0.0))
    with pytest.raises(ValueError):
        SegmentedSelection("vintage_years", (0.6, 0.6), knockout_end="middle")


def test_validate_policy_rejects_unknown_gated_and_rate_breaking():
    ok = SegmentedSelection("vintage_years", knockout_rates(1.0, 0.6))
    kw = dict(approval_rate=0.6, allowed_features=["vintage_years", "payroll"],
              gated_features=["payroll"])
    validate_policy(ok, **kw)  # does not raise
    with pytest.raises(ValueError, match="not an observed"):
        validate_policy(SegmentedSelection("nope", ok.rates), **kw)
    with pytest.raises(ValueError, match="structurally missing"):
        validate_policy(SegmentedSelection("payroll", ok.rates), **kw)
    with pytest.raises(ValueError, match="preserve the overall"):
        validate_policy(SegmentedSelection("vintage_years", (0.0, 0.5)), **kw)


def test_segment_index_is_equal_mass_and_ordered():
    values = np.array([5.0, 1.0, 4.0, 2.0, 3.0, 9.0, 8.0, 7.0, 6.0, 0.0])
    seg = segment_index(values, n_segments=5, knockout_end="low")
    assert np.bincount(seg).tolist() == [2, 2, 2, 2, 2]
    assert set(values[seg == 0]) == {0.0, 1.0}      # smallest values
    assert set(values[seg == 4]) == {8.0, 9.0}
    high = segment_index(values, n_segments=5, knockout_end="high")
    assert set(values[high == 0]) == {8.0, 9.0}     # largest values


def test_segment_index_breaks_ties_by_row_order():
    seg = segment_index(np.zeros(6), n_segments=3)
    assert seg.tolist() == [0, 0, 1, 1, 2, 2]


def test_segment_index_rejects_missing_values():
    with pytest.raises(ValueError, match="missing"):
        segment_index(np.array([1.0, np.nan, 2.0]), n_segments=2)


def test_apply_segmented_knockout_and_full_funding():
    score = np.arange(10, dtype=float)
    seg = np.array([0] * 5 + [1] * 5)
    approved = apply_segmented(score, seg, rates=(0.0, 1.0))
    assert approved.tolist() == [False] * 5 + [True] * 5


def test_apply_segmented_funds_lowest_scores_within_each_segment():
    rng = np.random.Generator(np.random.PCG64(7))
    score = rng.standard_normal(1000)
    seg = segment_index(rng.standard_normal(1000), n_segments=5)
    rates = knockout_rates(0.5, 0.6)
    approved = apply_segmented(score, seg, rates)
    for k, rate in enumerate(rates):
        in_seg = seg == k
        assert approved[in_seg].mean() == pytest.approx(rate, abs=0.01)
        # every funded row scores no higher than every declined row in its segment
        assert score[in_seg & approved].max() <= score[in_seg & ~approved].min()
    assert approved.mean() == pytest.approx(0.6, abs=0.005)
