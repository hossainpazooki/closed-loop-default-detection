"""Frontier seed sweep: run the closed loop itself across seeds/generators.

    python scripts/run_frontier_sweep.py [--generator {flat,scm,both}]
    python scripts/run_frontier_sweep.py --quick     # seed 42, flat only (smoke)

Unlike ``scripts/run_seed_sweep.py`` / ``artifacts/run_sweep_25_driver.py`` (which
sweep ``run_counterfactual_eval``, a single-cohort eval, not the loop), this is the
first **loop-level** sweep: each ``SelectiveLabelsLoop(...).run()`` walks the
severity grid itself and reports where its own operating frontier landed, plus the
v2 EMP columns, for every round along the way.

The 25-seed set is the *counterfactual* sweep's -- {7, 13, 42, 101, 2026} from
``scripts/run_seed_sweep.py`` plus the 20 in ``artifacts/run_sweep_25_driver.py`` --
kept here only for comparability with that committed sweep, not because the loop
needs 25 independent draws.

Same subprocess discipline as those two scripts: ONE SUBPROCESS PER (seed,
generator) loop run (two loop runs in one process have been observed to exhaust
memory), strictly sequential, resumable append to ``artifacts/frontier_sweep.csv``
(skips (seed, generator) pairs already present).

Seed-overlap correlation caveat (documented, not fixed): ``SelectiveLabelsLoop``
seed ``s`` consumes generator seeds ``s``..``s+7`` (one per round, measure seeds
only -- see ``TRAIN_SEED_OFFSET`` for the disjoint retrain-train seeds). The
25-seed set has gaps smaller than 8 (e.g. 3 and 5, 11 and 13, 17 and 19), so
different rows in this sweep can share feature draws (same generator seed drawn at
a different severity by another row's loop run -> identical features, different
selection). No two rows duplicate a cohort (severity is iteration-locked within a
single loop run), but the 25 rows are **not fully independent** -- read the
frontier-severity distribution below with that in mind.
"""
from __future__ import annotations

import argparse
import csv
import json
import subprocess
import sys
from pathlib import Path

SEEDS = [7, 13, 42, 101, 2026] + [
    3, 5, 11, 17, 19, 23, 29, 31, 37, 41, 43, 47, 53, 59, 61, 67, 71, 73, 79, 83,
]
GENERATORS = ("flat", "scm")

FIELDS = [
    "seed", "generator", "iteration", "selection_severity", "frontier_severity",
    "passed", "naive_declined_ece", "reweight_declined_ece", "retrain_declined_ece",
    "naive_declined_empc", "naive_declined_emp_h", "reweight_declined_empc",
    "reweight_declined_emp_h", "exploration_cost",
]

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "artifacts" / "frontier_sweep.csv"

# One JSON line per ROUND of the loop run (not one line per run) -- the parent
# appends every round as its own CSV row.
_CHILD = """\
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


def run_one(seed: int, generator: str) -> list[dict]:
    """One subprocess per (seed, generator) loop run; returns one dict per round."""
    out = subprocess.run(
        [sys.executable, "-c", _CHILD.format(seed=seed, generator=generator)],
        capture_output=True, text=True, check=True,
    )
    return [json.loads(line) for line in out.stdout.strip().splitlines() if line]


def done_pairs() -> set:
    if not OUT.exists():
        return set()
    with OUT.open(newline="") as f:
        return {(int(r["seed"]), r["generator"]) for r in csv.DictReader(f)}


def append_row(row: dict) -> None:
    new_file = not OUT.exists()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        if new_file:
            w.writeheader()
        w.writerow({k: row[k] for k in FIELDS})


def _summarize(generators) -> None:
    if not OUT.exists():
        print("no rows written; nothing to summarize.")
        return
    with OUT.open(newline="") as f:
        all_rows = list(csv.DictReader(f))
    for generator in generators:
        # One frontier_severity per (seed, generator) run -- constant across a
        # run's rounds, so collapse by seed before taking the distribution.
        by_seed = {}
        for r in all_rows:
            if r["generator"] != generator:
                continue
            by_seed[int(r["seed"])] = r["frontier_severity"]
        values = sorted(float(v) for v in by_seed.values() if v not in ("", "None"))
        if not values:
            print(f"{generator}: no seed crossed the frontier (all failed at the mildest severity)")
            continue
        n = len(values)
        median = values[n // 2] if n % 2 else (values[n // 2 - 1] + values[n // 2]) / 2
        print(
            f"{generator}: frontier severity min={values[0]:.4f} median={median:.4f} "
            f"max={values[-1]:.4f}  (n={n} of {len(by_seed)} seeds crossed it at least once)"
        )


def main() -> None:
    ap = argparse.ArgumentParser(description="Sweep the closed loop's operating frontier across seeds/generators.")
    ap.add_argument(
        "--generator", choices=("flat", "scm", "both"), default="both",
        help="cohort generator(s) to sweep (default: both)",
    )
    ap.add_argument("--quick", action="store_true", help="seed 42, flat only (smoke)")
    args = ap.parse_args()

    if args.quick:
        seeds = [42]
        generators = ["flat"]
    else:
        seeds = SEEDS
        generators = list(GENERATORS) if args.generator == "both" else [args.generator]

    done = done_pairs()
    for generator in generators:
        for seed in seeds:
            if (seed, generator) in done:
                print(f"skip seed={seed} generator={generator} (already done)", flush=True)
                continue
            print(f"running seed={seed} generator={generator} ...", flush=True)
            rows = run_one(seed, generator)
            for row in rows:
                append_row(row)
            frontier = rows[-1]["frontier_severity"] if rows else None
            print(f"  {len(rows)} rounds, frontier_severity={frontier}", flush=True)

    print(f"\nwrote {OUT}", flush=True)
    _summarize(generators)


if __name__ == "__main__":
    main()
