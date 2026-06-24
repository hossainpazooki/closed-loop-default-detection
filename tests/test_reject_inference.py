"""Tests for the reject-inference correctors (cldd.reject_inference).

Cover the load-bearing properties: the integrity invariant (an RI corrector never
reads a declined planted label at fit time), the held-out grading split,
determinism of the stochastic method, DECISION 1 (score-band augmentation is a
distinct estimator from propensity IPW, not a rename), and measured-before-frozen
directional grading against the oracle. Float-exact provenance lives in one
``pinned`` test; everything else asserts structural facts or robust margins so it
runs on the cross-version compat matrix.
"""

from __future__ import annotations

import numpy as np
import pytest

from cldd import config, eval_default, model_pd
from cldd.correctors import CorrectorContext
from cldd.loop import make_generator
from cldd.reject_inference import (
    AugmentationCorrector,
    FuzzyAugmentationCorrector,
    ParcellingCorrector,
    ReclassificationCorrector,
    grade_on_declined_fold,
    split_declines,
)

METHODS = [
    ReclassificationCorrector,
    AugmentationCorrector,
    FuzzyAugmentationCorrector,
    ParcellingCorrector,
]


def _ctx(seed: int, severity: float) -> CorrectorContext:
    return CorrectorContext(
        seed=seed, policy_threshold=config.POLICY_PD_THRESHOLD, severity=severity,
        iteration=0, exploration_rate=0.0, make_train_cohort=lambda: (None, 0),
    )


def _cohort(severity: float, seed: int = 42, n: int = 1200) -> dict:
    return make_generator(
        "flat", severity=severity, seed=seed, n_applicants=n,
        approval_rate=config.DEFAULT_APPROVAL_RATE,
    ).generate_cohort()


def _grade_all(severity: float, seed: int = 42, n: int = 1200) -> dict[str, float]:
    cohort = _cohort(severity, seed=seed, n=n)
    approved = np.asarray(cohort["approved"], dtype=bool)
    _, eval_idx = split_declines(approved, seed=seed, iteration=0)
    naive = eval_default.fit_observed_model(cohort, random_state=seed)
    out = {"naive": grade_on_declined_fold(naive, cohort, eval_idx, config.POLICY_PD_THRESHOLD).declined_ece}
    for Method in METHODS:
        out[Method().name] = Method().apply(cohort, _ctx(seed, severity)).metrics.declined_ece
    return out


# --- integrity invariant --------------------------------------------------- #
@pytest.mark.parametrize("Method", METHODS, ids=[m().name for m in METHODS])
def test_fit_never_reads_declined_labels(Method):
    """Corrupting every declined planted label leaves the fitted model unchanged —
    structural proof the corrector uses declined FEATURES, never their labels."""
    cohort = _cohort(0.6, seed=7)
    approved = np.asarray(cohort["approved"], dtype=bool)
    ctx = _ctx(7, 0.6)
    model_clean = Method()._fit(cohort, ctx)

    corrupt = dict(cohort)
    td = np.asarray(cohort["true_default"]).copy()
    rng = np.random.default_rng(12345)
    td[~approved] = rng.integers(0, 2, int((~approved).sum()))
    corrupt["true_default"] = td
    model_corrupt = Method()._fit(corrupt, ctx)

    X = cohort["features"].to_numpy(dtype=float)
    assert np.array_equal(model_pd.predict_pd(model_clean, X), model_pd.predict_pd(model_corrupt, X))


# --- held-out grading split ------------------------------------------------ #
def test_declined_split_is_held_out_and_complete():
    cohort = _cohort(0.4)
    approved = np.asarray(cohort["approved"], dtype=bool)
    declined = np.flatnonzero(~approved)
    train_idx, eval_idx = split_declines(approved, seed=42, iteration=0)

    assert set(train_idx.tolist()).isdisjoint(set(eval_idx.tolist()))
    assert np.array_equal(np.sort(np.concatenate([train_idx, eval_idx])), declined)
    assert eval_idx.size == round(declined.size * config.RI_EVAL_FRACTION)

    out = ReclassificationCorrector().apply(cohort, _ctx(42, 0.4))
    assert out.info["n_eval_declines"] == eval_idx.size
    assert out.info["n_train_declines"] == train_idx.size


# --- determinism ----------------------------------------------------------- #
def test_parcelling_is_deterministic():
    """The stochastic method seeds its label draw from ctx (never a global RNG)."""
    cohort = _cohort(0.6, seed=7)
    ctx = _ctx(7, 0.6)
    a = ParcellingCorrector().apply(cohort, ctx).metrics.declined_ece
    b = ParcellingCorrector().apply(cohort, ctx).metrics.declined_ece
    assert a == b


# --- DECISION 1: augmentation is not IPW ----------------------------------- #
def test_augmentation_is_not_ipw_reweighting():
    """Score-band augmentation weights differ from propensity-IPW weights: a
    distinct estimator, not a rename of IPWReweightCorrector."""
    cohort = _cohort(0.4)
    X = cohort["features"].to_numpy(dtype=float)
    approved = np.asarray(cohort["approved"], dtype=bool)
    y_app = np.asarray(cohort["true_default"], dtype=int)[approved]
    kgb = eval_default.fit_observed_model(cohort, random_state=42)
    train_idx, _ = split_declines(approved, seed=42, iteration=0)

    _, _, _, aug_w = AugmentationCorrector()._augment(X, y_app, kgb, approved, train_idx, _ctx(42, 0.4))
    ipw_w = model_pd.selection_adjusted_weights(X, approved, random_state=42)[approved]
    assert not np.allclose(aug_w, ipw_w)


# --- directional oracle grading (measured before frozen) ------------------- #
def test_all_methods_finite_and_in_unit_range():
    for sev in (0.0, 0.4, 1.0):
        for name, ece in _grade_all(sev).items():
            assert 0.0 <= ece <= 1.0, f"{name}@{sev}={ece}"


def test_mnar_confounder_defeats_every_method():
    """At full severity the unobserved confounder dominates: no method (naive or
    any RI) clears the declined-ECE target, and the best RI only modestly improves
    on naive. This is the honest headline — RI does not rescue calibration."""
    g = _grade_all(1.0)
    assert min(g.values()) > config.TARGET_DECLINED_ECE  # nobody clears 0.10
    best_ri = min(v for k, v in g.items() if k != "naive")
    assert g["naive"] - best_ri < 0.15


def test_methods_exported_from_top_level():
    import cldd

    for cls in (
        "RejectInferenceCorrector", "ReclassificationCorrector", "AugmentationCorrector",
        "FuzzyAugmentationCorrector", "ParcellingCorrector",
    ):
        assert hasattr(cldd, cls)


# --- frozen provenance (pinned) -------------------------------------------- #
@pytest.mark.pinned
def test_frozen_declined_ece_flat_seed42_sev04():
    """Float-exact provenance guard: RI held-out declined-ECE at flat / seed 42 /
    severity 0.4 / n=1200. Reproducible only under the requirements-dev pins."""
    g = _grade_all(0.4, seed=42, n=1200)
    assert g["reclassification"] == 0.1480435064244274
    assert g["augmentation"] == 0.08589491155608098
    assert g["fuzzy_augmentation"] == 0.06997504883677406
    assert g["parcelling"] == 0.07513693098358165
