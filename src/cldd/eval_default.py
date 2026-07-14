"""Measurement edge of the closed loop (the **measure** stage).

Train the PD model on the *observed* (approved) rows only — exactly what a real
lender has — then score it against the planted ground truth across three
subpopulations: **all / approved / declined**. The declined subpopulation is the
headline: it is the part of the applicant pool whose outcomes real data can never
reveal, so its calibration error (ECE) is the signal the loop optimizes and the
selection bias it exposes.

The reusable pieces here (``fit_observed_model`` and ``score_pd_detection``) are
shared with ``loop.py`` so the "measure" and "improve" stages score detection
identically.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
from sklearn.metrics import brier_score_loss, roc_auc_score

from . import config, emp, model_pd


@dataclass
class SubgroupMetrics:
    """Detection/calibration metrics on one subpopulation.

    The EMP fields (v2 reporting axis, ``cldd.emp``) are ``None`` where
    inapplicable: ``emp_h*`` on cohorts without planted default timing (flat
    generator), all of them when the cohort lacks the pricing columns.
    """

    n: int
    base_rate: float          # true default fraction in the subgroup
    mean_pd: float            # mean predicted PD (vs base_rate => bias direction)
    auc: float
    brier: float
    ece: float
    f1: float             # F1 at the fixed diagnostic POLICY_PD_THRESHOLD; see f1_emp_cutoff
                           # below for the economically grounded EMPC-optimal-cutoff alternative
    empc: float | None = None            # literature EMPC (fraction of mean exposure)
    empc_fraction: float | None = None   # fraction APPROVED at the EMPC-optimal cutoff
    emp_h: float | None = None           # harness-derived EMP (SCM cohorts only)
    emp_h_fraction: float | None = None  # fraction APPROVED at its optimal cutoff
    f1_emp_cutoff: float | None = None   # F1 at the EMPC-optimal cutoff (vs f1 at 0.5)


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


def _f1_from_predictions(y_true: np.ndarray, pred: np.ndarray) -> float:
    yt = np.asarray(y_true).astype(int)
    pred = np.asarray(pred).astype(int)
    tp = int(((pred == 1) & (yt == 1)).sum())
    fp = int(((pred == 1) & (yt == 0)).sum())
    fn = int(((pred == 0) & (yt == 1)).sum())
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    return float(2 * precision * recall / (precision + recall)) if (precision + recall) else 0.0


def _f1_at_threshold(y_true: np.ndarray, p: np.ndarray, threshold: float) -> float:
    """F1 at a fixed PD threshold (``POLICY_PD_THRESHOLD`` by default).

    This is a diagnostic-only cutoff with no economic justification; see
    ``SubgroupMetrics.f1_emp_cutoff`` for F1 at the EMPC-optimal cutoff instead.
    """
    pred = (np.asarray(p) >= threshold).astype(int)
    return _f1_from_predictions(y_true, pred)


def _f1_at_approval_fraction(y_true: np.ndarray, scores: np.ndarray, fraction: float) -> float:
    """F1 when the ``fraction`` lowest-score rows are approved and the rest flagged.

    Order statistics on a stable ascending argsort (not a float threshold), so
    ties and the exact approved count are reproducible: ``n_approved =
    round(fraction * n)``.
    """
    n = len(y_true)
    if n == 0:
        return float("nan")
    order = np.argsort(np.asarray(scores, dtype=float), kind="stable")
    n_approved = int(round(fraction * n))
    n_approved = min(max(n_approved, 0), n)
    pred = np.ones(n, dtype=int)
    pred[order[:n_approved]] = 0
    return _f1_from_predictions(y_true, pred)


def _subgroup_metrics(
    y_true: np.ndarray,
    p: np.ndarray,
    threshold: float,
    *,
    default_day: np.ndarray | None = None,
    requested_amount: np.ndarray | None = None,
) -> SubgroupMetrics:
    """Metrics on one subpopulation, with EMP fields appended when priceable.

    ``default_day``/``requested_amount`` are the cohort's per-row pricing
    columns already sliced to this subgroup. EMP fields stay ``None`` when
    ``requested_amount`` is not supplied (no pricing) or the subgroup is
    empty; ``emp_h*`` additionally stay ``None`` when ``default_day`` is
    ``None`` (flat cohorts — no planted default timing).
    """
    y_true = np.asarray(y_true, dtype=int)
    p = np.asarray(p, dtype=float)
    n = len(y_true)
    if n == 0:
        return SubgroupMetrics(0, float("nan"), float("nan"), float("nan"), float("nan"), float("nan"), float("nan"))
    try:
        auc = float(roc_auc_score(y_true, p)) if len(np.unique(y_true)) > 1 else float("nan")
    except ValueError:
        auc = float("nan")
    metrics = SubgroupMetrics(
        n=n,
        base_rate=float(y_true.mean()),
        mean_pd=float(p.mean()),
        auc=auc,
        brier=float(brier_score_loss(y_true, p)) if len(np.unique(y_true)) > 1 else float("nan"),
        ece=expected_calibration_error(y_true, p),
        f1=_f1_at_threshold(y_true, p, threshold),
    )
    if requested_amount is not None:
        requested_amount = np.asarray(requested_amount, dtype=float)
        empc_result = emp.empc_literature(y_true, p)
        metrics.empc = empc_result.emp
        if not np.isnan(empc_result.optimal_fraction):  # guard: degenerate subgroup -> None
            metrics.empc_fraction = empc_result.optimal_fraction
            metrics.f1_emp_cutoff = _f1_at_approval_fraction(y_true, p, empc_result.optimal_fraction)
        emp_h_result = emp.emp_harness(y_true, p, default_day, requested_amount)
        if emp_h_result is not None:
            metrics.emp_h = emp_h_result.emp
            metrics.emp_h_fraction = emp_h_result.optimal_fraction
    return metrics


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
    # EMP pricing columns, from the same in-process cohort (no replay path).
    # default_day is None on flat cohorts (no planted default timing).
    default_day = cohort.get("days_to_default")
    requested_amount = cohort["features"]["requested_amount"].to_numpy(dtype=float)
    return {
        "all": _subgroup_metrics(
            y, p, threshold,
            default_day=default_day,
            requested_amount=requested_amount,
        ),
        "approved": _subgroup_metrics(
            y[approved], p[approved], threshold,
            default_day=default_day[approved] if default_day is not None else None,
            requested_amount=requested_amount[approved],
        ),
        "declined": _subgroup_metrics(
            y[declined], p[declined], threshold,
            default_day=default_day[declined] if default_day is not None else None,
            requested_amount=requested_amount[declined],
        ),
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
