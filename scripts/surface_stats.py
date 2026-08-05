"""CLDD v4 Option A surface analysis (spec 3, 5, 7).

Recomputes every to-be-published surface number from the two committed artifact
CSVs (never from memory), enforces the I-1 byte-identity embed gate against the
v4env spaced baselines (spec Amendment Rev 1.1: the same configurations re-run
under this build environment, provenance in artifacts/surface_env.json; the
2026-07-29 originals stay untouched and authoritative for published numbers,
but cannot serve as a byte reference across an interpreter-build change), and
writes artifacts/surface_stats.csv. Exits
non-zero -- publication mechanically blocked -- if any confirmatory computation
is unevaluable (missing cells: fail-closed) or any integrity control fails.

Confirmatory family (m=4, Holm alpha=0.05, one-sided exact sign test AND
one-sided Wilcoxon, both must clear, plus the floors; spec 3):
  H-S1f: F_flat(0.0) - F_flat(0.7) > 0 per seed;  floor: median diff >= 0.2
  H-S1s: F_scm(0.0) - F_scm(0.55) > 0 per seed;   floor: median diff >= 0.2
  H-S2a: g(0.55, 0.4) - g(0.0, 0.4) > 0 per seed; floor: median diff >= median|g(0.0, 0.4)|
  H-S2b: D(0.55) - D(0.0) > 0 per seed,           floor: median diff >= median|D(0.0)|
         where D(v) = g(v, 0.4) - g(v, 1.0)
g(v, sev) is the per-seed strong-propagation gap (strong_gap column).

Falsification statement (spec 3): the one-wall narrative survives into any doc
only if ALL FOUR pass; any failure is reported as measured.

Encoding decision (recorded): a run whose frontier_severity is empty (never
passed severity 0) is encoded as -0.2 -- one grid step below the minimum --
preserving the grid quantization the H-S1 floor is stated in; occurrences are
counted per cell in n_never_passed.

Statistics primitives (sign_test, wilcoxon_test, holm_adjust) are imported from
scripts/feedback_sweep_stats.py so v4 uses the exact v3 implementations.
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
sys.path.insert(0, str(ROOT / "src"))

from cldd import config  # noqa: E402


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_rss = _load("run_surface_sweep")
_fss = _load("feedback_sweep_stats")

SEEDS = list(_rss.SEEDS)
STRENGTHS = list(_rss.STRENGTHS)
WORLDS = tuple(_rss.WORLDS)
DEFAULT_STRENGTH = dict(_rss.DEFAULT_STRENGTH)
FR_CSV, CF_CSV = _rss.FR_OUT, _rss.CF_OUT
SPACED_FR, SPACED_CF = _rss.SPACED_FR, _rss.SPACED_CF
OUT_CSV = ROOT / "artifacts" / "surface_stats.csv"

ALPHA = 0.05
NEVER_PASSED = -0.2          # one grid step below the minimum passable severity
GRID_STEP_FLOOR = 0.2        # H-S1 floor: one severity step (spec 3)
CF_CONF_SEV_LOW, CF_CONF_SEV_HIGH = 0.4, 1.0

SURFACE_STATS_FIELDS = [
    "metric", "hypothesis", "world", "strength", "severity", "role", "direction",
    "n_seeds", "median_stat", "mean_stat", "floor", "clears_floor",
    "sign_k", "sign_n", "sign_p_raw", "sign_p_holm",
    "wilcoxon_stat", "wilcoxon_p_raw", "wilcoxon_p_holm", "confirmed",
    "n_never_passed", "detail_json",
]


# --------------------------------------------------------------------------- #
# Loading + completeness (fail-closed)
# --------------------------------------------------------------------------- #

def _read_rows(path: Path) -> list:
    if not path.exists():
        raise FileNotFoundError(f"{path} missing -- run scripts/run_surface_sweep.py first")
    with path.open(newline="") as f:
        return list(csv.DictReader(f))


def missing_frontier_cells(rows: list) -> list:
    have = {(float(r["unobserved_strength"]), r["generator"], int(r["seed"])) for r in rows}
    return [(v, w, s) for v, w in _rss.frontier_cells() for s in SEEDS
            if (v, w, s) not in have]


def missing_cf_cells(rows: list) -> list:
    have = {(float(r["unobserved_strength"]), float(r["severity"]), int(r["seed"])) for r in rows}
    return [(v, sev, s) for v, sev in _rss.cf_cells() for s in SEEDS
            if (v, sev, s) not in have]


# --------------------------------------------------------------------------- #
# I-1 byte-identity embed gate (spec 7)
# --------------------------------------------------------------------------- #

def _group(rows: list, key_fn) -> dict:
    out: dict = {}
    for r in rows:
        out.setdefault(key_fn(r), []).append(r)
    return out


def i1_check_frontier(surface_csv: Path, spaced_csv: Path, fields: list,
                      default_strength: dict, seeds: list, worlds) -> list:
    """Default-strength surface rows must be string-equal per shared column with
    the spaced artifact, per (world, seed), in iteration order."""
    surf = _group(_read_rows(surface_csv),
                  lambda r: (r["generator"], float(r["unobserved_strength"]), int(r["seed"])))
    ref = _group(_read_rows(spaced_csv), lambda r: (r["generator"], int(r["seed"])))
    problems: list = []
    for world in worlds:
        for seed in seeds:
            got = sorted(surf.get((world, default_strength[world], seed), []),
                         key=lambda r: int(r["iteration"]))
            want = sorted(ref.get((world, seed), []), key=lambda r: int(r["iteration"]))
            label = f"I-1 frontier {world}@{default_strength[world]} seed={seed}"
            if len(got) != len(want):
                problems.append(f"{label}: {len(got)} rows != spaced {len(want)}")
                continue
            for i, (g, w) in enumerate(zip(got, want)):
                for f in fields:
                    if g.get(f, "") != w.get(f, ""):
                        problems.append(f"{label} row {i} col {f}: {g.get(f)!r} != {w.get(f)!r}")
    return problems


def i1_check_cf(surface_csv: Path, spaced_csv: Path, fields: list, seeds: list) -> list:
    surf = _group(_read_rows(surface_csv),
                  lambda r: (float(r["unobserved_strength"]), float(r["severity"]), int(r["seed"])))
    ref = _group(_read_rows(spaced_csv), lambda r: (float(r["severity"]), int(r["seed"])))
    problems: list = []
    for sev in (CF_CONF_SEV_LOW, CF_CONF_SEV_HIGH):
        for seed in seeds:
            got = surf.get((DEFAULT_STRENGTH["scm"], sev, seed), [])
            want = ref.get((sev, seed), [])
            label = f"I-1 cf 0.55@{sev} seed={seed}"
            if len(got) != 1 or len(want) != 1:
                problems.append(f"{label}: {len(got)} surface rows vs {len(want)} spaced rows")
                continue
            for f in fields:
                if got[0].get(f, "") != want[0].get(f, ""):
                    problems.append(f"{label} col {f}: {got[0].get(f)!r} != {want[0].get(f)!r}")
    return problems


# --------------------------------------------------------------------------- #
# Per-seed extraction
# --------------------------------------------------------------------------- #

def frontier_by_seed(rows: list, strength: float, world: str) -> dict:
    """{seed: frontier_severity} for one cell; '' (never passed) -> NEVER_PASSED."""
    out: dict = {}
    for r in rows:
        if float(r["unobserved_strength"]) != strength or r["generator"] != world:
            continue
        seed = int(r["seed"])
        raw = r["frontier_severity"]
        out[seed] = NEVER_PASSED if raw in ("", "None") else float(raw)
    return out


def gap_by_seed(rows: list, strength: float, severity: float) -> dict:
    """{seed: strong_gap} for one CF cell."""
    out: dict = {}
    for r in rows:
        if float(r["unobserved_strength"]) == strength and float(r["severity"]) == severity:
            out[int(r["seed"])] = float(r["strong_gap"])
    return out


# --------------------------------------------------------------------------- #
# Confirmatory rows (spec 3)
# --------------------------------------------------------------------------- #

def _row_defaults() -> dict:
    return {k: float("nan") for k in SURFACE_STATS_FIELDS}


def _paired(diff_a: dict, diff_b: dict) -> list:
    seeds = sorted(set(diff_a) & set(diff_b))
    return [diff_a[s] - diff_b[s] for s in seeds]


def _hypothesis_row(name: str, diffs: list, floor: float, world: str = "",
                    strength=float("nan")) -> dict:
    sign = _fss.sign_test(diffs, "positive")
    wil = _fss.wilcoxon_test(diffs, "positive")
    median = float(np.median(diffs)) if diffs else float("nan")
    row = _row_defaults()
    row.update(
        metric="hypothesis", hypothesis=name, world=world, strength=strength,
        role="confirmatory", direction="positive",
        n_seeds=len(diffs), median_stat=median,
        mean_stat=float(np.mean(diffs)) if diffs else float("nan"),
        floor=floor, clears_floor=bool(diffs and median >= floor),
        sign_k=sign["k"], sign_n=sign["n"], sign_p_raw=sign["p"],
        wilcoxon_stat=wil["stat"], wilcoxon_p_raw=wil["p"],
        confirmed=None, n_never_passed=0, detail_json="",
    )
    return row


def hs1_row(name: str, f_zero: dict, f_default: dict) -> dict:
    diffs = _paired(f_zero, f_default)
    world = "flat" if name.endswith("f") else "scm"
    row = _hypothesis_row(name, diffs, GRID_STEP_FLOOR, world=world)
    row["n_never_passed"] = sum(
        1 for d in (f_zero, f_default) for v in d.values() if v == NEVER_PASSED
    )
    return row


def hs2_row(name: str, g_default: dict, g_zero: dict) -> dict:
    diffs = _paired(g_default, g_zero)
    floor = float(np.median([abs(v) for v in g_zero.values()])) if g_zero else float("nan")
    return _hypothesis_row(name, diffs, floor, world="scm")


def build_rows(fr_rows: list, cf_rows: list) -> list:
    rows: list = []
    d_scm = DEFAULT_STRENGTH["scm"]

    # -- confirmatory family ------------------------------------------------ #
    rows.append(hs1_row("H-S1f", frontier_by_seed(fr_rows, 0.0, "flat"),
                        frontier_by_seed(fr_rows, DEFAULT_STRENGTH["flat"], "flat")))
    rows.append(hs1_row("H-S1s", frontier_by_seed(fr_rows, 0.0, "scm"),
                        frontier_by_seed(fr_rows, d_scm, "scm")))
    g0_low = gap_by_seed(cf_rows, 0.0, CF_CONF_SEV_LOW)
    gd_low = gap_by_seed(cf_rows, d_scm, CF_CONF_SEV_LOW)
    rows.append(hs2_row("H-S2a", gd_low, g0_low))
    g0_high = gap_by_seed(cf_rows, 0.0, CF_CONF_SEV_HIGH)
    gd_high = gap_by_seed(cf_rows, d_scm, CF_CONF_SEV_HIGH)
    delta_0 = {s: g0_low[s] - g0_high[s] for s in set(g0_low) & set(g0_high)}
    delta_d = {s: gd_low[s] - gd_high[s] for s in set(gd_low) & set(gd_high)}
    rows.append(hs2_row("H-S2b", delta_d, delta_0))

    conf = rows[:4]
    sign_holm = _fss.holm_adjust([r["sign_p_raw"] for r in conf])
    wil_holm = _fss.holm_adjust([r["wilcoxon_p_raw"] for r in conf])
    for r, sp, wp in zip(conf, sign_holm, wil_holm):
        r["sign_p_holm"], r["wilcoxon_p_holm"] = sp, wp
        r["confirmed"] = bool(sp <= ALPHA and wp <= ALPHA and r["clears_floor"])

    # -- corner prediction (descriptive, spec 3) ---------------------------- #
    for world in WORLDS:
        f0 = frontier_by_seed(fr_rows, 0.0, world)
        at_max = sum(1 for v in f0.values() if v == config.MAX_SEVERITY)
        row = _row_defaults()
        row.update(metric="corner", hypothesis="corner_frontier", world=world,
                   strength=0.0, role="descriptive", direction="n/a",
                   n_seeds=len(f0), sign_k=at_max, sign_n=len(f0),
                   median_stat=float(np.median(list(f0.values()))) if f0 else float("nan"),
                   n_never_passed=sum(1 for v in f0.values() if v == NEVER_PASSED),
                   detail_json="")
        rows.append(row)
    for sev in (0.4, 0.6, 0.8, 1.0):
        g0 = gap_by_seed(cf_rows, 0.0, sev)
        row = _row_defaults()
        row.update(metric="corner", hypothesis="corner_gap", world="scm",
                   strength=0.0, severity=sev, role="descriptive", direction="n/a",
                   n_seeds=len(g0),
                   median_stat=float(np.median([abs(v) for v in g0.values()])) if g0 else float("nan"),
                   detail_json="")
        rows.append(row)

    # -- descriptive surface ------------------------------------------------ #
    for world in WORLDS:
        for v in STRENGTHS:
            f = frontier_by_seed(fr_rows, v, world)
            vals = list(f.values())
            row = _row_defaults()
            row.update(metric="surface_frontier", hypothesis="", world=world, strength=v,
                       role="descriptive", direction="n/a", n_seeds=len(vals),
                       median_stat=float(np.median(vals)) if vals else float("nan"),
                       mean_stat=float(np.mean(vals)) if vals else float("nan"),
                       n_never_passed=sum(1 for x in vals if x == NEVER_PASSED),
                       detail_json=json.dumps(
                           {"min": min(vals), "max": max(vals)} if vals else {}))
            rows.append(row)
    for v, sev in _rss.cf_cells():
        g = gap_by_seed(cf_rows, v, sev)
        vals = list(g.values())
        row = _row_defaults()
        row.update(metric="surface_gap", hypothesis="", world="scm", strength=v,
                   severity=sev, role="descriptive", direction="n/a", n_seeds=len(vals),
                   median_stat=float(np.median(vals)) if vals else float("nan"),
                   mean_stat=float(np.mean(vals)) if vals else float("nan"),
                   detail_json=json.dumps(
                       {"min": min(vals), "max": max(vals)} if vals else {}))
        rows.append(row)

    # -- monotonicity read-off (descriptive) -------------------------------- #
    for world in WORLDS:
        medians = [float(np.median(list(frontier_by_seed(fr_rows, v, world).values() or [np.nan])))
                   for v in STRENGTHS]
        mono = all(a >= b for a, b in zip(medians, medians[1:]))
        row = _row_defaults()
        row.update(metric="monotonicity", hypothesis="frontier_nonincreasing",
                   world=world, role="descriptive", direction="n/a",
                   n_seeds=len(SEEDS), confirmed=None, clears_floor=mono,
                   detail_json=json.dumps(dict(zip(map(str, STRENGTHS), medians))))
        rows.append(row)
    return rows


_ROUND4 = ("median_stat", "mean_stat", "floor")


def write_stats_csv(rows: list, out: Path = OUT_CSV) -> pd.DataFrame:
    frame = pd.DataFrame(rows, columns=SURFACE_STATS_FIELDS)
    for col in _ROUND4:
        frame[col] = frame[col].apply(lambda v: v if pd.isna(v) else round(float(v), 4))
    out.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(out, index=False)
    return frame


def print_summary(rows: list) -> None:
    print("CLDD v4 Option A surface -- stats summary")
    print("output: " + str(OUT_CSV))
    print("")
    conf = [r for r in rows if r["metric"] == "hypothesis"]
    print("Confirmatory family (m=4, Holm alpha=%.2f, both tests + floor):" % ALPHA)
    for r in conf:
        verdict = "CONFIRMED" if r["confirmed"] else "not confirmed"
        print("  %s [%s]: median=%+.4f (n=%d) sign %d/%d p_holm=%.3e; "
              "wilcoxon p_holm=%.3e; floor=%.4f clears=%s -> %s"
              % (r["hypothesis"], r["world"], r["median_stat"], r["n_seeds"],
                 r["sign_k"], r["sign_n"], r["sign_p_holm"],
                 r["wilcoxon_p_holm"], r["floor"], r["clears_floor"], verdict))
        if r["n_never_passed"]:
            print("    NOTE: %d never-passed frontier cell(s) encoded as %.1f"
                  % (r["n_never_passed"], NEVER_PASSED))
    all_pass = all(r["confirmed"] for r in conf)
    print("")
    print("one-wall narrative: %s (survives only if ALL FOUR confirmed -- spec 3)"
          % ("SURVIVES" if all_pass else "FALSIFIED / QUALIFY THE DOCS"))
    print("")
    for r in rows:
        if r["metric"] == "corner" and r["hypothesis"] == "corner_frontier":
            print("corner [%s]: frontier at grid max for %d/%d seeds at strength 0; median %.2f"
                  % (r["world"], r["sign_k"], r["sign_n"], r["median_stat"]))
        if r["metric"] == "corner" and r["hypothesis"] == "corner_gap":
            print("corner [scm] sev %.1f: median |g(0, sev)| = %.4f"
                  % (r["severity"], r["median_stat"]))
    print("")
    for r in rows:
        if r["metric"] == "monotonicity":
            print("monotonicity [%s]: median frontier non-increasing in strength: %s  %s"
                  % (r["world"], r["clears_floor"], r["detail_json"]))


def main() -> int:
    fr_rows = _read_rows(FR_CSV)
    cf_rows = _read_rows(CF_CSV)

    miss_fr, miss_cf = missing_frontier_cells(fr_rows), missing_cf_cells(cf_rows)
    if miss_fr or miss_cf:
        print("FAIL-CLOSED: missing cells -- confirmatory stats are unevaluable")
        print("  frontier missing (%d): %s" % (len(miss_fr), miss_fr[:10]))
        print("  cf missing (%d): %s" % (len(miss_cf), miss_cf[:10]))
        return 1

    problems = i1_check_frontier(FR_CSV, SPACED_FR, fields=_rss.FR_FIELDS,
                                 default_strength=DEFAULT_STRENGTH, seeds=SEEDS,
                                 worlds=WORLDS)
    problems += i1_check_cf(CF_CSV, SPACED_CF, fields=_rss.CF_FIELDS, seeds=SEEDS)
    if problems:
        print("I-1 BYTE-IDENTITY EMBED GATE FAILED (driver-plumbing bug, spec 7):")
        for p in problems[:20]:
            print("  " + p)
        print("  (%d problems total)" % len(problems))
        return 1
    print("I-1 embed gate: PASS (default-strength cells string-equal to spaced artifacts)")
    print("")

    rows = build_rows(fr_rows, cf_rows)
    write_stats_csv(rows)
    print_summary(rows)
    return 0


if __name__ == "__main__":
    sys.exit(main())
