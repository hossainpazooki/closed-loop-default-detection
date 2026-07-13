"""Reject-inference frontier: do the classic RI methods recover declined-cohort
calibration as selection severity rises?

    python scripts/run_reject_inference.py [--quick] [--n N]

Lesson behind it (docs/assessment.md + the reject-inference literature): reject inference
imputes/extrapolates labels for the declined applicants, but it can only correct
selection that the *observed* features explain. The harness routes part of the
selection through an unobserved confounder, so as severity rises every
observational RI method degrades for the same structural reason IPW does — and
at full severity nothing recovers calibration. The honest deliverable is the
graded comparison, not a winner: Kozodoi et al. find reject inference's lift is
modest and that fixing the *evaluation* bias matters more.

Every method is scored on the SAME held-out fold of the declines (so the table is
apples-to-apples), and all route their constructed training set through the same
``model_pd.train_pd_model`` the naive lever uses (so only the training-set
construction varies). Writes long-format ``artifacts/reject_inference_frontier.csv``
with declined-cohort ECE / AUC / Brier per (generator, seed, severity, method).
ASCII-only output (Windows console).
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from cldd import config, eval_default, model_pd  # noqa: E402
from cldd.correctors import CorrectorContext  # noqa: E402
from cldd.loop import make_generator  # noqa: E402
from cldd.reject_inference import (  # noqa: E402
    AugmentationCorrector,
    FuzzyAugmentationCorrector,
    ParcellingCorrector,
    ReclassificationCorrector,
    grade_on_declined_fold,
    split_declines,
)

GENERATORS = ["flat", "scm"]
SEEDS = [7, 42, 2026]
RI_METHODS = [
    ReclassificationCorrector(),
    AugmentationCorrector(),
    FuzzyAugmentationCorrector(),
    ParcellingCorrector(),
]


def _severity_grid() -> list[float]:
    grid, s = [], config.START_SEVERITY
    while s <= config.MAX_SEVERITY + 1e-9:
        grid.append(round(s, 4))
        s += config.SEVERITY_STEP
    return grid


def _row(generator, seed, severity, train_idx, eval_idx, method, m):
    return {
        "generator": generator,
        "seed": seed,
        "selection_severity": severity,
        "n_train_declines": int(train_idx.size),
        "n_eval_declines": int(eval_idx.size),
        "method": method,
        "declined_ece": round(m.declined_ece, 4),
        "declined_auc": round(m.declined_auc, 4),
        "declined_brier": round(m.declined_brier, 4),
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--quick", action="store_true", help="flat world, seed 42 only (smoke)")
    ap.add_argument("--n", type=int, default=3000, help="applicants per cohort")
    args = ap.parse_args()
    generators = ["flat"] if args.quick else GENERATORS
    seeds = [42] if args.quick else SEEDS

    rows = []
    for generator in generators:
        for seed in seeds:
            for severity in _severity_grid():
                print(f"running generator={generator} seed={seed} severity={severity} ...", flush=True)
                cohort = make_generator(
                    generator, severity=severity, seed=seed,
                    n_applicants=args.n, approval_rate=config.DEFAULT_APPROVAL_RATE,
                ).generate_cohort()
                approved = np.asarray(cohort["approved"], dtype=bool)
                train_idx, eval_idx = split_declines(approved, seed=seed, iteration=0)
                ctx = CorrectorContext(
                    seed=seed, policy_threshold=config.POLICY_PD_THRESHOLD,
                    severity=severity, iteration=0, exploration_rate=0.0,
                    make_train_cohort=lambda: (cohort, seed),
                )

                # Baselines, scored on the SAME held-out declined fold.
                naive = eval_default.fit_observed_model(cohort, random_state=seed)
                rows.append(_row(generator, seed, severity, train_idx, eval_idx, "naive",
                                 grade_on_declined_fold(naive, cohort, eval_idx, config.POLICY_PD_THRESHOLD)))
                X = cohort["features"].to_numpy(dtype=float)
                w = model_pd.selection_adjusted_weights(X, approved, random_state=seed)
                ipw = eval_default.fit_observed_model(cohort, sample_weight=w[approved], random_state=seed)
                rows.append(_row(generator, seed, severity, train_idx, eval_idx, "ipw",
                                 grade_on_declined_fold(ipw, cohort, eval_idx, config.POLICY_PD_THRESHOLD)))

                # Reject-inference methods.
                for ri in RI_METHODS:
                    out = ri.apply(cohort, ctx)
                    rows.append(_row(generator, seed, severity, train_idx, eval_idx, ri.name, out.metrics))

    df = pd.DataFrame(rows)
    config.ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
    out = config.ARTIFACTS_DIR / "reject_inference_frontier.csv"
    df.to_csv(out, index=False)
    print(f"\nwrote {out}  ({len(df)} rows)")

    # Mean held-out declined-ECE by method x severity (averaged over generators/seeds).
    print("\nmean held-out declined-ECE by method x severity (lower is better):")
    pivot = df.pivot_table(index="method", columns="selection_severity",
                           values="declined_ece", aggfunc="mean")
    order = ["naive", "ipw", "reclassification", "augmentation", "fuzzy_augmentation", "parcelling"]
    pivot = pivot.reindex([m for m in order if m in pivot.index])
    with pd.option_context("display.width", 200, "display.max_columns", 20):
        print(pivot.round(4).to_string())
    print(
        "\nRead it honestly: RI lift over naive is modest at best and can be negative;"
        "\nas severity rises the unobserved confounder defeats every observational"
        "\nmethod (positivity boundary), which is the frontier the harness exists to show."
    )


if __name__ == "__main__":
    main()
