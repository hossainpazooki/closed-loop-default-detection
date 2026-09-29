"""CLDD strength-1.0 replication analysis.

Recomputes every to-be-published number from
artifacts/strength_replication_frontier.csv and writes
artifacts/strength_replication_stats.csv. Exits non-zero -- publication
mechanically blocked -- if any cell is missing (fail-closed) or a seed from the
spent set appears in the artifact.

F_w(v) is the per-seed loop frontier in world w at confounder strength v.

Confirmatory family (m=2, Holm alpha=0.05, one-sided exact sign test AND
one-sided Wilcoxon, both must clear, plus the floor):
  H-R1f: F_flat(0.0) - F_flat(1.0) > 0 per seed;  floor: median diff >= 0.2
  H-R1s: F_scm(0.0)  - F_scm(1.0)  > 0 per seed;  floor: median diff >= 0.2

Descriptive, no verdicts: the default-strength cells (dose response) and the
frontier distribution per cell.

The extraction, the hypothesis row, the never-passed encoding (-0.2) and the
statistics primitives are IMPORTED from scripts/surface_stats.py, so the
replication is judged by exactly the code that produced the observation.
Deterministic; ASCII-only stdout.
"""
from __future__ import annotations

import csv
import importlib.util
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

SCRIPTS = Path(__file__).resolve().parent
ROOT = SCRIPTS.parent


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_rsr = _load("run_strength_replication")
_ss = _load("surface_stats")

SEEDS = list(_rsr.SEEDS)
WORLDS = tuple(_rsr.WORLDS)
IN_CSV = _rsr.OUT
OUT_CSV = ROOT / "artifacts" / "strength_replication_stats.csv"
ALPHA = _ss.ALPHA
FIELDS = list(_ss.SURFACE_STATS_FIELDS)
_ROUND4 = ("median_stat", "mean_stat", "floor")


def _read_rows(path: Path) -> list:
    if not path.exists():
        raise FileNotFoundError(
            f"{path} missing -- run scripts/run_strength_replication.py first")
    with path.open(newline="") as f:
        return list(csv.DictReader(f))


def missing_cells(rows: list) -> list:
    have = {(float(r["unobserved_strength"]), r["generator"], int(r["seed"])) for r in rows}
    return [(v, w, s) for v, w in _rsr.cells() for s in SEEDS if (v, w, s) not in have]


def spent_seed_rows(rows: list) -> list:
    """Seeds the observation was made on must never enter the replication."""
    spent = set(_rsr.SPENT_SEEDS)
    return sorted({int(r["seed"]) for r in rows if int(r["seed"]) in spent})


def build_rows(rows_in: list) -> list:
    rows: list = []
    for name, world in (("H-R1f", "flat"), ("H-R1s", "scm")):
        row = _ss.hs1_row(
            name,
            _ss.frontier_by_seed(rows_in, _rsr.STRENGTH_LOW, world),
            _ss.frontier_by_seed(rows_in, _rsr.STRENGTH_HIGH, world),
        )
        row["strength"] = _rsr.STRENGTH_HIGH
        rows.append(row)
    sign_holm = _ss._fss.holm_adjust([r["sign_p_raw"] for r in rows])
    wil_holm = _ss._fss.holm_adjust([r["wilcoxon_p_raw"] for r in rows])
    for r, sp, wp in zip(rows, sign_holm, wil_holm):
        r["sign_p_holm"], r["wilcoxon_p_holm"] = sp, wp
        r["confirmed"] = bool(sp <= ALPHA and wp <= ALPHA and r["clears_floor"])

    for strength, world in _rsr.cells():
        vals = list(_ss.frontier_by_seed(rows_in, strength, world).values())
        counts: dict = {}
        for v in vals:
            counts[str(v)] = counts.get(str(v), 0) + 1
        row = _ss._row_defaults()
        row.update(metric="cell_frontier", hypothesis="", world=world, strength=strength,
                   role="descriptive", direction="n/a", n_seeds=len(vals),
                   median_stat=float(np.median(vals)) if vals else float("nan"),
                   mean_stat=float(np.mean(vals)) if vals else float("nan"),
                   n_never_passed=sum(1 for x in vals if x == _ss.NEVER_PASSED),
                   detail_json=json.dumps(counts, sort_keys=True))
        rows.append(row)
    return rows


def write_stats_csv(rows: list, out: Path) -> pd.DataFrame:
    frame = pd.DataFrame(rows, columns=FIELDS)
    for col in _ROUND4:
        frame[col] = frame[col].apply(lambda v: v if pd.isna(v) else round(float(v), 4))
    out.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(out, index=False)
    return frame


def print_summary(rows: list) -> None:
    print("CLDD strength-1.0 replication -- stats summary")
    print("output: " + str(OUT_CSV))
    print("")
    conf = [r for r in rows if r["metric"] == "hypothesis"]
    print("Confirmatory family (m=2, Holm alpha=%.2f, both tests + floor):" % ALPHA)
    for r in conf:
        verdict = "CONFIRMED" if r["confirmed"] else "not confirmed"
        print("  %s [%s]: median=%+.4f (n=%d) sign %d/%d p_holm=%.3e; "
              "wilcoxon p_holm=%.3e; floor=%.4f clears=%s -> %s"
              % (r["hypothesis"], r["world"], r["median_stat"], r["n_seeds"],
                 r["sign_k"], r["sign_n"], r["sign_p_holm"],
                 r["wilcoxon_p_holm"], r["floor"], r["clears_floor"], verdict))
        if r["n_never_passed"]:
            print("    NOTE: %d never-passed frontier cell(s) encoded as %.1f"
                  % (r["n_never_passed"], _ss.NEVER_PASSED))
    print("")
    n = sum(1 for r in conf if r["confirmed"])
    print("strength-1.0 observation: %s"
          % ("REPLICATED in both worlds" if n == 2 else
             "REPLICATED in %d of 2 worlds" % n if n else "NOT REPLICATED"))
    print("")
    for r in rows:
        if r["metric"] == "cell_frontier":
            print("cell [%s] strength %.2f: median %.2f  %s"
                  % (r["world"], r["strength"], r["median_stat"], r["detail_json"]))


def main() -> int:
    rows_in = _read_rows(IN_CSV)

    spent = spent_seed_rows(rows_in)
    if spent:
        print("FAIL-CLOSED: spent seeds in the replication artifact: %s" % spent[:10])
        return 1
    miss = missing_cells(rows_in)
    if miss:
        print("FAIL-CLOSED: missing cells -- confirmatory stats are unevaluable")
        print("  missing (%d): %s" % (len(miss), miss[:10]))
        return 1

    rows = build_rows(rows_in)
    write_stats_csv(rows, OUT_CSV)
    print_summary(rows)
    return 0


if __name__ == "__main__":
    sys.exit(main())
