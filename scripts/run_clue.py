"""Driver: run the closed loop and emit evidence for the Deliverable D writeup.

    python scripts/run_clue.py

Runs ``SelectiveLabelsLoop(improve_mode="both")``, writes
``artifacts/clue_frontier.csv`` and ``artifacts/clue_frontier.png``, and prints a
short summary suitable for pasting into the writeup's §3 (causal), §4
(calibration), and §5 (limitations).
"""

from __future__ import annotations

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
        rows.append(row)
    return rows


def _plot(df: pd.DataFrame, target_ece: float, out_path: Path) -> None:
    fig, ax = plt.subplots(figsize=(8, 5))
    ax.plot(df["selection_severity"], df["naive_declined_ece"], marker="o", label="naive (train-on-approved)")
    if "reweight_declined_ece" in df:
        ax.plot(df["selection_severity"], df["reweight_declined_ece"], marker="s", label="IPW reweight")
    if "retrain_declined_ece" in df:
        ax.plot(df["selection_severity"], df["retrain_declined_ece"], marker="^", label="retrain (disjoint)")
    ax.axhline(target_ece, color="grey", linestyle="--", label=f"target ECE = {target_ece}")
    ax.set_xlabel("selection severity  (0 = random approval, 1 = approval tracks true risk)")
    ax.set_ylabel("declined-subpopulation calibration error (ECE)")
    ax.set_title("Operating frontier: PD calibration on the applicants real data can't score")
    ax.legend()
    fig.tight_layout()
    fig.savefig(out_path, dpi=120)
    plt.close(fig)


def main() -> None:
    config.ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)

    loop = SelectiveLabelsLoop(improve_mode="both")
    result = loop.run()

    df = pd.DataFrame(_rows(result))
    csv_path = config.ARTIFACTS_DIR / "clue_frontier.csv"
    png_path = config.ARTIFACTS_DIR / "clue_frontier.png"
    df.to_csv(csv_path, index=False)
    _plot(df, result.target_declined_ece, png_path)

    print(df.to_string(index=False))
    print()
    frontier = result.frontier_severity
    best = result.best_round
    print(f"Operating frontier (highest passing severity): {frontier}")
    if best is not None:
        print(f"Best round: severity={best.selection_severity}, declined ECE={best.control_metric:.4f}")
    print()
    print("Writeup hook (Deliverable D sections 3/4/5):")
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
