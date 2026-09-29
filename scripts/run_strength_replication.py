"""CLDD strength-1.0 replication on fresh seeds (frontier leg, both worlds).

The v4 surface showed the median frontier at 0.4 for every confounder strength
up to 0.7 and at 0.2 only at strength 1.0. That was read off the surface AFTER
the data was in, so it is an observation, not a result. This driver re-runs the
whole strength grid on a seed set that no committed artifact has ever consumed.

Six strengths x {flat, scm} x 25 fresh seeds = 300 loop runs
  -> artifacts/strength_replication_frontier.csv
     (the surface_frontier.csv schema + four overlap-diagnostic columns)

The child code is the v4 surface child with ONE block inserted, the four
diagnostic columns; the helpers are imported from scripts/run_surface_sweep.py,
not copied. Remove the inserted block and the child is the v4 child byte for
byte (a test pins this). The diagnostics are computed by the loop on every
round anyway, so the extra columns cost no compute. No committed artifact is
ever written.

Usage:
    python scripts/run_strength_replication.py --pilot   # ~1 min gate, run FIRST
    python scripts/run_strength_replication.py           # full matrix (~50 min)

--pilot runs on SPACED seed 1000 only, never on a fresh seed, so it exposes no
confirmatory outcome. It asserts, exiting non-zero on any failure:
  (a) plumbing: this driver's rows at seed 1000, strengths {0.0, 1.0}, both
      worlds, are string-equal on every SHARED column to the committed
      surface_frontier.csv rows -- same child, same build, same bytes;
  (b) the four diagnostic columns are present and non-empty on every row;
  (c) budget trip-wire: per-run wall time under 60 s.
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
STRENGTHS = list(_rss.STRENGTHS)                     # the v4 grid, all six
SHARED_FIELDS = list(_rss.SURF_FR_FIELDS)            # what the pilot byte-matches
DIAG_FIELDS = ["propensity_auc", "ess_ratio", "unfunded_below_floor", "diag_flagged"]
FIELDS = SHARED_FIELDS + DIAG_FIELDS
SURFACE_FR = _rss.FR_OUT                             # committed surface_frontier.csv
SPENT_SEEDS = list(_rss.SEEDS)                       # {1000 + 16i}: the observation's seeds

# Fresh set. Spacing 16 exceeds every within-run consumption span (a loop run
# at seed s consumes s..s+7 and s+1000..s+1007). Every committed artifact's
# seeds are <= 2026, so their runs consume nothing at or above 3034.
SEEDS = [5000 + 16 * i for i in range(25)]
SPENT_CEILING = 4000                                 # a replication run consumes nothing below this
STRENGTH_LOW, STRENGTH_HIGH = 0.0, 1.0
PILOT_SEED = SPENT_SEEDS[0]
PILOT_STRENGTHS = (STRENGTH_LOW, STRENGTH_HIGH)

OUT = ROOT / "artifacts" / "strength_replication_frontier.csv"
PILOT_DIR = ROOT / "artifacts" / "strength_replication_pilot"
PILOT_LOOP_BUDGET_S = 60.0

MAX_ROUNDS = 8
TRAIN_SEED_OFFSET = 1000

# The one insertion into the v4 child. Braces are doubled because the child is
# a str.format template.
_ROW_PRINT = "    print(json.dumps(row))\n"
DIAG_BLOCK = (
    "    row.update({{\n"
    '        "propensity_auc": r.diagnostics.propensity_auc,\n'
    '        "ess_ratio": r.diagnostics.ess_ratio,\n'
    '        "unfunded_below_floor": r.diagnostics.unfunded_below_floor,\n'
    '        "diag_flagged": r.diagnostics.flagged,\n'
    "    }})\n"
)


def child_template() -> str:
    """The v4 surface child with the diagnostic block inserted before the print."""
    base = _rss._FR_CHILD
    if base.count(_ROW_PRINT) != 1:
        raise RuntimeError("the surface child changed shape; cannot insert the diagnostic block")
    return base.replace(_ROW_PRINT, DIAG_BLOCK + _ROW_PRINT)


def cells() -> list:
    """(strength, world) cells -- 12 cells x 25 seeds = 300 runs."""
    return [(v, w) for w in WORLDS for v in STRENGTHS]


def consumed(seed: int) -> set:
    """Every generator seed one loop run at ``seed`` can consume."""
    measure = set(range(seed, seed + MAX_ROUNDS))
    return measure | {s + TRAIN_SEED_OFFSET for s in measure}


def _key(row: dict) -> tuple:
    return (float(row["unobserved_strength"]), row["generator"], int(row["seed"]))


def missing_keys(out: Path) -> list:
    done = _rss._done_keys(out, _key)
    return [(v, w, s) for v, w in cells() for s in SEEDS if (v, w, s) not in done]


def _run(strength: float, world: str, seed: int) -> list:
    return _rss._run_child(child_template().format(strength=strength, generator=world, seed=seed))


def run_matrix(out: Path) -> None:
    tainted = [s for s in SEEDS if min(consumed(s)) < SPENT_CEILING]
    if tainted:
        raise SystemExit(f"refusing to run: seeds {tainted} consume below {SPENT_CEILING}")
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
            rows = _run(strength, world, seed)
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
            rows = _run(strength, world, PILOT_SEED)
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
            mine = got.get(key, [])
            failures += _rss._string_match(mine, want, SHARED_FIELDS,
                                           f"plumbing {world}@{strength}")
            for i, row in enumerate(mine):
                empty = [f for f in DIAG_FIELDS if row.get(f, "") in ("", "None")]
                if empty:
                    failures.append(f"diagnostics {world}@{strength} row {i}: empty {empty}")

    print("", flush=True)
    if failures:
        for msg in failures:
            print("FAIL: " + msg, flush=True)
        print("PILOT GATE FAIL -- DO NOT launch the matrix", flush=True)
        return 1
    print("PILOT GATE PASS -- byte-match to the committed surface + diagnostics present "
          "+ budget hold; matrix may launch", flush=True)
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
