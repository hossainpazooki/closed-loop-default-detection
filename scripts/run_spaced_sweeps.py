"""Spaced-seed rerun of the counterfactual and frontier sweeps (assessment III.2-1).

Assessment Part III critique 1: the committed 25-seed set behind
``artifacts/frontier_sweep.csv`` has inter-seed gaps smaller than the seeds a
loop run consumes, so its rows share feature draws and the distribution over
them is not fully independent. (The counterfactual sweep
``artifacts/seed_sweep_25.csv`` turned out NOT to share this defect — a
counterfactual run consumes only ``{s, s + TRAIN_SEED_OFFSET}``, and the old
set has no such collision; verified from source during this rerun. Its spaced
rerun is an independent replication, not a repair.) This driver re-runs both
sweeps on the v3 spaced set **{1000 + 16*i : i = 0..24}**: spacing 16 exceeds
every within-run consumption span, so no two runs *within the same generator
or severity cell* share any consumed seed. The same seed ACROSS cells stays
deliberately paired (severity does not alter stream consumption). New
artifacts:

    artifacts/seed_sweep_spaced.csv      (counterfactual eval; severities 0.4, 1.0)
    artifacts/frontier_sweep_spaced.csv  (loop-level frontier; generators flat, scm)

The committed originals are never touched. Same discipline as
``scripts/run_seed_sweep.py`` / ``artifacts/run_sweep_25_driver.py`` /
``scripts/run_frontier_sweep.py``: ONE SUBPROCESS PER EVAL (two evals in one
process have been observed to exhaust memory), strictly sequential, resumable
append (skips pairs already present in the output CSV).

Usage:
    python scripts/run_spaced_sweeps.py                       # both sweeps
    python scripts/run_spaced_sweeps.py --part counterfactual # cheaper sweep only
    python scripts/run_spaced_sweeps.py --part frontier
"""
from __future__ import annotations

import argparse
import csv
import json
import subprocess
import sys
from pathlib import Path

SEEDS = [1000 + 16 * i for i in range(25)]  # 1000, 1016, ..., 1384
SEVERITIES = [0.4, 1.0]
GENERATORS = ("flat", "scm")

ROOT = Path(__file__).resolve().parents[1]
CF_OUT = ROOT / "artifacts" / "seed_sweep_spaced.csv"
FR_OUT = ROOT / "artifacts" / "frontier_sweep_spaced.csv"

CF_FIELDS = ["seed", "severity", "naive_mae", "gcomp_mae", "naive_bias",
             "gcomp_bias", "naive_strong", "gcomp_strong", "strong_gap",
             "overall_gap"]

FR_FIELDS = [
    "seed", "generator", "iteration", "selection_severity", "frontier_severity",
    "passed", "naive_declined_ece", "reweight_declined_ece", "retrain_declined_ece",
    "naive_declined_empc", "naive_declined_emp_h", "reweight_declined_empc",
    "reweight_declined_emp_h", "exploration_cost",
]

_CF_CHILD = """\
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

_FR_CHILD = """\
import json
from cldd.loop import SelectiveLabelsLoop

loop = SelectiveLabelsLoop(improve_mode="both", generator={generator!r}, seed={seed})
result = loop.run()
frontier = result.frontier_severity
for r in result.rounds:
    row = {{
        "seed": {seed},
        "generator": {generator!r},
        "iteration": r.iteration,
        "selection_severity": r.selection_severity,
        "frontier_severity": frontier,
        "passed": r.passed,
        "naive_declined_ece": r.naive.declined_ece,
        "reweight_declined_ece": r.reweight.declined_ece if r.reweight is not None else None,
        "retrain_declined_ece": r.retrain.declined_ece if r.retrain is not None else None,
        "naive_declined_empc": r.naive.declined_empc,
        "naive_declined_emp_h": r.naive.declined_emp_h,
        "reweight_declined_empc": r.reweight.declined_empc if r.reweight is not None else None,
        "reweight_declined_emp_h": r.reweight.declined_emp_h if r.reweight is not None else None,
        "exploration_cost": r.exploration_cost,
    }}
    print(json.dumps(row))
"""


def _run_child(code: str) -> list[dict]:
    out = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True, text=True, check=True,
    )
    return [json.loads(line) for line in out.stdout.strip().splitlines() if line]


def _append(path: Path, fields: list[str], row: dict) -> None:
    new_file = not path.exists()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        if new_file:
            w.writeheader()
        w.writerow({k: row[k] for k in fields})


def run_counterfactual() -> None:
    done = set()
    if CF_OUT.exists():
        with CF_OUT.open(newline="") as f:
            done = {(int(r["seed"]), float(r["severity"])) for r in csv.DictReader(f)}
    for sev in SEVERITIES:
        for seed in SEEDS:
            if (seed, sev) in done:
                print(f"skip seed={seed} severity={sev} (already done)", flush=True)
                continue
            print(f"running counterfactual seed={seed} severity={sev} ...", flush=True)
            row = _run_child(_CF_CHILD.format(seed=seed, sev=sev))[-1]
            _append(CF_OUT, CF_FIELDS, row)
            print(f"  strong_gap={row['strong_gap']:+.4f}", flush=True)
    print(f"counterfactual sweep complete -> {CF_OUT}", flush=True)


def run_frontier() -> None:
    done = set()
    if FR_OUT.exists():
        with FR_OUT.open(newline="") as f:
            done = {(int(r["seed"]), r["generator"]) for r in csv.DictReader(f)}
    for generator in GENERATORS:
        for seed in SEEDS:
            if (seed, generator) in done:
                print(f"skip seed={seed} generator={generator} (already done)", flush=True)
                continue
            print(f"running frontier seed={seed} generator={generator} ...", flush=True)
            rows = _run_child(_FR_CHILD.format(seed=seed, generator=generator))
            for row in rows:
                _append(FR_OUT, FR_FIELDS, row)
            frontier = rows[-1]["frontier_severity"] if rows else None
            print(f"  {len(rows)} rounds, frontier_severity={frontier}", flush=True)
    print(f"frontier sweep complete -> {FR_OUT}", flush=True)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--part", choices=("counterfactual", "frontier", "both"),
                    default="both")
    args = ap.parse_args()
    if args.part in ("counterfactual", "both"):
        run_counterfactual()
    if args.part in ("frontier", "both"):
        run_frontier()
    print("SPACED SWEEPS COMPLETE", flush=True)


if __name__ == "__main__":
    main()
