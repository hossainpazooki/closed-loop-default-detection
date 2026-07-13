"""Multi-seed counterfactual sweep: the committed driver behind the 5-seed
certification quoted in docs/assessment.md.

Runs run_counterfactual_eval for each (seed, severity) in ONE SUBPROCESS PER
EVAL -- two evals in a single process have been observed to exhaust memory --
and writes artifacts/seed_sweep.csv plus a mean +/- sd summary, so the headline
numbers are recomputable from a committed source rather than quoted prose.

Usage:
    python scripts/run_seed_sweep.py            # default seeds/severities
    python scripts/run_seed_sweep.py --quick    # seed 42 only (smoke)
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

import pandas as pd

SEEDS = [7, 13, 42, 101, 2026]
SEVERITIES = [0.4, 1.0]

_CHILD = """\
import json
from cldd.counterfactual import run_counterfactual_eval
r = run_counterfactual_eval(selection_severity={sev}, seed={seed})
print(json.dumps({{
    "seed": {seed}, "severity": {sev},
    "naive_mae": r.naive_mae, "gcomp_mae": r.gcomp_mae,
    "naive_bias": r.naive_bias, "gcomp_bias": r.gcomp_bias,
    "naive_strong": r.naive_mae_strong_propagation,
    "gcomp_strong": r.gcomp_mae_strong_propagation,
    "strong_gap": r.naive_mae_strong_propagation - r.gcomp_mae_strong_propagation,
    "overall_gap": r.naive_mae - r.gcomp_mae,
}}))
"""


def run_one(seed: int, sev: float) -> dict:
    out = subprocess.run(
        [sys.executable, "-c", _CHILD.format(seed=seed, sev=sev)],
        capture_output=True, text=True, check=True,
    )
    return json.loads(out.stdout.strip().splitlines()[-1])


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--quick", action="store_true", help="seed 42 only (smoke)")
    args = ap.parse_args()
    seeds = [42] if args.quick else SEEDS

    rows = []
    for sev in SEVERITIES:
        for seed in seeds:
            print(f"running seed={seed} severity={sev} ...", flush=True)
            rows.append(run_one(seed, sev))

    df = pd.DataFrame(rows)
    out = Path(__file__).resolve().parents[1] / "artifacts" / "seed_sweep.csv"
    df.to_csv(out, index=False)
    print(f"\nwrote {out}  ({len(df)} rows)")

    for sev in SEVERITIES:
        d = df[df["severity"] == sev]
        if d.empty:
            continue
        g = d["strong_gap"]
        flips = d.loc[g <= 0, "seed"].tolist()
        print(
            f"severity {sev}: strong-prop gap mean={g.mean():+.4f} sd={g.std(ddof=1):.4f} "
            f"(naive {d['naive_strong'].mean():.4f}+/-{d['naive_strong'].std(ddof=1):.4f} vs "
            f"gcomp {d['gcomp_strong'].mean():.4f}+/-{d['gcomp_strong'].std(ddof=1):.4f}); "
            f"positive {int((g > 0).sum())}/{len(g)} seeds"
            + (f"; SIGN FLIPS on seeds {flips}" if flips else "")
        )


if __name__ == "__main__":
    main()
