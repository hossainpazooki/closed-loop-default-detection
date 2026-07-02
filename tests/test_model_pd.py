"""Focused regression tests for the calibrated PD detector (``cldd.model_pd``).

These assert *behavioral / structural* properties (output ranges, branch selection,
determinism, weight effects) rather than frozen float values, so they run on the
cross-version compat matrix and are NOT marked ``pinned``. Determinism is checked by
comparing two in-process runs to each other, which is environment-independent.
"""

from __future__ import annotations

import numpy as np

from cldd import CalibratedPDModel
from cldd.model_pd import (
    _MIN_CLASS_FOR_CALIBRATION,
    predict_pd,
    selection_adjusted_weights,
    train_pd_model,
)


def _xy(n=300, seed=0):
    """A small, separable-ish binary problem so the GBT has real signal."""
    rng = np.random.default_rng(seed)
    X = rng.normal(size=(n, 4))
    prob = 1.0 / (1.0 + np.exp(-(1.5 * X[:, 0] - 0.3)))
    y = (rng.uniform(size=n) < prob).astype(int)
    return X, y


def test_train_returns_calibrated_model_with_pd_in_unit_interval():
    X, y = _xy()
    model = train_pd_model(X, y, random_state=42)
    assert isinstance(model, CalibratedPDModel)
    p = model.predict_pd(X)
    assert p.shape == (len(X),)
    assert np.all((p >= 0.0) & (p <= 1.0))


def test_module_predict_pd_matches_method():
    X, y = _xy()
    model = train_pd_model(X, y, random_state=42)
    assert np.array_equal(predict_pd(model, X), model.predict_pd(X))


def test_calibrator_fitted_when_both_classes_are_well_populated():
    X, y = _xy(n=400, seed=1)
    assert y.sum() >= _MIN_CLASS_FOR_CALIBRATION
    assert (len(y) - y.sum()) >= _MIN_CLASS_FOR_CALIBRATION
    model = train_pd_model(X, y, random_state=42)
    assert model.calibrator is not None


def test_calibration_skipped_when_too_few_positives():
    # Fewer than _MIN_CLASS_FOR_CALIBRATION positives -> skip isotonic, raw GBT only.
    X, _ = _xy()
    y = np.zeros(len(X), dtype=int)
    y[: _MIN_CLASS_FOR_CALIBRATION - 1] = 1  # 7 positives < 8
    model = train_pd_model(X, y, random_state=42)
    assert model.calibrator is None
    p = model.predict_pd(X)
    assert np.all((p >= 0.0) & (p <= 1.0))


def test_single_class_labels_do_not_crash():
    X, _ = _xy()
    y = np.zeros(len(X), dtype=int)  # one class only
    model = train_pd_model(X, y, random_state=42)
    assert model.calibrator is None
    p = model.predict_pd(X)
    assert np.all((p >= 0.0) & (p <= 1.0))


def test_same_seed_is_deterministic():
    X, y = _xy()
    a = train_pd_model(X, y, random_state=7).predict_pd(X)
    b = train_pd_model(X, y, random_state=7).predict_pd(X)
    assert np.array_equal(a, b)  # two in-process runs -> environment-independent


def test_sample_weight_changes_and_directionally_shifts_predictions():
    X, y = _xy()
    base = train_pd_model(X, y, random_state=42).predict_pd(X)
    w = np.ones(len(y), dtype=float)
    w[y == 1] = 5.0  # up-weight defaults
    weighted = train_pd_model(X, y, sample_weight=w, random_state=42).predict_pd(X)
    assert not np.array_equal(base, weighted)
    assert weighted.mean() > base.mean()  # more weight on positives -> higher mean PD


def test_selection_adjusted_weights_are_clipped_inverse_propensity():
    X, _ = _xy(n=400, seed=2)
    approved = (X[:, 1] > 0.0).astype(int)  # selection driven by an observed feature
    w = selection_adjusted_weights(X, approved, clip=(0.05, 0.95), random_state=42)
    assert w.shape == (len(X),)
    # 1 / propensity with propensity clipped to [0.05, 0.95] -> weights in [1/0.95, 1/0.05].
    assert np.all(w >= 1.0 / 0.95 - 1e-9)
    assert np.all(w <= 1.0 / 0.05 + 1e-9)
