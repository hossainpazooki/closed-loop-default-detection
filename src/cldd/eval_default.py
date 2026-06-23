"""Measurement edge of the closed loop (the **measure** stage).

Train the PD model on the *observed* (approved) rows only — exactly what a real
lender has — then score it against the planted ground truth across three
subpopulations: **all / approved / declined**. The declined subpopulation is the
headline: it is the part of the applicant pool whose outcomes real data can never
reveal, so its calibration error (ECE) is the signal the loop optimizes and the
selection bias it exposes.

The reusable pieces here (``fit_observed_model`` and ``score_pd_detection``) are
shared with ``loop.py`` so the "measure" and "improve" stages score detection
identically — mirroring the building blocks shared in
``upstream-label-correction/evals/mislabel_detection.py``.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
from sklearn.metrics import brier_score_loss, roc_auc_score

from . import config, model_pd


@dataclass
class SubgroupMetrics:
    """Detection/calibration metrics on one subpopulation."""

    n: int
    base_rate: float          # true default fraction in the subgroup
    mean_pd: float            # mean predicted PD (vs base_rate => bias direction)
    auc: float
    brier: float
    ece: float
    f1: float


@dataclass
class PdDetectionResult:
    """Result of scoring one model on one cohort (local analog of EvalResult)."""

    name: str
    passed: bool
    score: float              # headline: declined-subpopulation ECE (lower better)
    threshold: float
    details: dict = field(default_factory=dict)


def expected_calibration_error(y_true: np.ndarray, p: np.ndarray, n_bins: int = 10) -> float:
    """Standard ECE: mean over equal-width PD bins of ``|accuracy - confidence|``."""
    y_true = np.asarray(y_true, dtype=float)
    p = np.asarray(p, dtype=float)
    if len(p) == 0:
        return float("nan")
    bins = np.linspace(0.0, 1.0, n_bins + 1)
    bin_idx = np.digitize(p, bins[1:-1])  # 0..n_bins-1
    ece = 0.0
    for b in range(n_bins):
        m = bin_idx == b
        count = int(m.sum())
        if count == 0:
            continue
        ece += (count / len(p)) * abs(float(y_true[m].mean()) - float(p[m].mean()))
    return float(ece)


def _f1_at_threshold(y_true: np.ndarray, p: np.ndarray, threshold: float) -> float:
    pred = (np.asarray(p) >= threshold).astype(int)
    yt = np.asarray(y_true).astype(int)
    tp = int(((pred == 1) & (yt == 1)).sum())
    fp = int(((pred == 1) & (yt == 0)).sum())
    fn = int(((pred == 0) & (yt == 1)).sum())
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    return float(2 * precision * recall / (precision + recall)) if (precision + recall) else 0.0


def _subgroup_metrics(y_true: np.ndarray, p: np.ndarray, threshold: float) -> SubgroupMetrics:
    y_true = np.asarray(y_true, dtype=int)
    p = np.asarray(p, dtype=float)
    n = len(y_true)
    if n == 0:
        return SubgroupMetrics(0, float("nan"), float("nan"), float("nan"), float("nan"), float("nan"), float("nan"))
    try:
        auc = float(roc_auc_score(y_true, p)) if len(np.unique(y_true)) > 1 else float("nan")
    except ValueError:
        auc = float("nan")
    return SubgroupMetrics(
        n=n,
        base_rate=float(y_true.mean()),
        mean_pd=float(p.mean()),
        auc=auc,
        brier=float(brier_score_loss(y_true, p)) if len(np.unique(y_true)) > 1 else float("nan"),
        ece=expected_calibration_error(y_true, p),
        f1=_f1_at_threshold(y_true, p, threshold),
    )


def fit_observed_model(cohort: dict, sample_weight=None, random_state: int | None = None) -> model_pd.CalibratedPDModel:
    """Fit the PD model on the cohort's **approved** rows only (selective labels).

    ``sample_weight``, when given, must already be aligned to the approved rows
    (length == ``cohort['approved'].sum()``) — the loop passes the approved slice
    of the IPW weights here.
    """
    X = cohort["features"].to_numpy(dtype=float)
    approved = cohort["approved"]
    return model_pd.train_pd_model(
        X[approved],
        cohort["true_default"][approved],
        sample_weight=sample_weight,
        random_state=random_state,
    )


def score_pd_detection(
    model: model_pd.CalibratedPDModel,
    cohort: dict,
    threshold: float | None = None,
    funded=None,
) -> dict:
    """Score ``model`` on the full cohort vs planted truth, split by subpopulation.

    Returns ``{'all', 'approved', 'declined'}`` -> :class:`SubgroupMetrics`, plus
    the raw ``predictions``. ``funded`` overrides the subgrouping mask (default:
    the cohort's prior-policy ``approved``) — the exploration lever and the
    feedback loop pass the mask of rows that were *actually* funded, so
    ``'declined'`` is exactly the never-labeled (out-of-training) population.
    """
    threshold = config.POLICY_PD_THRESHOLD if threshold is None else threshold
    X = cohort["features"].to_numpy(dtype=float)
    p = model_pd.predict_pd(model, X)
    y = cohort["true_default"]
    approved = cohort["approved"] if funded is None else np.asarray(funded, dtype=bool)
    declined = ~approved
    return {
        "all": _subgroup_metrics(y, p, threshold),
        "approved": _subgroup_metrics(y[approved], p[approved], threshold),
        "declined": _subgroup_metrics(y[declined], p[declined], threshold),
        "predictions": p,
    }


def evaluate_naive(cohort: dict, threshold: float | None = None, target_ece: float | None = None) -> PdDetectionResult:
    """Convenience: train-on-observed (no correction) and score, as a PASS/FAIL result.

    PASS when declined-subpopulation ECE <= ``target_ece``.
    """
    threshold = config.POLICY_PD_THRESHOLD if threshold is None else threshold
    target_ece = config.TARGET_DECLINED_ECE if target_ece is None else target_ece
    model = fit_observed_model(cohort)
    scored = score_pd_detection(model, cohort, threshold)
    declined_ece = scored["declined"].ece
    return PdDetectionResult(
        name="pd_default_detection",
        passed=declined_ece <= target_ece,
        score=declined_ece,
        threshold=threshold,
        details={"all": scored["all"], "approved": scored["approved"], "declined": scored["declined"]},
    )
