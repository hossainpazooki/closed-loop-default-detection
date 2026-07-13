"""Deployable positivity/overlap diagnostics — the observable frontier signal.

Lesson from the accompanying article (docs/assessment.md): the operating frontier was measured
against *planted* truth (declined-cohort ECE), which a real lender can never
compute — so the frontier, as measured, is not deployable knowledge. What a
lender CAN compute is how pathological the selection itself looks:

* **propensity separability** — fit P(funded | features) and take its in-sample
  AUC. Near 0.5 the funded and unfunded pools overlap (IPW has support to work
  with); near 1.0 the policy is deterministic in the features and positivity is
  gone by construction.
* **IPW weight degeneracy** — the effective sample size of the 1/propensity
  weights actually used by the reweight lever, as a fraction of the funded count.
  When a few rows carry all the weight, the "corrected" estimate is resting on
  almost no data.
* **unreachable region** — the share of unfunded rows whose propensity sits at
  or below the clip floor: the part of the declined population the funded sample
  cannot speak for at all.

None of these need a single declined-row label. The harness validates them
against the hidden truth (see ``test_diagnostics`` and the frontier artifacts):
inside the measured frontier they look healthy, beyond it they deteriorate — so
a real deployment can use them as an abstention trigger where this harness used
planted ground truth.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from sklearn.metrics import roc_auc_score

from . import config, model_pd


@dataclass(frozen=True)
class PositivityDiagnostics:
    """Observable-only overlap health for one cohort's funding selection."""

    #: In-sample AUC of P(funded | features). ~0.5 = overlapping pools,
    #: ~1.0 = selection deterministic in the features (positivity broken).
    propensity_auc: float
    #: Effective sample size of the clipped 1/propensity weights on funded rows,
    #: divided by the funded count. 1.0 = uniform weights; small = degenerate.
    ess_ratio: float
    #: Share of unfunded rows with raw propensity <= the clip floor — the region
    #: the funded sample cannot represent.
    unfunded_below_floor: float
    #: Observable abstention signal: True when any component crosses its
    #: configured threshold (calibrated on this harness — see config).
    flagged: bool


def positivity_diagnostics(
    X,
    funded,
    *,
    random_state: int | None = None,
    clip: tuple[float, float] = (0.05, 0.95),
    auc_max: float | None = None,
    ess_min: float | None = None,
    below_floor_max: float | None = None,
) -> PositivityDiagnostics:
    """Compute observable positivity diagnostics for a funding selection.

    Mirrors :func:`cldd.model_pd.selection_adjusted_weights` (same classifier,
    same clip) so the ESS describes the weights the IPW lever would actually use.
    Thresholds default to the config values; pass overrides for sweeps.
    """
    X = np.asarray(X, dtype=float)
    funded = np.asarray(funded).astype(bool)
    rs = config.RANDOM_SEED if random_state is None else random_state
    auc_max = config.DIAG_PROPENSITY_AUC_MAX if auc_max is None else auc_max
    ess_min = config.DIAG_ESS_RATIO_MIN if ess_min is None else ess_min
    below_floor_max = (
        config.DIAG_UNFUNDED_BELOW_FLOOR_MAX if below_floor_max is None else below_floor_max
    )

    n_funded = int(funded.sum())
    n_unfunded = int((~funded).sum())
    if n_funded == 0 or n_unfunded == 0:
        # Degenerate selection: nothing to compare against — abstain.
        return PositivityDiagnostics(
            propensity_auc=float("nan"),
            ess_ratio=float("nan"),
            unfunded_below_floor=float("nan"),
            flagged=True,
        )

    clf = model_pd._new_classifier(rs)
    clf.fit(X, funded.astype(int))
    propensity = clf.predict_proba(X)[:, 1]

    auc = float(roc_auc_score(funded.astype(int), propensity))
    below_floor = float((propensity[~funded] <= clip[0]).mean())

    w = 1.0 / np.clip(propensity[funded], clip[0], clip[1])
    ess_ratio = float((w.sum() ** 2) / (w**2).sum() / n_funded)

    flagged = (auc > auc_max) or (ess_ratio < ess_min) or (below_floor > below_floor_max)
    return PositivityDiagnostics(
        propensity_auc=auc,
        ess_ratio=ess_ratio,
        unfunded_below_floor=below_floor,
        flagged=bool(flagged),
    )
