"""Exploration lever: stream contract, determinism, default-path neutrality, and
the headline property — bought labels hold calibration where no observational
correction is identified (measured before being asserted; see values inline)."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from cldd import SelectiveLabelsLoop, config, emp
from cldd.correctors import CorrectorContext, ExplorationCorrector


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


@pytest.mark.pinned
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


def _no_train_cohort():
    raise AssertionError("ExplorationCorrector must not need a train cohort")


def _stub_out_unbuilt_emp_reporting(monkeypatch: pytest.MonkeyPatch) -> None:
    """``eval_default.score_pd_detection`` (unconditionally, sibling v2 work
    outside this file's scope) calls ``emp.empc_literature``/``emp.emp_harness``
    for every subgroup with a ``requested_amount`` column -- i.e. always. Those
    two entry points are still ``NotImplementedError`` stubs mid-build
    elsewhere in this fan-out. These tests exercise the corrector's OWN new
    ``exploration_cost`` accounting (this file's scope), not the EMP reporting
    fields, so unblock the shared call site with stand-ins that reproduce the
    exact documented degenerate-input contract (never raise; ``emp_harness``
    returns ``None`` without timing columns) rather than skipping the real
    ``score_pd_detection`` path."""

    def _fake_empc_literature(y_true, scores, params=None):
        return emp.EMPResult(emp=float("nan"), optimal_fraction=float("nan"), n=len(y_true))

    def _fake_emp_harness(y_true, scores, default_day, requested_amount, economics=None):
        return None

    monkeypatch.setattr(emp, "empc_literature", _fake_empc_literature)
    monkeypatch.setattr(emp, "emp_harness", _fake_emp_harness)


def test_exploration_cost_matches_hand_computed_flat_pricing(monkeypatch):
    """Miniature hand-built FLAT cohort (no ``days_to_default`` key, so the v2
    flat pricing convention applies -- see ``correctors._exploration_cost``):
    forces every decline to be explored via ``exploration_rate=1.0``
    (``rng.random()`` draws land in [0, 1), so ``< 1.0`` is always true --
    the explored mask is exactly ``~approved``, deterministic regardless of
    the RNG stream) and hand-computes the expected ``exploration_cost`` from
    the flat convention (defaults: profit = -A; goods: profit = A*(f+r_term)).

    Cohort (10 rows, 3 approved / 7 declined-and-explored):
      approved      = [T, T, T, F, F, F, F, F, F, F]
      true_default  = [0, 1, 0, 0, 0, 1, 0, 1, 0, 0]
      requested_amt = [10000, 11000, 12000, 13000, 14000, 15000, 16000,
                        17000, 18000, 19000]

    Explored (declined) rows are indices 3..9: defaults at idx 5 (A=15000)
    and idx 7 (A=17000) -> sum_default = 32000; goods at idx 3,4,6,8,9
    (A = 13000+14000+16000+18000+19000) -> sum_good = 80000.

    Hand computation (f=config.ORIGINATION_FEE_RATE, r_term=APR*TERM_DAYS/365):
      exploration_cost = sum_default - sum_good * (f + r_term)
                        = 32000 - 80000 * (0.03 + 21/365)
    """
    _stub_out_unbuilt_emp_reporting(monkeypatch)
    approved = np.array([True, True, True, False, False, False, False, False, False, False])
    true_default = np.array([0, 1, 0, 0, 0, 1, 0, 1, 0, 0])
    requested_amount = np.array(
        [10000.0, 11000.0, 12000.0, 13000.0, 14000.0, 15000.0, 16000.0, 17000.0, 18000.0, 19000.0]
    )
    cohort = {
        "features": pd.DataFrame({"requested_amount": requested_amount}),
        "true_default": true_default,
        "approved": approved,
    }
    ctx = CorrectorContext(
        seed=42,
        policy_threshold=config.POLICY_PD_THRESHOLD,
        severity=0.0,
        iteration=0,
        exploration_rate=1.0,  # forces explored == ~approved, deterministically
        make_train_cohort=_no_train_cohort,
    )
    outcome = ExplorationCorrector().apply(cohort, ctx)

    explored = ~approved
    assert outcome.info["n_explored"] == int(explored.sum()) == 7
    assert outcome.info["explored_defaults"] == 2

    f = config.ORIGINATION_FEE_RATE
    r_term = config.APR * config.TERM_DAYS / 365.0
    sum_good = float(requested_amount[explored & (true_default == 0)].sum())
    sum_default = float(requested_amount[explored & (true_default == 1)].sum())
    expected_cost = sum_default - sum_good * (f + r_term)
    assert outcome.info["exploration_cost"] == pytest.approx(expected_cost, abs=1e-9)
    assert outcome.info["exploration_cost"] > 0  # net cost here (losses outweigh explored returns)


def test_exploration_cost_zero_when_exploration_off(monkeypatch):
    """``exploration_rate=0.0`` explores nothing (``rng.random() < 0.0`` is
    never true) -> ``exploration_cost`` must be exactly ``0.0``, the guard
    path in ``correctors._exploration_cost``, not a coincidental zero sum."""
    _stub_out_unbuilt_emp_reporting(monkeypatch)
    approved = np.array([True, True, False])
    true_default = np.array([0, 1, 0])
    requested_amount = np.array([10000.0, 20000.0, 30000.0])
    cohort = {
        "features": pd.DataFrame({"requested_amount": requested_amount}),
        "true_default": true_default,
        "approved": approved,
    }
    ctx = CorrectorContext(
        seed=42,
        policy_threshold=config.POLICY_PD_THRESHOLD,
        severity=0.0,
        iteration=0,
        exploration_rate=0.0,
        make_train_cohort=_no_train_cohort,
    )
    outcome = ExplorationCorrector().apply(cohort, ctx)
    assert outcome.info["n_explored"] == 0
    assert outcome.info["exploration_cost"] == 0.0
