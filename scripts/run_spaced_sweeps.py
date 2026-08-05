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

``--out-suffix NAME`` (added 2026-08-04, v4 spec Amendment Rev 1.1) re-runs the
identical configurations into ``*_NAME.csv`` instead, plus an environment
manifest ``artifacts/surface_env.json``. It exists because the v4 surface's I-1
byte-identity embed gate compares against these artifacts, and the 2026-07-29
originals were produced under an interpreter build that no longer exists on this
machine (same pins, different compiled wheels -> last-ulp drift). The re-run
deliberately reuses THIS driver's child code so a re-implementation cannot
paper over a real plumbing bug. Default (empty suffix) behavior is unchanged,
and the 2026-07-29 originals are never touched or superseded.

Usage:
    python scripts/run_spaced_sweeps.py                       # both sweeps
    python scripts/run_spaced_sweeps.py --part counterfactual # cheaper sweep only
    python scripts/run_spaced_sweeps.py --part frontier
    python scripts/run_spaced_sweeps.py --out-suffix v4env    # I-1 re-baseline
"""
from __future__ import annotations

import argparse
import csv
import json
import platform
import subprocess
import sys
from pathlib import Path

SEEDS = [1000 + 16 * i for i in range(25)]  # 1000, 1016, ..., 1384
SEVERITIES = [0.4, 1.0]
GENERATORS = ("flat", "scm")

ROOT = Path(__file__).resolve().parents[1]
CF_OUT = ROOT / "artifacts" / "seed_sweep_spaced.csv"
FR_OUT = ROOT / "artifacts" / "frontier_sweep_spaced.csv"
ENV_MANIFEST = ROOT / "artifacts" / "surface_env.json"

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


def _suffixed(path: Path, suffix: str) -> Path:
    """artifacts/x.csv + 'v4env' -> artifacts/x_v4env.csv; empty suffix = unchanged."""
    return path if not suffix else path.with_name(f"{path.stem}_{suffix}{path.suffix}")


def write_env_manifest(out: Path = ENV_MANIFEST) -> dict:
    """Record the build environment a baseline was produced in.

    The absence of exactly this file is what made the 2026-07-29 baseline
    unreproducible: the pins were recorded, the interpreter build was not.
    """
    import numpy
    import sklearn

    manifest = {
        "python_implementation": platform.python_implementation(),
        "python_version": platform.python_version(),
        "python_build": list(platform.python_build()),
        "platform": platform.platform(),
        "machine": platform.machine(),
        "numpy": numpy.__version__,
        "scikit_learn": sklearn.__version__,
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    print(f"environment manifest -> {out}", flush=True)
    for k, v in sorted(manifest.items()):
        print(f"  {k}: {v}", flush=True)
    return manifest


def run_counterfactual(out: Path = CF_OUT) -> None:
    done = set()
    if out.exists():
        with out.open(newline="") as f:
            done = {(int(r["seed"]), float(r["severity"])) for r in csv.DictReader(f)}
    for sev in SEVERITIES:
        for seed in SEEDS:
            if (seed, sev) in done:
                print(f"skip seed={seed} severity={sev} (already done)", flush=True)
                continue
            print(f"running counterfactual seed={seed} severity={sev} ...", flush=True)
            row = _run_child(_CF_CHILD.format(seed=seed, sev=sev))[-1]
            _append(out, CF_FIELDS, row)
            print(f"  strong_gap={row['strong_gap']:+.4f}", flush=True)
    print(f"counterfactual sweep complete -> {out}", flush=True)


def run_frontier(out: Path = FR_OUT) -> None:
    done = set()
    if out.exists():
        with out.open(newline="") as f:
            done = {(int(r["seed"]), r["generator"]) for r in csv.DictReader(f)}
    for generator in GENERATORS:
        for seed in SEEDS:
            if (seed, generator) in done:
                print(f"skip seed={seed} generator={generator} (already done)", flush=True)
                continue
            print(f"running frontier seed={seed} generator={generator} ...", flush=True)
            rows = _run_child(_FR_CHILD.format(seed=seed, generator=generator))
            for row in rows:
                _append(out, FR_FIELDS, row)
            frontier = rows[-1]["frontier_severity"] if rows else None
            print(f"  {len(rows)} rounds, frontier_severity={frontier}", flush=True)
    print(f"frontier sweep complete -> {out}", flush=True)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--part", choices=("counterfactual", "frontier", "both"),
                    default="both")
    ap.add_argument(
        "--out-suffix", default="",
        help=(
            "write to artifacts/*_SUFFIX.csv + an environment manifest instead of "
            "the 2026-07-29 originals (v4 spec Amendment Rev 1.1); the originals "
            "are never touched"
        ),
    )
    args = ap.parse_args()
    cf_out = _suffixed(CF_OUT, args.out_suffix)
    fr_out = _suffixed(FR_OUT, args.out_suffix)
    if args.out_suffix:
        write_env_manifest()
    if args.part in ("counterfactual", "both"):
        run_counterfactual(cf_out)
    if args.part in ("frontier", "both"):
        run_frontier(fr_out)
    print("SPACED SWEEPS COMPLETE", flush=True)


if __name__ == "__main__":
    main()
