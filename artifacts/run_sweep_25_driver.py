"""One-off driver: scale seed sweep to 25 seeds (20 new seeds x 2 severities).

Identical method to scripts/run_seed_sweep.py: one subprocess per eval,
strictly sequential, same _CHILD fields, default eval parameters.
Appends each finished row to artifacts/seed_sweep_25.csv so partial
progress survives; resumable (skips (seed, severity) pairs already present).
Does NOT touch artifacts/seed_sweep.csv.
"""
from __future__ import annotations

import csv
import json
import subprocess
import sys
from pathlib import Path

NEW_SEEDS = [3, 5, 11, 17, 19, 23, 29, 31, 37, 41,
             43, 47, 53, 59, 61, 67, 71, 73, 79, 83]
SEVERITIES = [0.4, 1.0]

FIELDS = ["seed", "severity", "naive_mae", "gcomp_mae", "naive_bias",
          "gcomp_bias", "naive_strong", "gcomp_strong", "strong_gap",
          "overall_gap"]

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

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "artifacts" / "seed_sweep_25.csv"


def run_one(seed: int, sev: float) -> dict:
    out = subprocess.run(
        [sys.executable, "-c", _CHILD.format(seed=seed, sev=sev)],
        capture_output=True, text=True, check=True,
    )
    return json.loads(out.stdout.strip().splitlines()[-1])


def done_pairs() -> set:
    if not OUT.exists():
        return set()
    with OUT.open(newline="") as f:
        return {(int(r["seed"]), float(r["severity"])) for r in csv.DictReader(f)}


def append_row(row: dict) -> None:
    new_file = not OUT.exists()
    with OUT.open("a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        if new_file:
            w.writeheader()
        w.writerow({k: row[k] for k in FIELDS})


def main() -> None:
    done = done_pairs()
    for sev in SEVERITIES:
        for seed in NEW_SEEDS:
            if (seed, sev) in done:
                print(f"skip seed={seed} severity={sev} (already done)", flush=True)
                continue
            print(f"running seed={seed} severity={sev} ...", flush=True)
            row = run_one(seed, sev)
            append_row(row)
            print(f"  strong_gap={row['strong_gap']:+.4f}", flush=True)
    print("ALL 40 NEW EVALS COMPLETE", flush=True)


if __name__ == "__main__":
    main()
