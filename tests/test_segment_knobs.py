"""Option C knob tests: ``selection_policy`` on both generators.

Identity tests are IN-PROCESS DIFFERENTIALS (default vs explicit default in the
same process) -- no stored float constants, so they are NOT ``pinned``.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from cldd.loop import SelectiveLabelsLoop, make_generator
from cldd.scm import StructuralBorrowerGenerator
from cldd.selection import SegmentedSelection, knockout_rates
from cldd.synthetic import SyntheticBorrowerGenerator

GENERATORS = {"flat": SyntheticBorrowerGenerator, "scm": StructuralBorrowerGenerator}
KNOCKOUT = SegmentedSelection("vintage_years", knockout_rates(1.0, 0.6), knockout_end="low")
UNIFORM = SegmentedSelection("vintage_years", knockout_rates(0.0, 0.6), knockout_end="low")


def _cohort(world, policy=None, seed=7, n=1000):
    return GENERATORS[world](
        n_applicants=n, selection_severity=0.4, seed=seed, selection_policy=policy
    ).generate_cohort()


def _round_tuple(r):
    return (
        r.iteration, r.selection_severity, r.base_rate, r.approval_rate,
        r.naive.declined_ece,
        r.reweight.declined_ece if r.reweight is not None else None,
        r.retrain.declined_ece if r.retrain is not None else None,
        r.control_metric,
    )


def _run(world, generator_kwargs=None, seed=42, n=800):
    return SelectiveLabelsLoop(
        improve_mode="both", max_rounds=1, n_applicants=n, seed=seed,
        generator=world, generator_kwargs=generator_kwargs,
    ).run()


@pytest.mark.parametrize("world", ["flat", "scm"])
def test_explicit_none_policy_is_identical_to_default(world):
    base = _run(world)
    knob = _run(world, generator_kwargs={"selection_policy": None})
    assert [_round_tuple(r) for r in base.rounds] == [_round_tuple(r) for r in knob.rounds]
    assert base.frontier_severity == knob.frontier_severity


@pytest.mark.parametrize("world", ["flat", "scm"])
def test_default_cohort_carries_no_policy_keys(world):
    cohort = _cohort(world)
    assert "segment" not in cohort
    assert "selection_policy" not in cohort["ground_truth"]


@pytest.mark.parametrize("world", ["flat", "scm"])
def test_policy_moves_only_the_funding_mask(world):
    """Isolation + non-vacuity: same seed, same world -- the policy reaches the
    funding mask and nothing else."""
    base = _cohort(world)
    seg = _cohort(world, policy=KNOCKOUT)
    pd.testing.assert_frame_equal(base["features"], seg["features"])
    assert np.array_equal(base["true_default"], seg["true_default"])
    assert np.array_equal(base["prior_score"], seg["prior_score"])
    assert not np.array_equal(base["approved"], seg["approved"])


@pytest.mark.parametrize("world", ["flat", "scm"])
def test_knockout_declines_the_whole_segment_and_keeps_the_rate(world):
    cohort = _cohort(world, policy=KNOCKOUT)
    segment, approved = cohort["segment"], cohort["approved"]
    assert approved[segment == 0].sum() == 0
    assert approved.mean() == pytest.approx(0.6, abs=0.005)
    assert cohort["ground_truth"]["approval_rate"] == float(approved.mean())
    assert cohort["ground_truth"]["selection_policy"] == KNOCKOUT.as_dict()
    # the knocked-out segment is the LOW end of the feature
    vintage = cohort["features"]["vintage_years"].to_numpy()
    assert vintage[segment == 0].max() <= vintage[segment != 0].min()


@pytest.mark.parametrize("world", ["flat", "scm"])
def test_uniform_policy_recuts_within_segments(world):
    """Depth 0 is NOT the legacy path: same rate everywhere, but the cutoff is
    taken inside each segment. It is the re-cut control the floors are built on."""
    base = _cohort(world)
    uni = _cohort(world, policy=UNIFORM)
    for k in range(5):
        assert uni["approved"][uni["segment"] == k].mean() == pytest.approx(0.6, abs=0.01)
    assert not np.array_equal(base["approved"], uni["approved"])


@pytest.mark.parametrize("world", ["flat", "scm"])
def test_constructor_rejects_gated_and_rate_breaking_policies(world):
    cls = GENERATORS[world]
    with pytest.raises(ValueError, match="structurally missing"):
        cls(selection_policy=SegmentedSelection("payroll_regularity_score", KNOCKOUT.rates))
    with pytest.raises(ValueError, match="preserve the overall"):
        cls(selection_policy=SegmentedSelection("vintage_years", (0.0, 0.5)))
    with pytest.raises(ValueError, match="not an observed"):
        cls(selection_policy=SegmentedSelection("no_such_column", KNOCKOUT.rates))


def test_make_generator_forwards_the_policy():
    gen = make_generator(
        "scm", severity=0.4, seed=7, n_applicants=100, approval_rate=0.6,
        selection_policy=KNOCKOUT,
    )
    assert gen.selection_policy is KNOCKOUT
    assert gen.independent_selection_noise is True  # scm loop path untouched


@pytest.mark.parametrize("world", ["flat", "scm"])
def test_policy_reaches_the_loop(world):
    base = _run(world)
    seg = _run(world, generator_kwargs={"selection_policy": KNOCKOUT})
    assert _round_tuple(base.rounds[0]) != _round_tuple(seg.rounds[0])
    assert seg.rounds[0].approval_rate == pytest.approx(0.6, abs=0.005)
