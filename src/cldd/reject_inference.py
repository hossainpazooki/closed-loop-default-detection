"""Reject-inference correction levers, graded against planted ground truth.

These are **Correctors-under-grade**, not a practitioner-facing reject-inference
API. There is deliberately no ``run_reject_inference_on(df)`` helper: the whole
point of the harness is that every method is scored against the *planted* default
labels on the applicants a prior policy declined, which real data does not have.
The moment a method is exposed for users' real data the oracle is gone, so the
public surface here is only the closed loop's ``Corrector`` contract.

**Integrity invariant (the make-or-break property).** A reject-inference corrector
may use the declined applicants' *features* but never their planted
``true_default`` at fit time — exactly the no-leakage discipline the naive lever
already follows (it fits approved rows only). This is enforced *structurally*: a
subclass's :meth:`RejectInferenceCorrector._augment` is handed the feature matrix,
the **approved** rows' (observable) labels, and a KGB model — it is never given
the declined labels at all. ``test_reject_inference.py`` additionally asserts the
fitted model is invariant to corrupting the declined labels.

**What the numbers certify.** Declined-cohort calibration is measured on a
**held-out fold** of the declines (``config.RI_EVAL_FRACTION``): the method may
pseudo-label one fold of the declines for training, and is graded on the *other*
fold it never saw. So a number here certifies "calibration recovered on held-out
declined applicants from this cohort", not generalization of the pseudo-labeling
rule to a fresh cohort (a different claim — see :func:`split_declines`).

The four shipped methods all route their constructed training set through the
same ``model_pd.train_pd_model`` the naive lever uses, so a frontier table over
{naive, IPW, these four} compares training-set construction with the downstream
PD model held fixed.

*Conceptual anchor (a pointer, not a treatise):* the reweighting family is the
importance-sampling dual of rejection sampling against the selection policy, and
both fail at the positivity boundary — so the operating frontier is where the
inverse map stops existing.
"""

from __future__ import annotations

from abc import abstractmethod

import numpy as np

from . import config, eval_default, model_pd
from .correctors import CorrectionOutcome, Corrector, CorrectorContext, LeverMetrics

#: Acceptance-rate / propensity clip shared with the IPW lever's spirit — keeps
#: band reweighting from exploding on a near-empty band.
_RATE_CLIP = (0.05, 1.0)


def split_declines(
    approved,
    *,
    seed: int,
    iteration: int,
    eval_fraction: float = config.RI_EVAL_FRACTION,
) -> tuple[np.ndarray, np.ndarray]:
    """Split the declined rows into a pseudo-label fold and a held-out grading fold.

    Deterministic given ``(seed, iteration)`` via a dedicated RNG stream
    (``config.RI_SPLIT_STREAM``), so every RI corrector and the frontier driver
    score on identical eval rows — the comparison stays apples-to-apples. Returns
    ``(train_idx, eval_idx)`` as sorted arrays of row indices into the cohort.
    """
    declined_idx = np.flatnonzero(~np.asarray(approved, dtype=bool))
    rng = np.random.default_rng([seed, iteration, config.RI_SPLIT_STREAM])
    perm = rng.permutation(declined_idx)
    n_eval = int(round(len(declined_idx) * eval_fraction))
    eval_idx = np.sort(perm[:n_eval])
    train_idx = np.sort(perm[n_eval:])
    return train_idx, eval_idx


def grade_on_declined_fold(model, cohort: dict, eval_idx: np.ndarray, threshold: float) -> LeverMetrics:
    """Score ``model`` so the ``declined`` subgroup is exactly ``eval_idx``.

    ``score_pd_detection``'s ``declined`` subgroup is ``~funded``; we mark every
    row funded except the held-out eval fold, so declined-cohort metrics are
    computed on the held-out declines against their planted truth (grading only).
    """
    approved = np.asarray(cohort["approved"], dtype=bool)
    funded = np.ones(approved.shape[0], dtype=bool)
    funded[eval_idx] = False
    scored = eval_default.score_pd_detection(model, cohort, threshold, funded=funded)
    return LeverMetrics.from_scored(scored)


def _score_bands(p: np.ndarray, n_bands: int) -> np.ndarray:
    """Assign each score to one of ``n_bands`` quantile bands (0..n_bands-1)."""
    edges = np.quantile(p, np.linspace(0.0, 1.0, n_bands + 1))
    return np.clip(np.digitize(p, edges[1:-1]), 0, n_bands - 1)


class RejectInferenceCorrector(Corrector):
    """Base for reject-inference levers.

    Subclasses implement :meth:`_augment`, which — given the feature matrix, the
    **approved** rows' labels, a KGB model fit on the approved rows, the approved
    mask, and the pseudo-label fold of declined indices — returns the extra
    training rows (declined features with *pseudo*-labels) and/or per-approved-row
    weights. Crucially, ``_augment`` is never handed the declined ``true_default``,
    so the integrity invariant holds by construction.

    The base owns: the declined train/eval split, assembling the training set,
    fitting via ``model_pd.train_pd_model`` (the same estimator the naive lever
    uses), and grading on the held-out declined fold.
    """

    #: Above the built-in levers (naive=0, retrain=1, reweight=2, explore=3) so an
    #: RI lever drives loop control if dropped into a ``SelectiveLabelsLoop`` —
    #: though these levers are designed to be graded by ``run_reject_inference.py``.
    control_priority = 4

    @abstractmethod
    def _augment(
        self,
        X: np.ndarray,
        y_approved: np.ndarray,
        kgb: model_pd.CalibratedPDModel,
        approved: np.ndarray,
        train_idx: np.ndarray,
        ctx: CorrectorContext,
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray | None]:
        """Return ``(extra_X, extra_y, extra_w, approved_w)``.

        ``extra_*`` are declined rows to ADD to training with *pseudo*-labels
        (may be empty arrays). ``approved_w`` is per-approved-row weights, or
        ``None`` for uniform. MUST NOT read the declined planted labels.
        """
        ...

    def _fit(self, cohort: dict, ctx: CorrectorContext) -> model_pd.CalibratedPDModel:
        X = cohort["features"].to_numpy(dtype=float)
        approved = np.asarray(cohort["approved"], dtype=bool)
        y = np.asarray(cohort["true_default"], dtype=int)
        y_approved = y[approved]
        train_idx, _ = split_declines(approved, seed=ctx.seed, iteration=ctx.iteration)

        # KGB ("known good/bad") model: the naive detector, fit on approved rows
        # only with their observable labels. Reused by every method to score declines.
        kgb = eval_default.fit_observed_model(cohort, random_state=ctx.seed)

        extra_X, extra_y, extra_w, approved_w = self._augment(
            X, y_approved, kgb, approved, train_idx, ctx
        )

        X_app = X[approved]
        w_app = np.ones(int(approved.sum())) if approved_w is None else np.asarray(approved_w, dtype=float)
        extra_X = np.asarray(extra_X, dtype=float)
        if extra_X.size:
            X_train = np.vstack([X_app, extra_X])
            y_train = np.concatenate([y_approved, np.asarray(extra_y, dtype=int)])
            w_train = np.concatenate([w_app, np.asarray(extra_w, dtype=float)])
        else:
            X_train, y_train, w_train = X_app, y_approved, w_app

        return model_pd.train_pd_model(X_train, y_train, sample_weight=w_train, random_state=ctx.seed)

    def apply(self, cohort: dict, ctx: CorrectorContext) -> CorrectionOutcome:
        approved = np.asarray(cohort["approved"], dtype=bool)
        train_idx, eval_idx = split_declines(approved, seed=ctx.seed, iteration=ctx.iteration)
        model = self._fit(cohort, ctx)
        metrics = grade_on_declined_fold(model, cohort, eval_idx, ctx.policy_threshold)
        return CorrectionOutcome(
            metrics=metrics,
            info={"n_train_declines": int(train_idx.size), "n_eval_declines": int(eval_idx.size)},
        )


class ReclassificationCorrector(RejectInferenceCorrector):
    """Hard-cutoff reclassification: pseudo-label the declined fold by thresholding
    the KGB score at ``policy_threshold``, then add those rows to training."""

    name = "reclassification"

    def _augment(self, X, y_approved, kgb, approved, train_idx, ctx):
        if train_idx.size == 0:
            empty = np.empty((0, X.shape[1]))
            return empty, np.empty(0, dtype=int), np.empty(0), None
        p = model_pd.predict_pd(kgb, X[train_idx])
        pseudo = (p >= ctx.policy_threshold).astype(int)
        weights = np.ones(train_idx.size)
        return X[train_idx], pseudo, weights, None


class AugmentationCorrector(RejectInferenceCorrector):
    """Score-band augmentation (a.k.a. reweighting): reweight ACCEPTED rows by the
    inverse of their KGB-score band's empirical acceptance rate, so the weighted
    accepted sample represents the full through-the-door population.

    Distinct from :class:`cldd.correctors.IPWReweightCorrector`, which fits a
    continuous propensity *classifier* ``P(approved | features)``. Augmentation
    instead bins by the KGB risk *score* and uses each band's empirical
    accepted/total ratio (the classic credit-scoring construction). It adds no
    declined rows to training; it uses declined *features* only to count band totals.
    """

    name = "augmentation"

    def _augment(self, X, y_approved, kgb, approved, train_idx, ctx):
        p = model_pd.predict_pd(kgb, X)
        bands = _score_bands(p, config.RI_SCORE_BANDS)
        approved_w = np.ones(int(approved.sum()))
        band_of_approved = bands[approved]
        for b in range(config.RI_SCORE_BANDS):
            total = int((bands == b).sum())
            if total == 0:
                continue
            acc_rate = float((approved & (bands == b)).sum()) / total
            acc_rate = float(np.clip(acc_rate, _RATE_CLIP[0], _RATE_CLIP[1]))
            approved_w[band_of_approved == b] = 1.0 / acc_rate
        empty = np.empty((0, X.shape[1]))
        return empty, np.empty(0, dtype=int), np.empty(0), approved_w


class FuzzyAugmentationCorrector(RejectInferenceCorrector):
    """Fuzzy augmentation: each declined-fold applicant enters training TWICE — as
    a good (label 0, weight ``1 - p``) and a bad (label 1, weight ``p``) record,
    where ``p`` is the KGB-predicted PD. No hard label is ever assigned."""

    name = "fuzzy_augmentation"

    def _augment(self, X, y_approved, kgb, approved, train_idx, ctx):
        if train_idx.size == 0:
            empty = np.empty((0, X.shape[1]))
            return empty, np.empty(0, dtype=int), np.empty(0), None
        Xd = X[train_idx]
        p = model_pd.predict_pd(kgb, Xd)
        extra_X = np.vstack([Xd, Xd])
        extra_y = np.concatenate([np.ones(train_idx.size, dtype=int), np.zeros(train_idx.size, dtype=int)])
        extra_w = np.concatenate([p, 1.0 - p])
        return extra_X, extra_y, extra_w, None


class ParcellingCorrector(RejectInferenceCorrector):
    """Parcelling: bin the declined fold by KGB score; within each band assign a
    bad label with probability ``min(accepted_band_bad_rate * RI_PARCEL_FACTOR, 1)``
    (the uplift encodes that declines are riskier than look-alike accepts), drawn
    from a dedicated seeded RNG stream so the labels are deterministic."""

    name = "parcelling"

    def _augment(self, X, y_approved, kgb, approved, train_idx, ctx):
        if train_idx.size == 0:
            empty = np.empty((0, X.shape[1]))
            return empty, np.empty(0, dtype=int), np.empty(0), None
        p_all = model_pd.predict_pd(kgb, X)
        bands = _score_bands(p_all, config.RI_SCORE_BANDS)
        overall_bad = float(np.mean(y_approved)) if y_approved.size else 0.0

        band_target = np.full(config.RI_SCORE_BANDS, overall_bad)
        band_of_approved = bands[approved]
        for b in range(config.RI_SCORE_BANDS):
            in_band = band_of_approved == b
            if in_band.any():
                band_target[b] = float(np.mean(y_approved[in_band]))
        band_target = np.clip(band_target * config.RI_PARCEL_FACTOR, 0.0, 1.0)

        bands_train = bands[train_idx]
        rng = np.random.default_rng([ctx.seed, ctx.iteration, config.RI_PARCEL_STREAM])
        draws = rng.random(train_idx.size)
        pseudo = (draws < band_target[bands_train]).astype(int)
        weights = np.ones(train_idx.size)
        return X[train_idx], pseudo, weights, None
