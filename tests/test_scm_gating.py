"""Tests for the bank-feed structural switch and DAG topology accessors (cldd.scm).

These cover GAP 2 of the session handoff:
  (a) ``do(has_linked_bank_feed = True/False)`` is a *structural* (information)
      switch — it is NOT refused, it flips the no-feed risk term and yields a
      NON-ZERO mean true effect on a mixed-feed cohort, while preserving exact
      no-op invariance (do(X = each unit's current value) == baseline);
  (b) genuinely non-manipulable identity nodes (sector, vintage_years, ...) are
      still refused (intervenable=False, structural=False, zero effect);
  (c) the public DAG topology accessors are mutually consistent — every child
      lists the node as a parent, and vice-versa.
"""

from __future__ import annotations

import numpy as np

from cldd import dag_children, dag_parents  # exported from cldd package
from cldd.scm import StructuralBorrowerGenerator


def _generator(seed: int = 42, n: int = 3000, severity: float = 1.0):
    return StructuralBorrowerGenerator(
        n_applicants=n, selection_severity=severity, seed=seed
    )


# --------------------------------------------------------------------------- #
# (a) Bank-feed structural switch: manipulable, non-zero effect, no-op exact.
# --------------------------------------------------------------------------- #


def test_bank_feed_switch_is_structural_not_refused():
    """do(has_linked_bank_feed=...) is a structural switch, not a refusal."""
    gen = _generator(seed=13)
    state = gen.generate_cohort()["scm_state"]
    res = gen.do_intervention(state, "has_linked_bank_feed", True)
    # Marked structural; still NOT one of the 16 policy-intervenable features.
    assert res.structural is True
    assert res.intervenable is False


def test_bank_feed_true_nonzero_mean_effect_on_mixed_cohort():
    """do(has_linked_bank_feed=True) on a mixed-feed cohort has non-zero mean effect."""
    gen = _generator(seed=21)
    state = gen.generate_cohort()["scm_state"]
    # Mixed-feed cohort precondition: both linked and unlinked units present.
    assert 0.0 < float(state.has_feed.mean()) < 1.0

    res = gen.do_intervention(state, "has_linked_bank_feed", True)
    assert abs(float(res.effect.mean())) > 1e-6, "feed switch produced ~zero effect"
    # Effect is exactly zero for units whose feed status does NOT flip, and
    # non-zero only for units whose feed status actually flips (no-feed -> feed).
    assert np.max(np.abs(res.effect[state.has_feed])) < 1e-12
    assert np.any(np.abs(res.effect[~state.has_feed]) > 1e-9)
    # Linking a feed removes the no-feed risk penalty => effect is non-positive.
    assert float(res.effect[~state.has_feed].mean()) < 0.0


def test_bank_feed_false_nonzero_mean_effect_on_mixed_cohort():
    """do(has_linked_bank_feed=False) on a mixed-feed cohort has non-zero mean effect."""
    gen = _generator(seed=21)
    state = gen.generate_cohort()["scm_state"]
    res = gen.do_intervention(state, "has_linked_bank_feed", False)
    assert abs(float(res.effect.mean())) > 1e-6
    # Only units that currently HAVE a feed flip to no-feed; the rest are unchanged.
    assert np.max(np.abs(res.effect[~state.has_feed])) < 1e-12
    assert np.any(np.abs(res.effect[state.has_feed]) > 1e-9)
    # Unlinking a feed adds the no-feed risk penalty => effect is non-negative.
    assert float(res.effect[state.has_feed].mean()) > 0.0


def test_bank_feed_switch_modest_information_effect():
    """The feed switch is an information change with a MODEST direct effect."""
    gen = _generator(seed=4)
    state = gen.generate_cohort()["scm_state"]
    res = gen.do_intervention(state, "has_linked_bank_feed", True)
    # Per-unit effect for flipped units is small (a 0.20-logit no-feed term),
    # NOT a fabricated large effect.
    assert np.max(np.abs(res.effect)) < 0.06


def test_bank_feed_noop_invariance_exact():
    """do(has_linked_bank_feed = each unit's current value) is an exact no-op."""
    gen = _generator(seed=7)
    state = gen.generate_cohort()["scm_state"]
    # Per-unit "observed" feed flags (broadcast as a length-n array).
    observed = state.has_feed.astype(float)
    res = gen.do_intervention(state, "has_linked_bank_feed", observed)
    assert res.is_noop
    assert np.max(np.abs(res.effect)) == 0.0
    np.testing.assert_array_equal(res.true_pd, res.baseline_pd)


# --------------------------------------------------------------------------- #
# (b) Identity nodes remain refused (do() ill-defined).
# --------------------------------------------------------------------------- #


def test_identity_nodes_still_refused():
    """sector / geography_region / vintage_years / employee_count_bucket refused."""
    gen = _generator(seed=2)
    state = gen.generate_cohort()["scm_state"]
    for feat in ("sector", "geography_region", "vintage_years",
                 "employee_count_bucket"):
        res = gen.do_intervention(state, feat, 1.0)
        assert res.intervenable is False, f"{feat} should be refused"
        assert res.structural is False, f"{feat} is not a structural switch"
        assert np.max(np.abs(res.effect)) == 0.0, f"{feat} refusal must be zero-effect"
        np.testing.assert_array_equal(res.true_pd, res.baseline_pd)


# --------------------------------------------------------------------------- #
# (c) Public DAG topology accessors are mutually consistent.
# --------------------------------------------------------------------------- #


def test_dag_children_parents_consistent():
    """Every child lists the node as a parent, and every parent edge is a child edge."""
    children = dag_children()
    parents = dag_parents()
    # Classmethod and module-level accessors agree.
    assert children == StructuralBorrowerGenerator.dag_children()
    assert parents == StructuralBorrowerGenerator.dag_parents()

    # child -> parent direction
    for node, kids in children.items():
        for kid in kids:
            assert node in parents.get(kid, []), (
                f"{kid} should list {node} as a parent"
            )
    # parent -> child direction
    for node, ps in parents.items():
        for p in ps:
            assert node in children.get(p, []), (
                f"{p} should list {node} as a child"
            )


def test_dag_parents_inverts_children():
    """dag_parents is the exact edge-inverse of dag_children over the same nodes."""
    children = dag_children()
    parents = dag_parents()
    edges_from_children = {
        (parent, child) for parent, kids in children.items() for child in kids
    }
    edges_from_parents = {
        (parent, child) for child, ps in parents.items() for parent in ps
    }
    assert edges_from_children == edges_from_parents
