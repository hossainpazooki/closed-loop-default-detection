"""Exploration-budget sweep: what does buying labels do to the operating frontier?

    python scripts/run_exploration_sweep.py [--quick]

Lesson behind it (docs/assessment.md): beyond severity 0.4 the unobserved confounder
defeats every observational correction — IPW and g-computation fail for the
same structural reason. Exploration (randomly approving an eps-fraction of
declines) is the one lever that buys *identification* instead of reweighting:
its labeled-propensities are known exactly, so no fitted propensity model — and
nothing the confounder can distort — stands between the explored labels and the
correction.

Runs ``SelectiveLabelsLoop(improve_mode="reweight", generator="scm",
exploration_rate=eps)`` for eps in {0, 0.02, 0.05, 0.10} x seeds {7, 42, 2026}
and writes every round to ``artifacts/exploration_frontier.csv``: hidden
declined-ECE for the IPW and exploration levers side by side, the labels bought
and defaults incurred (both observable to a real lender), and the observable
positivity flag. ASCII-only output (Windows console).
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pandas as pd  # noqa: E402

from cldd import SelectiveLabelsLoop, config  # noqa: E402

EPS_GRID = [0.0, 0.02, 0.05, 0.10]
SEEDS = [7, 42, 2026]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--quick", action="store_true", help="seed 42 only (smoke)")
    args = ap.parse_args()
    seeds = [42] if args.quick else SEEDS

    rows = []
    for seed in seeds:
        for eps in EPS_GRID:
            print(f"running seed={seed} eps={eps} ...", flush=True)
            res = SelectiveLabelsLoop(
                improve_mode="reweight", generator="scm", seed=seed, exploration_rate=eps
            ).run()
            for r in res.rounds:
                rows.append(
                    {
                        "seed": seed,
                        "exploration_rate": eps,
                        "selection_severity": r.selection_severity,
                        "control_declined_ece": round(r.control_metric, 4),
                        "ipw_declined_ece": round(r.reweight.declined_ece, 4),
                        "explore_declined_ece": (
                            round(r.explore.declined_ece, 4) if r.explore else None
                        ),
                        "n_explored": r.n_explored,
                        "explored_defaults": r.explored_defaults,
                        # v2: the exploration budget priced in dollars (cldd.emp
                        # economics on the planted rows). Positive = the bought
                        # labels cost money net. Reported, never a gate input.
                        "exploration_cost": round(r.exploration_cost, 2),
                        "diag_flagged": r.diagnostics.flagged,
                        "passed": r.passed,
                        "frontier": res.frontier_severity,
                    }
                )

    df = pd.DataFrame(rows)
    config.ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
    out = config.ARTIFACTS_DIR / "exploration_frontier.csv"
    df.to_csv(out, index=False)
    print(f"\nwrote {out}  ({len(df)} rows)")

    print("\nfrontier by exploration budget (scm world):")
    print(f"{'seed':>6} " + " ".join(f"eps={e:<5}" for e in EPS_GRID))
    for seed in seeds:
        d = df[df["seed"] == seed]
        fr = [d[d["exploration_rate"] == e]["frontier"].iloc[0] for e in EPS_GRID]
        print(f"{seed:>6} " + " ".join(f"{str(f):<9}" for f in fr))
    print(
        "\nNote: at small budgets the exploration estimate is high-variance (tens of"
        "\nbought labels carry the whole declined population), so its frontier can sit"
        "\nBELOW the IPW frontier inside the IPW-valid regime. The lever's value is"
        "\nbeyond that regime, where no observational correction is identified."
    )


if __name__ == "__main__":
    main()
