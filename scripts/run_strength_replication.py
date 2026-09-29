"""CLDD strength-1.0 replication on fresh seeds (frontier leg, both worlds).

The v4 surface showed the median frontier at 0.4 for every confounder strength
up to 0.7 and at 0.2 only at strength 1.0. That was read off the surface AFTER
the data was in, so it is an observation, not a result. This driver re-runs the
contrast on a seed set that no committed artifact has ever consumed.

Strengths {0.0, world default, 1.0} x {flat, scm} x 25 fresh seeds = 150 loop runs
  -> artifacts/strength_replication_frontier.csv  (the surface_frontier.csv schema)

The child code, the row pipeline and the helpers are IMPORTED from
scripts/run_surface_sweep.py, not copied: this driver differs from the v4
surface driver in its seed set, its strength grid and its output path, and in
nothing else. No committed artifact is ever written.

Usage:
    python scripts/run_strength_replication.py --pilot   # ~1 min gate, run FIRST
    python scripts/run_strength_replication.py           # full matrix (~25 min)

--pilot runs on SPACED seed 1000 only, never on a fresh seed, so it exposes no
confirmatory outcome. It asserts, exiting non-zero on any failure:
  (a) plumbing: this driver's rows at seed 1000, strengths {0.0, 1.0}, both
      worlds, are string-equal on every column to the committed
      surface_frontier.csv rows -- same child, same build, same bytes;
  (b) budget trip-wire: per-run wall time under 60 s.
"""
from __future__ import annotations

import argparse
import importlib.util
import sys
import time
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
ROOT = SCRIPTS.parent


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_rss = _load("run_surface_sweep")

WORLDS = tuple(_rss.WORLDS)
DEFAULT_STRENGTH = dict(_rss.DEFAULT_STRENGTH)       # {"flat": 0.7, "scm": 0.55}
FIELDS = list(_rss.SURF_FR_FIELDS)
SURFACE_FR = _rss.FR_OUT                             # committed surface_frontier.csv
SPENT_SEEDS = list(_rss.SEEDS)                       # {1000 + 16i}: the observation's seeds

# Fresh set. Spacing 16 exceeds every within-run consumption span (a loop run
# at seed s consumes s..s+7 and s+1000..s+1007). Every committed artifact's
# seeds are <= 2026, so nothing below 4000 is reused here.
SEEDS = [5000 + 16 * i for i in range(25)]
STRENGTH_LOW, STRENGTH_HIGH = 0.0, 1.0
PILOT_SEED = SPENT_SEEDS[0]
PILOT_STRENGTHS = (STRENGTH_LOW, STRENGTH_HIGH)

OUT = ROOT / "artifacts" / "strength_replication_frontier.csv"
PILOT_DIR = ROOT / "artifacts" / "strength_replication_pilot"
PILOT_LOOP_BUDGET_S = 60.0

MAX_ROUNDS = 8
TRAIN_SEED_OFFSET = 1000


def strengths_for(world: str) -> list:
    return [STRENGTH_LOW, DEFAULT_STRENGTH[world], STRENGTH_HIGH]


def cells() -> list:
    """(strength, world) cells -- 6 cells x 25 seeds = 150 runs."""
    return [(v, w) for w in WORLDS for v in strengths_for(w)]


def consumed(seed: int) -> set:
    """Every generator seed one loop run at ``seed`` can consume."""
    measure = set(range(seed, seed + MAX_ROUNDS))
    return measure | {s + TRAIN_SEED_OFFSET for s in measure}


def _key(row: dict) -> tuple:
    return (float(row["unobserved_strength"]), row["generator"], int(row["seed"]))


def missing_keys(out: Path) -> list:
    done = _rss._done_keys(out, _key)
    return [(v, w, s) for v, w in cells() for s in SEEDS if (v, w, s) not in done]


def run_matrix(out: Path) -> None:
    done = _rss._done_keys(out, _key)
    total = len(cells()) * len(SEEDS)
    n = 0
    for strength, world in cells():
        for seed in SEEDS:
            n += 1
            label = f"strength={strength} world={world} seed={seed}"
            if (strength, world, seed) in done:
                print(f"[{n}/{total}] skip {label}", flush=True)
                continue
            print(f"[{n}/{total}] loop {label} ...", flush=True)
            rows = _rss._run_child(
                _rss._FR_CHILD.format(strength=strength, generator=world, seed=seed)
            )
            for row in rows:
                _rss._append(out, FIELDS, row)
            print(f"  {len(rows)} rounds", flush=True)
    print(f"replication sweep complete -> {out} (missing keys: {len(missing_keys(out))})",
          flush=True)


def run_pilot() -> int:
    print("PILOT GATE (strength replication) -- spaced seed %d only" % PILOT_SEED, flush=True)
    failures: list = []
    PILOT_DIR.mkdir(parents=True, exist_ok=True)
    pilot_csv = PILOT_DIR / "pilot_frontier.csv"
    if pilot_csv.exists():
        pilot_csv.unlink()    # pilot scratch only -- committed artifacts are never touched

    for world in WORLDS:
        for strength in PILOT_STRENGTHS:
            t0 = time.monotonic()
            print(f"loop pilot {world}@{strength} seed={PILOT_SEED} ...", flush=True)
            rows = _rss._run_child(
                _rss._FR_CHILD.format(strength=strength, generator=world, seed=PILOT_SEED)
            )
            dt = time.monotonic() - t0
            for row in rows:
                _rss._append(pilot_csv, FIELDS, row)
            print(f"  {len(rows)} rounds in {dt:.0f} s", flush=True)
            if dt > PILOT_LOOP_BUDGET_S:
                failures.append(
                    f"budget trip-wire: {world}@{strength} took {dt:.0f} s "
                    f"> {PILOT_LOOP_BUDGET_S:.0f} s -- STOP, re-scope by spec revision"
                )

    got = _rss._rows_by_key(pilot_csv, _key)
    ref = _rss._rows_by_key(SURFACE_FR, _key)
    for world in WORLDS:
        for strength in PILOT_STRENGTHS:
            key = (strength, world, PILOT_SEED)
            want = ref.get(key, [])
            if not want:
                failures.append(f"plumbing {key}: reference cell absent (gate cannot verify)")
                continue
            failures += _rss._string_match(got.get(key, []), want, FIELDS,
                                           f"plumbing {world}@{strength}")

    print("", flush=True)
    if failures:
        for msg in failures:
            print("FAIL: " + msg, flush=True)
        print("PILOT GATE FAIL -- DO NOT launch the matrix", flush=True)
        return 1
    print("PILOT GATE PASS -- byte-match to the committed surface + budget hold; "
          "matrix may launch", flush=True)
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--pilot", action="store_true", help="run the pilot gate only")
    args = ap.parse_args()
    if args.pilot:
        return run_pilot()
    run_matrix(OUT)
    miss = missing_keys(OUT)
    print(f"REPLICATION SWEEP COMPLETE -- missing keys: {len(miss)}", flush=True)
    return 0 if not miss else 1


if __name__ == "__main__":
    sys.exit(main())
