"""CLDD strength-1.0 replication analysis.

Recomputes every to-be-published number from
artifacts/strength_replication_frontier.csv and writes
artifacts/strength_replication_stats.csv. Exits non-zero -- publication
mechanically blocked -- if any cell is missing, if any row's run consumed a
spent seed, or if a confirmatory computation is unevaluable.

Per seed, world w, confounder strength v:
  E_w(v)  declined ECE of the loop's control lever at severity 0.4. Under the
          published configuration (improve_mode="both", exploration 0) the
          control lever is the IPW reweight, column reweight_declined_ece.
  F_w(v)  the loop's frontier severity.

PRIMARY family (m=2, Holm alpha=0.05, one-sided exact sign test AND one-sided
Wilcoxon, both must clear, plus the floor):
  H-R1f / H-R1s   E_w(1.0) - E_w(0.0) > 0
      floor: median paired difference >= the LARGER of
        (a) target distance: 0.10 - median E_w(0.0), what it takes to carry the
            median strength-0 run across the calibration target; and
        (b) noise scale: median |E at severity 0, strength 1.0 minus strength 0|.
            At severity 0 selection is random, so strength cannot act through
            selection there and the contrast measures noise.
      Unevaluable if median E_w(0.0) is already at or over the target.

SECONDARY family (m=2, its own Holm, same tests):
  H-R2f / H-R2s   F_w(0.0) - F_w(1.0) > 0;  floor: one severity step (0.2)

Implementation decision, recorded: a run that stopped before severity 0.4 has
no E. Its pair is excluded and counted (n_missing_pairs). The exclusion biases
AGAINST the hypothesis, because a run that fails before 0.4 is a run calibration
already left. A world with fewer than MIN_PAIRS pairs is unevaluable.

Descriptive, no verdicts: the dose response at every strength; the frontier
distribution per cell; and two reads of the overlap diagnostics at strength 0.
  across severities  how often the flag fired at a run's failing severity. It
                     can withdraw the overlap explanation. It cannot confirm
                     it: the flag and the failure both follow severity.
  within severity    at severity 0.4, whether the diagnostics separate failing
                     runs from passing ones.

Extraction of F, the hypothesis row, the never-passed encoding (-0.2) and the
statistics primitives are IMPORTED from scripts/surface_stats.py, so the
replication is judged by the code that produced the observation.
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
from scipy import stats

SCRIPTS = Path(__file__).resolve().parent
ROOT = SCRIPTS.parent
sys.path.insert(0, str(ROOT / "src"))

from cldd import config  # noqa: E402


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_rsr = _load("run_strength_replication")
_ss = _load("surface_stats")

SEEDS = list(_rsr.SEEDS)
WORLDS = tuple(_rsr.WORLDS)
STRENGTHS = list(_rsr.STRENGTHS)
LOW, HIGH = _rsr.STRENGTH_LOW, _rsr.STRENGTH_HIGH
IN_CSV = _rsr.OUT
OUT_CSV = ROOT / "artifacts" / "strength_replication_stats.csv"

ALPHA = _ss.ALPHA
TARGET = config.TARGET_DECLINED_ECE
ECE_COL = "reweight_declined_ece"
PRIMARY_SEVERITY = 0.4
NOISE_SEVERITY = 0.0
MIN_PAIRS = 20
WITHDRAW_AT = 13            # "most" of 25 seeds: the across-severities reading rule
DIAG_COLS = ("propensity_auc", "ess_ratio", "unfunded_below_floor")
FIELDS = list(_ss.SURFACE_STATS_FIELDS)
_ROUND4 = ("median_stat", "mean_stat", "floor")


class Unevaluable(Exception):
    """A confirmatory computation has no defined answer on this artifact."""


# --------------------------------------------------------------------------- #
# Loading + completeness (fail-closed)
# --------------------------------------------------------------------------- #

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
    """Seeds whose RUN consumed anything a committed artifact consumed.

    Checks the consumed span, not the base seed: a run at 1005 is not one of the
    25 spent base seeds, but it re-reads cohorts the run at 1000 already drew.
    """
    spent = set().union(*(_rsr.consumed(s) for s in _rsr.SPENT_SEEDS))
    bad = set()
    for seed in {int(r["seed"]) for r in rows}:
        used = _rsr.consumed(seed)
        if used & spent or min(used) < _rsr.SPENT_CEILING:
            bad.add(seed)
    return sorted(bad)


# --------------------------------------------------------------------------- #
# Per-seed extraction
# --------------------------------------------------------------------------- #

def _cell(rows: list, strength: float, world: str) -> list:
    return [r for r in rows
            if float(r["unobserved_strength"]) == strength and r["generator"] == world]


def ece_by_seed(rows: list, strength: float, world: str, severity: float) -> dict:
    """{seed: control-lever declined ECE} at one walked severity."""
    return {int(r["seed"]): float(r[ECE_COL]) for r in _cell(rows, strength, world)
            if float(r["selection_severity"]) == severity}


def _paired(a: dict, b: dict) -> list:
    return [a[s] - b[s] for s in sorted(set(a) & set(b))]


def _median(values) -> float:
    vals = list(values)
    return float(np.median(vals)) if vals else float("nan")


# --------------------------------------------------------------------------- #
# The primary floor
# --------------------------------------------------------------------------- #

def primary_floor(e_low: dict, noise_low: dict, noise_high: dict) -> tuple:
    """(floor, parts). The larger of the target distance and the noise scale."""
    baseline = _median(e_low.values())
    distance = TARGET - baseline
    if not distance > 0:
        raise Unevaluable(
            f"strength-0 median ECE {baseline:.4f} is already at or over the target "
            f"{TARGET:.2f}; the target-distance floor is undefined")
    noise = _median(abs(d) for d in _paired(noise_high, noise_low))
    if np.isnan(noise):
        raise Unevaluable("no severity-0 pairs; the noise scale is undefined")
    binding = "target_distance" if distance >= noise else "noise_scale"
    return max(distance, noise), {
        "baseline_median": baseline, "target": TARGET, "target_distance": distance,
        "noise_scale": noise, "binding": binding,
    }


# --------------------------------------------------------------------------- #
# Families
# --------------------------------------------------------------------------- #

def _holm(rows: list) -> None:
    sign = _ss._fss.holm_adjust([r["sign_p_raw"] for r in rows])
    wil = _ss._fss.holm_adjust([r["wilcoxon_p_raw"] for r in rows])
    for r, sp, wp in zip(rows, sign, wil):
        r["sign_p_holm"], r["wilcoxon_p_holm"] = sp, wp
        r["confirmed"] = bool(sp <= ALPHA and wp <= ALPHA and r["clears_floor"])


def primary_row(name: str, world: str, rows_in: list) -> dict:
    e_low = ece_by_seed(rows_in, LOW, world, PRIMARY_SEVERITY)
    e_high = ece_by_seed(rows_in, HIGH, world, PRIMARY_SEVERITY)
    diffs = _paired(e_high, e_low)
    n_missing = len(SEEDS) - len(diffs)
    if len(diffs) < MIN_PAIRS:
        raise Unevaluable(
            f"{name}: only {len(diffs)} pairs have a severity-{PRIMARY_SEVERITY} row at both "
            f"strengths (minimum {MIN_PAIRS})")
    floor, parts = primary_floor(
        e_low,
        ece_by_seed(rows_in, LOW, world, NOISE_SEVERITY),
        ece_by_seed(rows_in, HIGH, world, NOISE_SEVERITY),
    )
    row = _ss._hypothesis_row(name, diffs, floor, world=world, strength=HIGH)
    parts["n_missing_pairs"] = n_missing
    row.update(severity=PRIMARY_SEVERITY, role="confirmatory",
               detail_json=json.dumps(parts, sort_keys=True))
    return row


def secondary_row(name: str, world: str, rows_in: list) -> dict:
    row = _ss.hs1_row(name, _ss.frontier_by_seed(rows_in, LOW, world),
                      _ss.frontier_by_seed(rows_in, HIGH, world))
    row.update(strength=HIGH, role="secondary")
    return row


# --------------------------------------------------------------------------- #
# Descriptive reads
# --------------------------------------------------------------------------- #

def _descriptive(metric: str, world: str, strength: float, **kw) -> dict:
    row = _ss._row_defaults()
    row.update(metric=metric, hypothesis="", world=world, strength=strength,
               role="descriptive", direction="n/a", confirmed=None, detail_json="")
    row.update(kw)
    return row


def dose_row(world: str, strength: float, rows_in: list) -> dict:
    diffs = _paired(ece_by_seed(rows_in, strength, world, PRIMARY_SEVERITY),
                    ece_by_seed(rows_in, LOW, world, PRIMARY_SEVERITY))
    return _descriptive(
        "dose_ece", world, strength, severity=PRIMARY_SEVERITY, n_seeds=len(diffs),
        median_stat=_median(diffs),
        mean_stat=float(np.mean(diffs)) if diffs else float("nan"),
        sign_k=sum(1 for d in diffs if d > 0), sign_n=len(diffs),
    )


def cell_frontier_row(world: str, strength: float, rows_in: list) -> dict:
    vals = list(_ss.frontier_by_seed(rows_in, strength, world).values())
    counts: dict = {}
    for v in vals:
        counts[str(v)] = counts.get(str(v), 0) + 1
    return _descriptive(
        "cell_frontier", world, strength, n_seeds=len(vals), median_stat=_median(vals),
        mean_stat=float(np.mean(vals)) if vals else float("nan"),
        n_never_passed=sum(1 for x in vals if x == _ss.NEVER_PASSED),
        detail_json=json.dumps(counts, sort_keys=True),
    )


def flag_across_row(world: str, rows_in: list) -> dict:
    """Across severities, strength 0: the flag at each run's failing round."""
    cell = _cell(rows_in, LOW, world)
    table = {"flagged_passed": 0, "flagged_failed": 0, "clear_passed": 0, "clear_failed": 0}
    for r in cell:
        flag = "flagged" if r["diag_flagged"] == "True" else "clear"
        outcome = "passed" if r["passed"] == "True" else "failed"
        table[f"{flag}_{outcome}"] += 1
    failing = table["flagged_failed"] + table["clear_failed"]
    # A loop stops at its first failing round, so clear_failed counts seeds.
    table["withdraw_at"] = WITHDRAW_AT
    table["overlap_explanation_withdrawn"] = table["clear_failed"] >= WITHDRAW_AT
    return _descriptive(
        "flag_at_failing_severity", world, LOW, n_seeds=len({r["seed"] for r in cell}),
        sign_k=table["flagged_failed"], sign_n=failing,
        detail_json=json.dumps(table, sort_keys=True),
    )


def diag_within_row(world: str, rows_in: list) -> dict:
    """Within severity 0.4, strength 0: do the diagnostics separate fail from pass?"""
    cell = [r for r in _cell(rows_in, LOW, world)
            if float(r["selection_severity"]) == PRIMARY_SEVERITY]
    failing = [r for r in cell if r["passed"] != "True"]
    passing = [r for r in cell if r["passed"] == "True"]
    ece = [float(r[ECE_COL]) for r in cell]
    detail = {"n_failing": len(failing), "n_passing": len(passing),
              "median_failing": {}, "median_passing": {}, "spearman_vs_ece": {}}
    for col in DIAG_COLS:
        detail["median_failing"][col] = _median(float(r[col]) for r in failing)
        detail["median_passing"][col] = _median(float(r[col]) for r in passing)
        values = [float(r[col]) for r in cell]
        if len(set(values)) > 1 and len(set(ece)) > 1:
            rho = stats.spearmanr(values, ece)
            detail["spearman_vs_ece"][col] = {"rho": float(rho.statistic), "p": float(rho.pvalue)}
        else:
            detail["spearman_vs_ece"][col] = {"rho": float("nan"), "p": float("nan")}
    return _descriptive(
        "diag_within_severity", world, LOW, severity=PRIMARY_SEVERITY, n_seeds=len(cell),
        detail_json=json.dumps(detail, sort_keys=True),
    )


def build_rows(rows_in: list) -> list:
    primary = [primary_row("H-R1" + sfx, w, rows_in) for sfx, w in (("f", "flat"), ("s", "scm"))]
    _holm(primary)
    secondary = [secondary_row("H-R2" + sfx, w, rows_in) for sfx, w in (("f", "flat"), ("s", "scm"))]
    _holm(secondary)

    rows = primary + secondary
    for world in WORLDS:
        for strength in STRENGTHS:
            if strength != LOW:
                rows.append(dose_row(world, strength, rows_in))
    for world in WORLDS:
        for strength in STRENGTHS:
            rows.append(cell_frontier_row(world, strength, rows_in))
    for world in WORLDS:
        rows.append(flag_across_row(world, rows_in))
    for world in WORLDS:
        rows.append(diag_within_row(world, rows_in))
    return rows


def write_stats_csv(rows: list, out: Path) -> pd.DataFrame:
    frame = pd.DataFrame(rows, columns=FIELDS)
    for col in _ROUND4:
        frame[col] = frame[col].apply(lambda v: v if pd.isna(v) else round(float(v), 4))
    out.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(out, index=False)
    return frame


def _verdict_lines(rows: list, role: str) -> None:
    for r in rows:
        if r["metric"] != "hypothesis" or r["role"] != role:
            continue
        verdict = "CONFIRMED" if r["confirmed"] else "not confirmed"
        print("  %s [%s]: median=%+.4f (n=%d) sign %d/%d p_holm=%.3e; "
              "wilcoxon p_holm=%.3e; floor=%.4f clears=%s -> %s"
              % (r["hypothesis"], r["world"], r["median_stat"], r["n_seeds"],
                 r["sign_k"], r["sign_n"], r["sign_p_holm"],
                 r["wilcoxon_p_holm"], r["floor"], r["clears_floor"], verdict))
        if role == "confirmatory":
            print("    floor parts: " + r["detail_json"])
        if r["n_never_passed"]:
            print("    NOTE: %d never-passed frontier cell(s) encoded as %.1f"
                  % (r["n_never_passed"], _ss.NEVER_PASSED))


def print_summary(rows: list) -> None:
    print("CLDD strength-1.0 replication -- stats summary")
    print("output: " + str(OUT_CSV))
    print("")
    print("PRIMARY family: calibration error at severity %.1f "
          "(m=2, Holm alpha=%.2f, both tests + floor)" % (PRIMARY_SEVERITY, ALPHA))
    _verdict_lines(rows, "confirmatory")
    print("")
    print("SECONDARY family: frontier (m=2, its own Holm)")
    _verdict_lines(rows, "secondary")
    print("")
    n = sum(1 for r in rows if r["role"] == "confirmatory" and r["confirmed"])
    print("strength-1.0 observation, primary outcome: %s"
          % ("REPLICATED in both worlds" if n == 2 else
             "REPLICATED in %d of 2 worlds" % n if n else "NOT REPLICATED"))
    print("")
    for r in rows:
        if r["metric"] == "dose_ece":
            print("dose [%s] 0 -> %.2f at severity %.1f: median %+.4f, rising %d/%d"
                  % (r["world"], r["strength"], r["severity"], r["median_stat"],
                     r["sign_k"], r["sign_n"]))
    print("")
    for r in rows:
        if r["metric"] == "cell_frontier":
            print("frontier [%s] strength %.2f: median %.2f  %s"
                  % (r["world"], r["strength"], r["median_stat"], r["detail_json"]))
    print("")
    for r in rows:
        if r["metric"] == "flag_at_failing_severity":
            withdrawn = json.loads(r["detail_json"])["overlap_explanation_withdrawn"]
            print("flag, across severities [%s] strength 0: fired at the failing severity "
                  "on %d of %d runs -> overlap explanation %s  %s"
                  % (r["world"], r["sign_k"], r["sign_n"],
                     "WITHDRAWN" if withdrawn else "not withdrawn (and not confirmed)",
                     r["detail_json"]))
    for r in rows:
        if r["metric"] == "diag_within_severity":
            print("diagnostics, within severity %.1f [%s] strength 0: %s"
                  % (r["severity"], r["world"], r["detail_json"]))


def main() -> int:
    rows_in = _read_rows(IN_CSV)

    spent = spent_seed_rows(rows_in)
    if spent:
        print("FAIL-CLOSED: runs that consumed spent seeds are in the artifact: %s" % spent[:10])
        return 1
    miss = missing_cells(rows_in)
    if miss:
        print("FAIL-CLOSED: missing cells -- confirmatory stats are unevaluable")
        print("  missing (%d): %s" % (len(miss), miss[:10]))
        return 1
    try:
        rows = build_rows(rows_in)
    except Unevaluable as exc:
        print("FAIL-CLOSED: unevaluable -- %s" % exc)
        return 1

    write_stats_csv(rows, OUT_CSV)
    print_summary(rows)
    return 0


if __name__ == "__main__":
    sys.exit(main())
