"""Minimal but real calibrated probability-of-default model + IPW weights.

This is the detector the closed loop drives — the analog of the cross-omics
detector in ``upstream-label-correction``. Two things matter here:

  1. **Calibration**, not just ranking: the closed loop scores calibration error
     on the declined subpopulation, so the model must emit honest probabilities.
     We fit a gradient-boosted classifier, then isotonic-calibrate it on a
     held-out slice of the training data.
  2. **Sample weights** flow end to end, so the loop's inverse-propensity
     (IPW) selection-bias lever can reweight the approved training rows.

scikit-learn only — ``HistGradientBoostingClassifier`` handles the structural
NaNs natively, so no imputation is needed. Everything is deterministic per seed.
"""

from __future__ import annotations

import numpy as np
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.isotonic import IsotonicRegression
from sklearn.model_selection import train_test_split

from . import config

#: Below this many samples in the minority class, skip the held-out isotonic step
#: (not enough positives to calibrate honestly) and return raw GBT probabilities.
_MIN_CLASS_FOR_CALIBRATION = 8


class CalibratedPDModel:
    """A fitted GBT classifier plus an optional isotonic calibrator."""

    def __init__(self, classifier: HistGradientBoostingClassifier, calibrator: IsotonicRegression | None):
        self.classifier = classifier
        self.calibrator = calibrator

    def predict_pd(self, X: np.ndarray) -> np.ndarray:
        raw = self.classifier.predict_proba(np.asarray(X, dtype=float))[:, 1]
        if self.calibrator is not None:
            raw = self.calibrator.predict(raw)
        return np.clip(raw, 0.0, 1.0)


def _new_classifier(random_state: int) -> HistGradientBoostingClassifier:
    return HistGradientBoostingClassifier(
        random_state=random_state,
        max_depth=3,
        max_iter=200,
        learning_rate=0.06,
        l2_regularization=1.0,
    )


def train_pd_model(
    X,
    y,
    sample_weight=None,
    random_state: int | None = None,
) -> CalibratedPDModel:
    """Fit the PD estimator and return a calibrated model.

    ``sample_weight`` (e.g. IPW weights) is forwarded to both the classifier and
    the isotonic calibrator so the selection-bias correction is honored throughout.
    """
    X = np.asarray(X, dtype=float)
    y = np.asarray(y, dtype=int)
    rs = config.RANDOM_SEED if random_state is None else random_state
    sw = None if sample_weight is None else np.asarray(sample_weight, dtype=float)

    clf = _new_classifier(rs)
    counts = np.bincount(y, minlength=2)
    if len(np.unique(y)) < 2 or counts.min() < _MIN_CLASS_FOR_CALIBRATION:
        # Too few positives (or one class) to carve a calibration split — fit on
        # everything and skip isotonic rather than fail.
        clf.fit(X, y, sample_weight=sw)
        return CalibratedPDModel(clf, None)

    idx = np.arange(len(y))
    fit_idx, cal_idx = train_test_split(idx, test_size=0.3, random_state=rs, stratify=y)
    clf.fit(X[fit_idx], y[fit_idx], sample_weight=None if sw is None else sw[fit_idx])

    raw_cal = clf.predict_proba(X[cal_idx])[:, 1]
    iso = IsotonicRegression(out_of_bounds="clip", y_min=0.0, y_max=1.0)
    iso.fit(raw_cal, y[cal_idx], sample_weight=None if sw is None else sw[cal_idx])
    return CalibratedPDModel(clf, iso)


def predict_pd(model: CalibratedPDModel, X) -> np.ndarray:
    """Calibrated PD point estimates in [0, 1], one per row."""
    return model.predict_pd(np.asarray(X, dtype=float))


def selection_adjusted_weights(
    X,
    approved,
    clip: tuple[float, float] = (0.05, 0.95),
    random_state: int | None = None,
) -> np.ndarray:
    """Inverse-propensity weights that correct prior-approval selection bias.

    Fits a propensity model ``P(approved | features)`` and returns ``1/propensity``
    for every row. The loop applies the approved-row slice as training weights so
    the funded sample is reweighted back toward the full applicant population.

    Note the assumption this rides on (the heart of the Deliverable D causal
    discussion): IPW only corrects selection that is explained by the *observed*
    features. The synthetic generator deliberately routes part of the selection
    through an unobserved confounder, so this correction degrades as selection
    severity rises — which is exactly the frontier the loop measures.
    """
    X = np.asarray(X, dtype=float)
    approved = np.asarray(approved).astype(int)
    rs = config.RANDOM_SEED if random_state is None else random_state

    propensity_model = _new_classifier(rs)
    propensity_model.fit(X, approved)
    propensity = propensity_model.predict_proba(X)[:, 1]
    propensity = np.clip(propensity, clip[0], clip[1])
    return 1.0 / propensity
