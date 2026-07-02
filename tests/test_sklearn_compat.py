"""sklearn estimator-API compatibility tests for ``CalibratedPDClassifier``.

``CalibratedPDClassifier`` is a thin sklearn-style wrapper around the research
API (``train_pd_model``); these tests pin the estimator contract — construction,
``clone``/``get_params`` round-trips, fit/predict shapes, ``NotFittedError``,
sample-weight forwarding, determinism — plus the honest boundary: the wrapper
must produce byte-identical probabilities to the research entry point it wraps.

Like ``test_model_pd.py`` these are behavioral (not ``pinned``): determinism is
asserted by comparing two in-process runs, never against frozen floats.

The last test runs the full ``sklearn.utils.estimator_checks.check_estimator``
battery; under the pinned environment (scikit-learn 1.9.0) every generated
check passes. ``VERSION_SPECIFIC_ALLOWED_FAILURES`` exists as the documented
escape hatch should another sklearn version on the compat matrix generate a
check that conflicts with the research semantics — it is currently empty.
"""

from __future__ import annotations

import numpy as np
import pytest
from sklearn.base import clone
from sklearn.exceptions import NotFittedError
from sklearn.utils.estimator_checks import check_estimator

from cldd import CalibratedPDClassifier
from cldd.model_pd import train_pd_model


def _xy(n=300, seed=0):
    """Same small separable-ish binary problem as ``test_model_pd.py``."""
    rng = np.random.default_rng(seed)
    X = rng.normal(size=(n, 4))
    prob = 1.0 / (1.0 + np.exp(-(1.5 * X[:, 0] - 0.3)))
    y = (rng.uniform(size=n) < prob).astype(int)
    return X, y


# --- constructor / params / clone -------------------------------------------


def test_constructor_stores_params_verbatim_and_creates_no_state():
    est = CalibratedPDClassifier(random_state=7)
    assert est.random_state == 7
    # No learned state before fit: nothing fitted-looking on the instance.
    assert not [a for a in vars(est) if a.endswith("_") and not a.startswith("_")]


def test_get_params_set_params_roundtrip():
    est = CalibratedPDClassifier(random_state=3)
    params = est.get_params()
    assert params["random_state"] == 3
    est.set_params(random_state=11)
    assert est.get_params()["random_state"] == 11


def test_clone_returns_unfitted_copy_with_same_params():
    X, y = _xy()
    est = CalibratedPDClassifier(random_state=5).fit(X, y)
    cloned = clone(est)
    assert cloned is not est
    assert cloned.get_params() == est.get_params()
    with pytest.raises(NotFittedError):
        cloned.predict_proba(X)


# --- fit / predict contract ---------------------------------------------------


def test_fit_returns_self_and_sets_fitted_attributes():
    X, y = _xy()
    est = CalibratedPDClassifier(random_state=42)
    assert est.fit(X, y) is est
    assert np.array_equal(est.classes_, np.array([0, 1]))
    assert est.n_features_in_ == X.shape[1]


def test_predict_proba_shape_and_unit_interval():
    X, y = _xy()
    proba = CalibratedPDClassifier(random_state=42).fit(X, y).predict_proba(X)
    assert proba.shape == (len(X), 2)
    assert np.all((proba >= 0.0) & (proba <= 1.0))
    assert np.allclose(proba.sum(axis=1), 1.0)


def test_predict_returns_binary_labels():
    X, y = _xy()
    pred = CalibratedPDClassifier(random_state=42).fit(X, y).predict(X)
    assert pred.shape == (len(X),)
    assert set(np.unique(pred)) <= {0, 1}


def test_predict_consistent_with_predict_proba_argmax():
    X, y = _xy()
    est = CalibratedPDClassifier(random_state=42).fit(X, y)
    assert np.array_equal(est.predict(X), est.classes_[np.argmax(est.predict_proba(X), axis=1)])


def test_unfitted_predict_raises_notfittederror():
    X, _ = _xy()
    with pytest.raises(NotFittedError):
        CalibratedPDClassifier().predict(X)
    with pytest.raises(NotFittedError):
        CalibratedPDClassifier().predict_proba(X)


def test_non_01_binary_labels_are_preserved():
    X, y01 = _xy()
    y = np.where(y01 == 1, "default", "repaid")
    est = CalibratedPDClassifier(random_state=42).fit(X, y)
    assert set(est.classes_) == {"default", "repaid"}
    assert set(np.unique(est.predict(X))) <= {"default", "repaid"}


def test_single_class_fit_raises_value_error():
    X, _ = _xy()
    with pytest.raises(ValueError, match="class"):
        CalibratedPDClassifier(random_state=42).fit(X, np.zeros(len(X), dtype=int))


def test_predict_feature_count_mismatch_raises():
    X, y = _xy()
    est = CalibratedPDClassifier(random_state=42).fit(X, y)
    with pytest.raises(ValueError):
        est.predict_proba(X[:, :2])


# --- research-API equivalence and determinism ---------------------------------


def test_wrapper_is_byte_identical_to_train_pd_model():
    # The compatibility boundary: the sklearn face must not change the science.
    X, y = _xy()
    research = train_pd_model(X, y, random_state=42).predict_pd(X)
    wrapped = CalibratedPDClassifier(random_state=42).fit(X, y).predict_proba(X)[:, 1]
    assert np.array_equal(research, wrapped)


def test_same_seed_is_deterministic():
    X, y = _xy()
    a = CalibratedPDClassifier(random_state=7).fit(X, y).predict_proba(X)
    b = CalibratedPDClassifier(random_state=7).fit(X, y).predict_proba(X)
    assert np.array_equal(a, b)  # two in-process runs -> environment-independent


def test_sample_weight_accepted_and_directional():
    X, y = _xy()
    base = CalibratedPDClassifier(random_state=42).fit(X, y).predict_proba(X)[:, 1]
    w = np.ones(len(y), dtype=float)
    w[y == 1] = 5.0  # up-weight defaults
    weighted = (
        CalibratedPDClassifier(random_state=42).fit(X, y, sample_weight=w).predict_proba(X)[:, 1]
    )
    assert not np.array_equal(base, weighted)
    assert weighted.mean() > base.mean()  # more weight on positives -> higher mean PD


def test_nan_features_are_accepted():
    # HistGradientBoosting handles structural NaNs natively; the wrapper must not reject them.
    X, y = _xy()
    X = X.copy()
    X[::7, 2] = np.nan
    proba = CalibratedPDClassifier(random_state=42).fit(X, y).predict_proba(X)
    assert np.all((proba >= 0.0) & (proba <= 1.0))


# --- the full sklearn check battery -------------------------------------------

#: Escape hatch for cross-version CI: if a *different* sklearn release generates a
#: check that conflicts with the research semantics (e.g. a stricter sample-weight
#: equivalence check — the calibration split in ``train_pd_model`` is drawn on row
#: indices, and ``HistGradientBoostingClassifier`` bins features, so exact
#: weight-k == repeat-k-times equivalence is not guaranteed by design), record its
#: name substring here WITH a rationale. Empty means: every generated check passes
#: on the versions tested so far (scikit-learn 1.7.2 and 1.9.0 on the CI compat
#: matrix, plus a one-off local 1.8.0 run).
VERSION_SPECIFIC_ALLOWED_FAILURES: tuple[str, ...] = ()


@pytest.mark.filterwarnings("ignore::sklearn.exceptions.SkipTestWarning")
def test_check_estimator_battery_passes():
    results = check_estimator(CalibratedPDClassifier(random_state=42), on_fail=None)
    assert len(results) > 50  # sanity: the battery actually ran
    failed = [r["check_name"] for r in results if r["status"] == "failed"]
    unexpected = [
        name
        for name in failed
        if not any(s in name for s in VERSION_SPECIFIC_ALLOWED_FAILURES)
    ]
    assert not unexpected, f"unexpected sklearn check failures: {unexpected}"
