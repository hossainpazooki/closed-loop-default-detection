"""Exploration lever: stream contract, determinism, default-path neutrality, and
the headline property — bought labels hold calibration where no observational
correction is identified (measured before being asserted; see values inline)."""

from __future__ import annotations

import numpy as np
import pytest

from cldd import SelectiveLabelsLoop, config


def test_invalid_exploration_rate_rejected():
    with pytest.raises(ValueError, match="exploration_rate"):
        SelectiveLabelsLoop(exploration_rate=1.0)
    with pytest.raises(ValueError, match="exploration_rate"):
        SelectiveLabelsLoop(exploration_rate=-0.1)


def test_default_path_has_no_explore_lever():
    """exploration_rate=0 (the default) must leave the lever off and control on
    the reweight lever — the committed artifacts' behavior. (The exact frozen
    flat baseline is separately enforced in test_loop_scm.)"""
    result = SelectiveLabelsLoop(
        improve_mode="both", max_rounds=1, n_applicants=1000, seed=42
    ).run()
    r = result.rounds[0]
    assert r.explore is None
    assert r.n_explored == 0 and r.explored_defaults == 0
    assert r.control_metric == r.reweight.declined_ece
    assert result.exploration_rate == 0.0
    # Diagnostics ride along on every round, observable-only.
    assert r.diagnostics is not None
    assert 0.0 <= r.diagnostics.propensity_auc <= 1.0


def test_explore_lever_deterministic_and_documented_stream():
    """Two runs agree exactly, and the explored count is reproducible from the
    documented RNG stream [seed, iteration, EXPLORE_STREAM_LOOP]."""

    def run():
        return SelectiveLabelsLoop(
            improve_mode="reweight",
            max_rounds=1,
            n_applicants=2000,
            seed=42,
            exploration_rate=0.1,
        ).run()

    a, b = run(), run()
    ra, rb = a.rounds[0], b.rounds[0]
    assert ra.explore.declined_ece == rb.explore.declined_ece
    assert ra.n_explored == rb.n_explored
    assert ra.control_metric == ra.explore.declined_ece  # explore drives control

    # Reconstruct the explored draw from the documented stream contract.
    cohort = SelectiveLabelsLoop(
        improve_mode="reweight", max_rounds=1, n_applicants=2000, seed=42
    )._generate(0.0, 0)
    rng = np.random.default_rng([42, 0, config.EXPLORE_STREAM_LOOP])
    explored = (~cohort["approved"]) & (rng.random(2000) < 0.1)
    assert int(explored.sum()) == ra.n_explored


def test_exploration_holds_calibration_beyond_the_ipw_frontier():
    """THE lesson-driven property: at severity 0.6 — past the certified frontier,
    where the unobserved confounder defeats fitted-propensity IPW — exact-weight
    exploration still calibrates the declined cohort.

    Measured (scm, n=2500, seed 42, one round at severity 0.6):
    IPW declined-ECE 0.2816 vs exploration 0.0970 with 91 bought labels
    (38 of which defaulted — the explicit price of identification).
    """
    loop = SelectiveLabelsLoop(
        improve_mode="reweight",
        generator="scm",
        seed=42,
        n_applicants=2500,
        start_severity=0.6,
        max_rounds=1,
        exploration_rate=0.10,
    )
    r = loop.run().rounds[0]
    assert r.reweight.declined_ece > 0.2          # observational correction is lost
    assert r.explore.declined_ece < 0.15          # bought labels still calibrate
    assert r.explore.declined_ece < r.reweight.declined_ece / 2
    assert r.n_explored > 0
    # The cost is real and visible: explored declines default far above the book.
    assert r.explored_defaults / r.n_explored > config.TARGET_BASE_DEFAULT_RATE
