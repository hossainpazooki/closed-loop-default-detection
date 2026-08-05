"""CLDD v4 Option A surface sweep (spec 2026-07-29, decision records 1-5).

Frontier leg: 6 strengths x {flat, scm} x 25 spaced seeds = 300 loop runs
  -> artifacts/surface_frontier.csv   (leading unobserved_strength + the
     frontier_sweep_spaced.csv schema)
Counterfactual leg (SCM only): anchor strengths {0.0, 0.55, 1.0} x severities
{0.4, 0.6, 0.8, 1.0} plus endpoint strengths {0.2, 0.4, 0.7} x {0.4, 1.0},
25 seeds each = 450 evals
  -> artifacts/surface_counterfactual.csv (leading unobserved_strength + the
     seed_sweep_spaced.csv schema)

Same discipline as scripts/run_spaced_sweeps.py: ONE SUBPROCESS PER RUN
(two runs in one process have been observed to exhaust memory), strictly
sequential, resumable append (skips keys already present in the output CSV),
ASCII-only stdout. The committed artifacts are never touched; the surface
writes only its own files. Rows go through the identical json -> csv.DictWriter
pipeline as the spaced driver so the default-strength cells are STRING-equal to
the spaced artifacts (the I-1 byte-identity embed gate in surface_stats.py
depends on this).

Usage:
    python scripts/run_surface_sweep.py --pilot        # ~1 min gate, run FIRST
    python scripts/run_surface_sweep.py                # full matrix (~3 h)
    python scripts/run_surface_sweep.py --part frontier
    python scripts/run_surface_sweep.py --part counterfactual

--pilot (spec 7): seed 1000 only -- loop runs {flat@0.7, scm@0.55, scm@0.0} +
counterfactual evals at (strength 0.55, sev 0.4) and (0.0, 0.4), written to
artifacts/surface_pilot/ (scratch, never committed, never the main CSVs).
Asserts mechanically, exiting non-zero on any failure:
  (a) I-1 in miniature: the default-strength rows are string-equal on every
      shared column with the v4env spaced baselines (spec Amendment Rev 1.1);
  (b) non-vacuity: the strength-0.0 SCM cohort has byte-identical features but
      different true_pd (the knob reaches exactly the confounder channel), and
      its round-0 loop metrics differ from the default-strength run's;
  (c) budget trip-wire: per-run wall time must stay under 60 s (~5x measured).
      Exceeding it means STOP and re-scope by spec revision, not silently
      shrink the grid.
"""
from __future__ import annotations

import argparse
import csv
import json
import subprocess
import sys
import time
from pathlib import Path

STRENGTHS = [0.0, 0.2, 0.4, 0.55, 0.7, 1.0]          # locked (decision 2)
SEEDS = [1000 + 16 * i for i in range(25)]           # locked (decision 5)
WORLDS = ("flat", "scm")
DEFAULT_STRENGTH = {"flat": 0.7, "scm": 0.55}

CF_ANCHOR_STRENGTHS = [0.0, 0.55, 1.0]               # locked (decision 3)
CF_ANCHOR_SEVERITIES = [0.4, 0.6, 0.8, 1.0]
CF_ENDPOINT_STRENGTHS = [0.2, 0.4, 0.7]
CF_ENDPOINT_SEVERITIES = [0.4, 1.0]

ROOT = Path(__file__).resolve().parents[1]
FR_OUT = ROOT / "artifacts" / "surface_frontier.csv"
CF_OUT = ROOT / "artifacts" / "surface_counterfactual.csv"
# I-1 embed references (spec Amendment Rev 1.1, 2026-08-04): the SAME spaced
# configurations re-run under THIS build environment. The 2026-07-29 originals
# (frontier_sweep_spaced.csv / seed_sweep_spaced.csv) are untouched and remain
# the basis of every published number; they cannot serve as a byte-identity
# reference here because they were produced by an interpreter build that no
# longer exists on this machine (same pins, different compiled wheels -> the
# mismatch is entirely in the last ulp). Provenance: artifacts/surface_env.json.
SPACED_FR = ROOT / "artifacts" / "frontier_sweep_spaced_v4env.csv"
SPACED_CF = ROOT / "artifacts" / "seed_sweep_spaced_v4env.csv"
ENV_MANIFEST = ROOT / "artifacts" / "surface_env.json"
PILOT_DIR = ROOT / "artifacts" / "surface_pilot"

# Shared schemas (spec 4): the spaced sweeps' fields, verbatim.
CF_FIELDS = ["seed", "severity", "naive_mae", "gcomp_mae", "naive_bias",
             "gcomp_bias", "naive_strong", "gcomp_strong", "strong_gap",
             "overall_gap"]
FR_FIELDS = [
    "seed", "generator", "iteration", "selection_severity", "frontier_severity",
    "passed", "naive_declined_ece", "reweight_declined_ece", "retrain_declined_ece",
    "naive_declined_empc", "naive_declined_emp_h", "reweight_declined_empc",
    "reweight_declined_emp_h", "exploration_cost",
]
SURF_FR_FIELDS = ["unobserved_strength"] + FR_FIELDS
SURF_CF_FIELDS = ["unobserved_strength"] + CF_FIELDS

# Budget trip-wire, re-based by spec Amendment Rev 1.1: this environment runs
# ~15x faster than the 2026-07-29 measurements the spec 4 budget was built on
# (loop 7-11 s, eval 15 s vs 150 s / 120 s). ~5x measured, so ordinary machine
# load cannot fire it while a regression to the old per-run cost would; a wire
# left 20x above actual detects nothing.
PILOT_LOOP_BUDGET_S = 60.0
PILOT_EVAL_BUDGET_S = 60.0


def frontier_cells() -> list:
    """(strength, world) cells of the frontier leg -- 12 cells x 25 seeds = 300."""
    return [(v, w) for v in STRENGTHS for w in WORLDS]


def cf_cells() -> list:
    """(strength, severity) cells of the CF leg -- 18 cells x 25 seeds = 450."""
    cells = [(v, s) for v in CF_ANCHOR_STRENGTHS for s in CF_ANCHOR_SEVERITIES]
    cells += [(v, s) for v in CF_ENDPOINT_STRENGTHS for s in CF_ENDPOINT_SEVERITIES]
    return cells


_FR_CHILD = """\
import json
from cldd.loop import SelectiveLabelsLoop

loop = SelectiveLabelsLoop(
    improve_mode="both", generator={generator!r}, seed={seed},
    generator_kwargs={{"unobserved_strength": {strength}}},
)
result = loop.run()
frontier = result.frontier_severity
for r in result.rounds:
    row = {{
        "unobserved_strength": {strength},
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

_CF_CHILD = """\
import json
from cldd.counterfactual import run_counterfactual_eval
r = run_counterfactual_eval(
    selection_severity={sev}, seed={seed}, unobserved_strength={strength}
)
print(json.dumps({{
    "unobserved_strength": {strength},
    "seed": {seed}, "severity": {sev},
    "naive_mae": r.naive_mae, "gcomp_mae": r.gcomp_mae,
    "naive_bias": r.naive_bias, "gcomp_bias": r.gcomp_bias,
    "naive_strong": r.naive_mae_strong_propagation,
    "gcomp_strong": r.gcomp_mae_strong_propagation,
    "strong_gap": r.naive_mae_strong_propagation - r.gcomp_mae_strong_propagation,
    "overall_gap": r.naive_mae - r.gcomp_mae,
}}))
"""


def _run_child(code: str) -> list:
    out = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True, text=True, check=True,
    )
    return [json.loads(line) for line in out.stdout.strip().splitlines() if line]


def _append(path: Path, fields: list, row: dict) -> None:
    new_file = not path.exists()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        if new_file:
            w.writeheader()
        w.writerow({k: row[k] for k in fields})


def _done_keys(path: Path, key_fn) -> set:
    if not path.exists():
        return set()
    with path.open(newline="") as f:
        return {key_fn(r) for r in csv.DictReader(f)}


def run_frontier(out: Path = FR_OUT) -> None:
    done = _done_keys(out, lambda r: (float(r["unobserved_strength"]), r["generator"], int(r["seed"])))
    total = len(frontier_cells()) * len(SEEDS)
    n = 0
    for strength, world in frontier_cells():
        for seed in SEEDS:
            n += 1
            key = (strength, world, seed)
            if key in done:
                print(f"[{n}/{total}] skip strength={strength} world={world} seed={seed}", flush=True)
                continue
            print(f"[{n}/{total}] loop strength={strength} world={world} seed={seed} ...", flush=True)
            rows = _run_child(_FR_CHILD.format(strength=strength, generator=world, seed=seed))
            for row in rows:
                _append(out, SURF_FR_FIELDS, row)
            frontier = rows[-1]["frontier_severity"] if rows else None
            print(f"  {len(rows)} rounds, frontier_severity={frontier}", flush=True)
    missing = _missing_frontier_keys(out)
    print(f"frontier leg complete -> {out} (missing keys: {len(missing)})", flush=True)


def run_cf(out: Path = CF_OUT) -> None:
    done = _done_keys(out, lambda r: (float(r["unobserved_strength"]), float(r["severity"]), int(r["seed"])))
    total = len(cf_cells()) * len(SEEDS)
    n = 0
    for strength, sev in cf_cells():
        for seed in SEEDS:
            n += 1
            key = (strength, sev, seed)
            if key in done:
                print(f"[{n}/{total}] skip strength={strength} sev={sev} seed={seed}", flush=True)
                continue
            print(f"[{n}/{total}] eval strength={strength} sev={sev} seed={seed} ...", flush=True)
            row = _run_child(_CF_CHILD.format(strength=strength, sev=sev, seed=seed))[-1]
            _append(out, SURF_CF_FIELDS, row)
            print(f"  strong_gap={row['strong_gap']:+.4f}", flush=True)
    missing = _missing_cf_keys(out)
    print(f"counterfactual leg complete -> {out} (missing keys: {len(missing)})", flush=True)


def _missing_frontier_keys(out: Path = FR_OUT) -> list:
    done = _done_keys(out, lambda r: (float(r["unobserved_strength"]), r["generator"], int(r["seed"])))
    return [(v, w, s) for v, w in frontier_cells() for s in SEEDS if (v, w, s) not in done]


def _missing_cf_keys(out: Path = CF_OUT) -> list:
    done = _done_keys(out, lambda r: (float(r["unobserved_strength"]), float(r["severity"]), int(r["seed"])))
    return [(v, sev, s) for v, sev in cf_cells() for s in SEEDS if (v, sev, s) not in done]


# --------------------------------------------------------------------------- #
# Pilot gate (spec 7) -- must pass BEFORE the matrix is launched
# --------------------------------------------------------------------------- #

def _rows_by_key(path: Path, key_fn) -> dict:
    with path.open(newline="") as f:
        rows = list(csv.DictReader(f))
    out: dict = {}
    for r in rows:
        out.setdefault(key_fn(r), []).append(r)
    return out


def _string_match(got_rows: list, ref_rows: list, fields: list, label: str) -> list:
    """String-equality on shared columns, row-by-row in iteration order."""
    problems: list = []
    if len(got_rows) != len(ref_rows):
        return [f"{label}: row count {len(got_rows)} != reference {len(ref_rows)}"]
    for i, (g, ref) in enumerate(zip(got_rows, ref_rows)):
        for f in fields:
            if g.get(f, "") != ref.get(f, ""):
                problems.append(f"{label} row {i} col {f}: {g.get(f)!r} != {ref.get(f)!r}")
    return problems


def run_pilot() -> int:
    print("PILOT GATE (spec 7) -- seed 1000 only", flush=True)
    seed = SEEDS[0]
    failures: list = []
    PILOT_DIR.mkdir(parents=True, exist_ok=True)
    fr_pilot = PILOT_DIR / "pilot_frontier.csv"
    cf_pilot = PILOT_DIR / "pilot_counterfactual.csv"
    for p in (fr_pilot, cf_pilot):
        if p.exists():
            p.unlink()   # pilot scratch only -- committed artifacts are never touched

    # (b1) non-vacuity, in-process: strength 0 changes true_pd and ONLY true_pd's
    # channel -- features stay byte-identical (u never enters feature values).
    print("non-vacuity: scm strength 0.0 vs default 0.55 cohorts ...", flush=True)
    sys.path.insert(0, str(ROOT / "src"))
    import numpy as np
    import pandas as pd
    from cldd.scm import StructuralBorrowerGenerator
    kw = dict(n_applicants=1000, selection_severity=0.4, seed=seed,
              independent_selection_noise=True)
    base = StructuralBorrowerGenerator(**kw).generate_cohort()
    zero = StructuralBorrowerGenerator(**kw, unobserved_strength=0.0).generate_cohort()
    try:
        pd.testing.assert_frame_equal(base["features"], zero["features"])
    except AssertionError:
        failures.append("non-vacuity: features moved -- knob leaks outside the confounder channel")
    if np.array_equal(base["true_pd"], zero["true_pd"]):
        failures.append("non-vacuity: true_pd identical at strength 0 -- knob does not reach the world")

    # loop pilot runs: (world, strength) at the defaults + the scm zero corner.
    loop_cells = [("flat", 0.7), ("scm", 0.55), ("scm", 0.0)]
    for world, strength in loop_cells:
        t0 = time.monotonic()
        print(f"loop pilot {world}@{strength} seed={seed} ...", flush=True)
        rows = _run_child(_FR_CHILD.format(strength=strength, generator=world, seed=seed))
        dt = time.monotonic() - t0
        for row in rows:
            _append(fr_pilot, SURF_FR_FIELDS, row)
        print(f"  {len(rows)} rounds in {dt:.0f} s", flush=True)
        if dt > PILOT_LOOP_BUDGET_S:
            failures.append(
                f"budget trip-wire: loop {world}@{strength} took {dt:.0f} s "
                f"> {PILOT_LOOP_BUDGET_S:.0f} s -- STOP, re-scope by spec revision"
            )

    # cf pilot runs.
    for strength, sev in [(0.55, 0.4), (0.0, 0.4)]:
        t0 = time.monotonic()
        print(f"cf pilot strength={strength} sev={sev} seed={seed} ...", flush=True)
        row = _run_child(_CF_CHILD.format(strength=strength, sev=sev, seed=seed))[-1]
        dt = time.monotonic() - t0
        _append(cf_pilot, SURF_CF_FIELDS, row)
        print(f"  strong_gap={row['strong_gap']:+.4f} in {dt:.0f} s", flush=True)
        if dt > PILOT_EVAL_BUDGET_S:
            failures.append(
                f"budget trip-wire: eval strength={strength} sev={sev} took {dt:.0f} s "
                f"> {PILOT_EVAL_BUDGET_S:.0f} s -- STOP, re-scope by spec revision"
            )

    # (a) I-1 in miniature: default-strength pilot rows == committed spaced rows.
    got_fr = _rows_by_key(fr_pilot, lambda r: (r["generator"], float(r["unobserved_strength"])))
    ref_fr = _rows_by_key(SPACED_FR, lambda r: (r["generator"], int(r["seed"])))
    for world in WORLDS:
        got = got_fr.get((world, DEFAULT_STRENGTH[world]), [])
        ref = ref_fr.get((world, seed), [])
        failures += _string_match(got, ref, FR_FIELDS, f"I-1 frontier {world}@default")
    got_cf = _rows_by_key(cf_pilot, lambda r: float(r["unobserved_strength"]))
    ref_cf = _rows_by_key(SPACED_CF, lambda r: (int(r["seed"]), float(r["severity"])))
    failures += _string_match(
        got_cf.get(0.55, []), ref_cf.get((seed, 0.4), []), CF_FIELDS, "I-1 cf 0.55@0.4"
    )

    # (b2) non-vacuity at the loop level: round-0 metrics move at strength 0.
    zero_rows = got_fr.get(("scm", 0.0), [])
    dflt_rows = got_fr.get(("scm", 0.55), [])
    if not zero_rows or not dflt_rows:
        failures.append("non-vacuity: missing scm pilot rows")
    elif zero_rows[0]["naive_declined_ece"] == dflt_rows[0]["naive_declined_ece"]:
        failures.append("non-vacuity: scm round-0 naive_declined_ece identical at strength 0 vs default")

    print("", flush=True)
    if failures:
        for msg in failures:
            print("FAIL: " + msg, flush=True)
        print("PILOT GATE FAIL -- DO NOT launch the matrix", flush=True)
        return 1
    print("PILOT GATE PASS -- byte-match + non-vacuity + budget all hold; matrix may launch", flush=True)
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--part", choices=("frontier", "counterfactual", "both"), default="both")
    ap.add_argument("--pilot", action="store_true", help="run the ~15 min pilot gate only")
    args = ap.parse_args()
    if args.pilot:
        return run_pilot()
    if args.part in ("frontier", "both"):
        run_frontier()
    if args.part in ("counterfactual", "both"):
        run_cf()
    miss_fr, miss_cf = _missing_frontier_keys(), _missing_cf_keys()
    print(f"SURFACE SWEEP COMPLETE -- missing frontier keys: {len(miss_fr)}, "
          f"missing cf keys: {len(miss_cf)}", flush=True)
    return 0 if not (miss_fr or miss_cf) else 1


if __name__ == "__main__":
    sys.exit(main())
