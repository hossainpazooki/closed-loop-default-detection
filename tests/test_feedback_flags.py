"""v3 FeedbackLoop flags: ``retrain`` (frozen arm), ``policy_mode`` (prior arm),
and the default-path byte-identity regression (spec section 7 bullets 2-3).

Spec: docs/superpowers/specs/2026-07-14-cldd-v3-design.md (Rev 2), section 1.2.
"""

from __future__ import annotations

import hashlib
import importlib.util
import inspect
import json
import pathlib
import subprocess
import sys

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


# Pre-v3 baseline: the last commit before the v3 core landed (3f07075).
PRE_V3_COMMIT = "da81c98"

# The identity is measured DIFFERENTIALLY -- pre-v3 and current code run in the
# same process, same interpreter, same BLAS -- rather than against a stored
# hash. An earlier revision pinned a sha256 literal derived on one machine;
# HistGBT floats shift across OS and numpy version, so that literal encoded
# "same floats as the author's laptop" and failed on every non-Windows CI job
# (2026-07-19, 14/15 jobs red). Comparing both implementations in one
# environment tests the claim the spec actually makes -- that v3's flags did
# not perturb the default path -- and is invariant to the platform's floats.
RUN_KWARGS = dict(
    selection_severity=0.4,
    n_generations=4,
    exploration_rate=0.05,
    generator="scm",
    n_applicants=1000,
    seed=42,
)


def _load_pre_v3_feedback():
    """Import ``feedback.py`` as of :data:`PRE_V3_COMMIT` as a live module.

    Loaded under the package name ``cldd._prev3_feedback`` so its relative
    imports (``from . import config, ...``) resolve against the *current*
    ``cldd`` package. That is sound because v3's ``emp.py`` change was purely
    additive (``realized_book_profit`` appended); pre-v3 ``feedback.py`` does
    not import ``emp`` at all, so nothing it touches was modified.

    Skips (never silently passes) when the object is unreachable -- no git, not
    a checkout, or a shallow clone without history.
    """
    repo_root = pathlib.Path(__file__).resolve().parent.parent
    try:
        proc = subprocess.run(
            ["git", "show", f"{PRE_V3_COMMIT}:src/cldd/feedback.py"],
            cwd=repo_root,
            capture_output=True,
            text=True,
        )
    except (OSError, FileNotFoundError) as exc:  # pragma: no cover - env-dependent
        pytest.skip(f"git unavailable, cannot reconstruct pre-v3 baseline: {exc}")
    if proc.returncode != 0:  # pragma: no cover - env-dependent
        pytest.skip(
            f"pre-v3 blob {PRE_V3_COMMIT} unreachable (shallow clone or sdist): "
            f"{proc.stderr.strip()}"
        )

    name = "cldd._prev3_feedback"
    spec = importlib.util.spec_from_loader(name, loader=None)
    module = importlib.util.module_from_spec(spec)
    module.__package__ = "cldd"
    sys.modules[name] = module
    exec(  # noqa: S102 - executing a pinned in-repo git blob, not user input
        compile(proc.stdout, f"<{PRE_V3_COMMIT}:src/cldd/feedback.py>", "exec"),
        module.__dict__,
    )
    return module


@pytest.fixture(scope="module")
def pre_v3_feedback():
    """The reconstructed pre-v3 module, built once per module.

    Module-scoped because the blob exec and the baseline loop below are the
    expensive half of this file; rebuilding them per test tripled the work in
    every one of CI's fifteen jobs. Stays registered in ``sys.modules`` for the
    duration so anything resolved lazily off the module still works, and is
    unregistered on teardown.
    """
    module = _load_pre_v3_feedback()
    yield module
    sys.modules.pop("cldd._prev3_feedback", None)


@pytest.fixture(scope="module")
def baseline_hash(pre_v3_feedback):
    """Hash of the pre-v3 default-path run -- the differential reference.

    Computed once and shared: it is the same run for every comparison below.
    """
    return _hash_v1_fields(pre_v3_feedback.FeedbackLoop(**RUN_KWARGS).run())


def test_pre_v3_baseline_really_is_pre_v3(pre_v3_feedback):
    """Non-vacuity guard on the oracle itself.

    The differential test is only meaningful if the reconstructed module is
    genuinely older code. If the loader silently handed back today's
    ``feedback.py``, the comparison would be a tautology. v3 added the
    ``retrain`` and ``policy_mode`` parameters, so their *absence* is a
    positive signature of pre-v3 code.
    """
    params = inspect.signature(pre_v3_feedback.FeedbackLoop).parameters
    assert "retrain" not in params
    assert "policy_mode" not in params
    # ...and the current one does have them, so the two really do differ.
    current = inspect.signature(FeedbackLoop).parameters
    assert "retrain" in current
    assert "policy_mode" in current


def test_default_path_byte_identity_regression(baseline_hash):
    """Hard gate #1 (spec section 7): with default flags, v3 must reproduce
    pre-v3 behaviour on every v1 field, bit for bit."""
    current = FeedbackLoop(**RUN_KWARGS).run()
    assert _hash_v1_fields(current) == baseline_hash


def test_default_path_byte_identity_regression_is_seed_sensitive(baseline_hash):
    """Sanity check on the hash oracle: a different seed must NOT collide
    (guards against hashing something seed-invariant by mistake)."""
    other_seed = FeedbackLoop(**{**RUN_KWARGS, "seed": 43}).run()
    assert _hash_v1_fields(other_seed) != baseline_hash
