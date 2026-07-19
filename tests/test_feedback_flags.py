"""v3 FeedbackLoop flags: ``retrain`` (frozen arm), ``policy_mode`` (prior arm),
and the default-path byte-identity regression (spec section 7 bullets 2-3).

Spec: docs/superpowers/specs/2026-07-14-cldd-v3-design.md (Rev 2), section 1.2.
"""

from __future__ import annotations

import hashlib
import json

import pytest

import cldd.model_pd as model_pd_mod
from cldd import FeedbackLoop, config
from cldd.loop import make_generator


def test_invalid_policy_mode_raises():
    with pytest.raises(ValueError, match="policy_mode"):
        FeedbackLoop(policy_mode="bogus")


def test_frozen_arm_trains_exactly_once(monkeypatch):
    """retrain=False: the generation-0 model is the only model ever trained,
    across every subsequent generation, regardless of exploration."""
    calls = {"n": 0}
    original = model_pd_mod.train_pd_model

    def counting_train(*args, **kwargs):
        calls["n"] += 1
        return original(*args, **kwargs)

    monkeypatch.setattr(model_pd_mod, "train_pd_model", counting_train)

    res = FeedbackLoop(
        selection_severity=0.4,
        n_generations=4,
        exploration_rate=0.05,
        generator="scm",
        n_applicants=600,
        seed=7,
        retrain=False,
    ).run()

    assert calls["n"] == 1
    assert len(res.generations) == 4
    # policy label semantics are unchanged: gen 0 "prior", gen>=1 "model",
    # even though the SAME model (never retrained) makes every decision.
    assert [g.policy for g in res.generations] == ["prior", "model", "model", "model"]
    # Exploration is suppressed at generation 0 only (gen-0 training must be
    # eps-invariant for the H4 identity) but resumes from generation 1.
    assert res.generations[0].n_explored == 0
    assert all(g.n_explored > 0 for g in res.generations[1:])


def test_frozen_arm_zero_calls_is_not_possible_n_generations_one(monkeypatch):
    """Edge case: even a single-generation frozen run still trains once (the
    generation-0 model always trains -- ``retrain`` only gates generations
    >= 1)."""
    calls = {"n": 0}
    original = model_pd_mod.train_pd_model

    def counting_train(*args, **kwargs):
        calls["n"] += 1
        return original(*args, **kwargs)

    monkeypatch.setattr(model_pd_mod, "train_pd_model", counting_train)

    FeedbackLoop(
        selection_severity=0.4,
        n_generations=1,
        exploration_rate=0.0,
        generator="scm",
        n_applicants=400,
        seed=11,
        retrain=False,
    ).run()
    assert calls["n"] == 1


def test_prior_arm_funds_via_cohort_approved_every_generation():
    """policy_mode='prior': funding equals the cohort's own prior-policy
    ``approved`` column at EVERY generation (not just generation 0), even
    though a model still trains each generation for its metrics.

    Reconstructs each generation's cohort independently via the same
    ``make_generator`` call the loop uses internally (seed + generation) --
    generator determinism (CLAUDE.md invariant) makes this a valid oracle.
    """
    seed = 13
    n_generations = 4
    n_applicants = 600

    res = FeedbackLoop(
        selection_severity=0.4,
        n_generations=n_generations,
        exploration_rate=0.0,  # isolate funding == approved (no explore mixing in)
        generator="scm",
        n_applicants=n_applicants,
        seed=seed,
        policy_mode="prior",
    ).run()

    assert [g.policy for g in res.generations] == ["prior", "model", "model", "model"]

    for generation, g in enumerate(res.generations):
        cohort = make_generator(
            "scm",
            severity=0.4,
            seed=seed + generation,
            n_applicants=n_applicants,
            approval_rate=config.DEFAULT_APPROVAL_RATE,
        ).generate_cohort()
        expected_funded = cohort["approved"]
        expected_rate = float(expected_funded.mean())
        expected_default_rate = float(cohort["true_default"][expected_funded].mean())

        assert g.funded_rate == pytest.approx(expected_rate)
        assert g.funded_default_rate == pytest.approx(expected_default_rate)


def test_prior_arm_default_path_untouched():
    """policy_mode='prior' with retrain=True still trains every generation
    (only the funding decision is diverted, per spec section 1.2)."""
    seed = 17
    res = FeedbackLoop(
        selection_severity=0.4,
        n_generations=3,
        exploration_rate=0.0,
        generator="scm",
        n_applicants=500,
        seed=seed,
        policy_mode="prior",
        retrain=True,
    ).run()
    # metrics is populated for every generation (i.e. a model was trained and
    # scored each time -- prior-mode does not skip metric computation).
    for g in res.generations:
        assert g.metrics is not None
        assert g.funded_rate == pytest.approx(0.6, abs=0.02)


# --------------------------------------------------------------------------- #
# Default-path byte-identity regression (spec section 7 bullet, hard gate #1).
# --------------------------------------------------------------------------- #


def _serialize_v1_fields(res) -> list[dict]:
    """Serialize only the pre-v3 GenerationResult fields -- excludes
    ``book_profit``/``explored_profit`` so this function is valid against both
    the pre-v3 and post-v3 ``GenerationResult`` shape."""
    rows = []
    for g in res.generations:
        rows.append(
            {
                "generation": g.generation,
                "policy": g.policy,
                "funded_rate": g.funded_rate,
                "funded_default_rate": g.funded_default_rate,
                "n_explored": g.n_explored,
                "explored_defaults": g.explored_defaults,
                "metrics": {
                    "declined_ece": g.metrics.declined_ece,
                    "declined_auc": g.metrics.declined_auc,
                    "declined_brier": g.metrics.declined_brier,
                    "declined_mean_pd": g.metrics.declined_mean_pd,
                    "declined_base_rate": g.metrics.declined_base_rate,
                    "declined_f1": g.metrics.declined_f1,
                    "all_ece": g.metrics.all_ece,
                },
                "diagnostics": {
                    "propensity_auc": g.diagnostics.propensity_auc,
                    "ess_ratio": g.diagnostics.ess_ratio,
                    "unfunded_below_floor": g.diagnostics.unfunded_below_floor,
                    "flagged": g.diagnostics.flagged,
                },
            }
        )
    return rows


def _hash_v1_fields(res) -> str:
    blob = json.dumps(_serialize_v1_fields(res), sort_keys=True).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()


# Derived 2026-07-18: ran FeedbackLoop(selection_severity=0.4, n_generations=4,
# exploration_rate=0.05, generator="scm", n_applicants=1000, seed=42).run()
# (default retrain/policy_mode) against (a) a scratch copy of src/cldd with
# feedback.py and emp.py replaced by `git show HEAD:...` at commit da81c98
# (pre-v3, before this session's changes) and (b) the current post-v3
# src/cldd, both under the pinned venv (scikit-learn==1.9.0, numpy==2.4.6).
# Both runs produced this identical sha256 of _serialize_v1_fields' output --
# confirms the default path (retrain=True, policy_mode="model") is
# byte-identical pre/post v3.
EXPECTED_DEFAULT_PATH_SHA256 = "e8f0d3c4d1e338eb25876c02fd3b94c813e3cc12d8ce7cb6993590f867eafbc4"


def test_default_path_byte_identity_regression():
    res = FeedbackLoop(
        selection_severity=0.4,
        n_generations=4,
        exploration_rate=0.05,
        generator="scm",
        n_applicants=1000,
        seed=42,
    ).run()
    assert _hash_v1_fields(res) == EXPECTED_DEFAULT_PATH_SHA256


def test_default_path_byte_identity_regression_is_seed_sensitive():
    """Sanity check on the hash oracle itself: a different seed must NOT
    collide with the pinned hash (guards against a vacuously-true comparison,
    e.g. hashing something seed-invariant by mistake)."""
    res = FeedbackLoop(
        selection_severity=0.4,
        n_generations=4,
        exploration_rate=0.05,
        generator="scm",
        n_applicants=1000,
        seed=43,
    ).run()
    assert _hash_v1_fields(res) != EXPECTED_DEFAULT_PATH_SHA256
