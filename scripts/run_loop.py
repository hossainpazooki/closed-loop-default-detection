"""Driver: run the closed loop and emit the operating-frontier evidence.

    python scripts/run_loop.py [--generator {flat,scm}]

Runs ``SelectiveLabelsLoop(improve_mode="both")``, writes
``artifacts/loop_frontier.csv`` and ``artifacts/loop_frontier.png`` (or
``loop_frontier_scm.csv`` / ``loop_frontier_scm.png`` with ``--generator scm``,
so the flat artifacts are never overwritten), and prints a short summary of
where the frontier landed and why.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")  # headless: write PNGs without a display
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402

# Allow running as a plain script (no install) by putting src/ on the path.
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from cldd import SelectiveLabelsLoop, config  # noqa: E402


def _rows(result) -> list[dict]:
    rows = []
    for r in result.rounds:
        row = {
            "iteration": r.iteration,
            "selection_severity": r.selection_severity,
            "base_rate": round(r.base_rate, 4),
            "approval_rate": round(r.approval_rate, 4),
            "naive_declined_ece": round(r.naive.declined_ece, 4),
            "naive_declined_mean_pd": round(r.naive.declined_mean_pd, 4),
            "naive_declined_base_rate": round(r.naive.declined_base_rate, 4),
            "naive_declined_auc": round(r.naive.declined_auc, 4),
            "control_metric": round(r.control_metric, 4),
            "passed": r.passed,
        }
        if r.reweight is not None:
            row["reweight_declined_ece"] = round(r.reweight.declined_ece, 4)
            row["reweight_declined_mean_pd"] = round(r.reweight.declined_mean_pd, 4)
        if r.retrain is not None:
            row["retrain_declined_ece"] = round(r.retrain.declined_ece, 4)
            row["retrain_train_seed"] = r.retrain_train_seed
        if r.explore is not None:
            row["explore_declined_ece"] = round(r.explore.declined_ece, 4)
            row["n_explored"] = r.n_explored
            row["explored_defaults"] = r.explored_defaults
        if r.diagnostics is not None:
            # Observable-only positivity diagnostics (no declined labels needed).
            row["diag_propensity_auc"] = round(r.diagnostics.propensity_auc, 4)
            row["diag_ess_ratio"] = round(r.diagnostics.ess_ratio, 4)
            row["diag_below_floor"] = round(r.diagnostics.unfunded_below_floor, 4)
            row["diag_flagged"] = r.diagnostics.flagged
        rows.append(row)
    return rows


def _plot(df: pd.DataFrame, target_ece: float, out_path: Path) -> None:
    fig, ax = plt.subplots(figsize=(8, 5))
    ax.plot(df["selection_severity"], df["naive_declined_ece"], marker="o", label="naive (train-on-approved)")
    if "reweight_declined_ece" in df:
        ax.plot(df["selection_severity"], df["reweight_declined_ece"], marker="s", label="IPW reweight")
    if "retrain_declined_ece" in df:
        ax.plot(df["selection_severity"], df["retrain_declined_ece"], marker="^", label="retrain (disjoint)")
    if "explore_declined_ece" in df:
        ax.plot(df["selection_severity"], df["explore_declined_ece"], marker="D", label="exploration (bought labels)")
    ax.axhline(target_ece, color="grey", linestyle="--", label=f"target ECE = {target_ece}")
    ax.set_xlabel("selection severity  (0 = random approval, 1 = approval tracks true risk)")
    ax.set_ylabel("declined-subpopulation calibration error (ECE)")
    ax.set_title("Operating frontier: PD calibration on the applicants real data can't score")
    ax.legend()
    fig.tight_layout()
    fig.savefig(out_path, dpi=120)
    plt.close(fig)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the selective-labels closed loop.")
    parser.add_argument(
        "--generator",
        choices=("flat", "scm"),
        default="flat",
        help="cohort generator: 'flat' = single-layer synthetic (default), "
        "'scm' = fitted layered SCM (writes *_scm artifacts, never the flat ones)",
    )
    parser.add_argument(
        "--exploration-rate",
        type=float,
        default=0.0,
        help="randomly approve this fraction of declines to buy labels (adds the "
        "exploration lever; 0 = off, the committed-artifact default)",
    )
    args = parser.parse_args()

    config.ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)

    loop = SelectiveLabelsLoop(
        improve_mode="both", generator=args.generator, exploration_rate=args.exploration_rate
    )
    result = loop.run()

    df = pd.DataFrame(_rows(result))
    suffix = "_scm" if args.generator == "scm" else ""
    csv_path = config.ARTIFACTS_DIR / f"loop_frontier{suffix}.csv"
    png_path = config.ARTIFACTS_DIR / f"loop_frontier{suffix}.png"
    df.to_csv(csv_path, index=False)
    _plot(df, result.target_declined_ece, png_path)

    print(df.to_string(index=False))
    print()
    print(f"Generator: {args.generator}"
          + (" (structural SCM — artifacts written to the *_scm files, flat artifacts untouched)"
             if args.generator == "scm" else " (single-layer synthetic)"))
    frontier = result.frontier_severity
    best = result.best_round
    print(f"Operating frontier (highest passing severity): {frontier}")
    if best is not None:
        print(f"Best round: severity={best.selection_severity}, declined ECE={best.control_metric:.4f}")
    print()
    print("Reading:")
    if frontier is None:
        print("  - Even at the mildest selection regime the model failed the calibration target;")
        print("    the declined subpopulation is mis-scored from the start (see naive_declined_mean_pd).")
    else:
        print(f"  - Under selection on observed features, IPW reweighting holds calibration on the")
        print(f"    *unobserved* declined population out to severity {frontier}. Beyond it, selection")
        print(f"    leaks through an unobserved confounder that propensity reweighting cannot reach —")
        print(f"    the honest limit of an observational correction, and what we'd flag to a regulator.")
    print(f"  - Artifacts: {csv_path}  and  {png_path}")


if __name__ == "__main__":
    main()
