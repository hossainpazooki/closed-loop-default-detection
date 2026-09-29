"""CLDD Option C segmented-selection analysis.

Recomputes every to-be-published number from artifacts/segment_frontier.csv
(never from memory), enforces the I-C1 byte-identity embed gate against the
v4env spaced baseline, and writes artifacts/segment_stats.csv. Exits non-zero
-- publication mechanically blocked -- if any confirmatory computation is
unevaluable (missing cells: fail-closed) or the integrity control fails.

Notation, per seed, world w, policy cell p:
  E_w(p)  declined ECE of the loop's control lever at severity 0.0 (round 0:
          selection is random inside each segment, so nothing is hidden and the
          policy's structure is the ONLY selection effect)
  F_w(p)  the loop's frontier severity

Confirmatory family (m=4, Holm alpha=0.05, one-sided exact sign test AND
one-sided Wilcoxon, both must clear, plus the floors). PRIMARY is the first
attack feature at knockout depth 1 against depth 0:
  H-C1f / H-C1s  E_w(d1) - E_w(d0) > 0
                 floor: median diff >= median |E_w(d0) - E_w(legacy)|
                 (the re-cut noise scale: same rate, cutoff moved inside segments)
  H-C2f / H-C2s  F_w(d0) - F_w(d1) > 0
                 floor: median diff >= one severity step (0.2)

Placebo control (flat, outside the family, unadjusted): the same E contrast on
a feature with no risk coefficient. It is expected NOT to move. If it moves,
H-C1f cannot be attributed to losing overlap in a risk-relevant direction.

Encoding decision (inherited from surface_stats.py): a run that never passed
severity 0 has frontier -0.2, one grid step below the minimum; counted per row
in n_never_passed.

Statistics primitives are imported from scripts/feedback_sweep_stats.py so this
script uses the exact v3/v4 implementations. Deterministic; ASCII-only stdout.
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


_rgs = _load("run_segment_sweep")
_fss = _load("feedback_sweep_stats")

SEEDS = list(_rgs.SEEDS)
WORLDS = tuple(_rgs.WORLDS)
LEGACY = _rgs.LEGACY
SEG_CSV = _rgs.SEG_OUT
SPACED_FR = _rgs.SPACED_FR
FR_FIELDS = list(_rgs.FR_FIELDS)
OUT_CSV = ROOT / "artifacts" / "segment_stats.csv"

ALPHA = 0.05
NEVER_PASSED = -0.2          # one grid step below the minimum passable severity
GRID_STEP_FLOOR = 0.2        # H-C2 floor: one severity step
PRIMARY_SEVERITY = 0.0       # E is read at round 0

PRIMARY_FEATURE, PRIMARY_END = _rgs.ATTACK_FEATURES[0]
PRIMARY_D0 = _rgs.policy_id(PRIMARY_FEATURE, PRIMARY_END, 0.0)
PRIMARY_D1 = _rgs.policy_id(PRIMARY_FEATURE, PRIMARY_END, 1.0)
PLACEBO_D0 = _rgs.policy_id(*_rgs.PLACEBO_FEATURE, 0.0)
PLACEBO_D1 = _rgs.policy_id(*_rgs.PLACEBO_FEATURE, 1.0)

SEGMENT_STATS_FIELDS = [
    "metric", "hypothesis", "world", "policy_id", "severity", "role", "direction",
    "n_seeds", "median_stat", "mean_stat", "floor", "clears_floor",
    "sign_k", "sign_n", "sign_p_raw", "sign_p_holm",
    "wilcoxon_stat", "wilcoxon_p_raw", "wilcoxon_p_holm", "confirmed",
    "n_never_passed", "detail_json",
]
_ROUND4 = ("median_stat", "mean_stat", "floor")


# --------------------------------------------------------------------------- #
# Loading + completeness (fail-closed)
# --------------------------------------------------------------------------- #

def _read_rows(path: Path) -> list:
    if not path.exists():
        raise FileNotFoundError(f"{path} missing -- run scripts/run_segment_sweep.py first")
    with path.open(newline="") as f:
        return list(csv.DictReader(f))


def missing_cells(rows: list) -> list:
    have = {(r["policy_id"], r["generator"], int(r["seed"])) for r in rows}
    return [(c["policy_id"], c["world"], s) for c in _rgs.policy_cells() for s in SEEDS
            if (c["policy_id"], c["world"], s) not in have]


def _group(rows: list, key_fn) -> dict:
    out: dict = {}
    for r in rows:
        out.setdefault(key_fn(r), []).append(r)
    return out


# --------------------------------------------------------------------------- #
# I-C1 byte-identity embed gate
# --------------------------------------------------------------------------- #

def ic1_check(segment_csv: Path, spaced_csv: Path, fields: list, seeds: list,
              worlds) -> list:
    """Legacy-cell rows must be string-equal per shared column with the spaced
    artifact, per (world, seed), in iteration order."""
    seg = _group([r for r in _read_rows(segment_csv) if r["policy_id"] == LEGACY],
                 lambda r: (r["generator"], int(r["seed"])))
    ref = _group(_read_rows(spaced_csv), lambda r: (r["generator"], int(r["seed"])))
    problems: list = []
    for world in worlds:
        for seed in seeds:
            got = sorted(seg.get((world, seed), []), key=lambda r: int(r["iteration"]))
            want = sorted(ref.get((world, seed), []), key=lambda r: int(r["iteration"]))
            label = f"I-C1 legacy [{world}] seed={seed}"
            if not want:
                # fail-closed: absent-from-both-sides must not zip to a silent pass
                problems.append(f"{label}: reference cell absent (gate cannot verify)")
                continue
            if len(got) != len(want):
                problems.append(f"{label}: {len(got)} rows != spaced {len(want)}")
                continue
            for i, (g, w) in enumerate(zip(got, want)):
                for f in fields:
                    if g.get(f, "") != w.get(f, ""):
                        problems.append(f"{label} row {i} col {f}: {g.get(f)!r} != {w.get(f)!r}")
    return problems


# --------------------------------------------------------------------------- #
# Per-seed extraction
# --------------------------------------------------------------------------- #

def _cell_rows(rows: list, policy: str, world: str) -> list:
    return [r for r in rows if r["policy_id"] == policy and r["generator"] == world]


def ece_by_seed(rows: list, policy: str, world: str,
                severity: float = PRIMARY_SEVERITY) -> dict:
    """{seed: control-lever declined ECE} at one walked severity."""
    out: dict = {}
    for r in _cell_rows(rows, policy, world):
        if float(r["selection_severity"]) == severity:
            out[int(r["seed"])] = float(r["control_metric"])
    return out


def frontier_by_seed(rows: list, policy: str, world: str) -> dict:
    """{seed: frontier_severity}; '' (never passed) -> NEVER_PASSED."""
    out: dict = {}
    for r in _cell_rows(rows, policy, world):
        raw = r["frontier_severity"]
        out[int(r["seed"])] = NEVER_PASSED if raw in ("", "None") else float(raw)
    return out


def diag_confusion(rows: list, policy: str, world: str) -> dict:
    """Counts over every walked round of one cell: flag state x pass state."""
    counts = {"flagged_passed": 0, "flagged_failed": 0,
              "clear_passed": 0, "clear_failed": 0}
    for r in _cell_rows(rows, policy, world):
        flag = "flagged" if r["diag_flagged"] == "True" else "clear"
        outcome = "passed" if r["passed"] == "True" else "failed"
        counts[f"{flag}_{outcome}"] += 1
    return counts


# --------------------------------------------------------------------------- #
# Hypothesis rows
# --------------------------------------------------------------------------- #

def _row_defaults() -> dict:
    return {k: float("nan") for k in SEGMENT_STATS_FIELDS}


def _paired(a: dict, b: dict) -> list:
    return [a[s] - b[s] for s in sorted(set(a) & set(b))]


def _hypothesis_row(name: str, diffs: list, floor: float, world: str, policy: str,
                    role: str = "confirmatory") -> dict:
    sign = _fss.sign_test(diffs, "positive")
    wil = _fss.wilcoxon_test(diffs, "positive")
    median = float(np.median(diffs)) if diffs else float("nan")
    row = _row_defaults()
    row.update(
        metric="hypothesis", hypothesis=name, world=world, policy_id=policy,
        severity=PRIMARY_SEVERITY, role=role, direction="positive",
        n_seeds=len(diffs), median_stat=median,
        mean_stat=float(np.mean(diffs)) if diffs else float("nan"),
        floor=floor, clears_floor=bool(diffs and median >= floor),
        sign_k=sign["k"], sign_n=sign["n"], sign_p_raw=sign["p"],
        wilcoxon_stat=wil["stat"], wilcoxon_p_raw=wil["p"],
        confirmed=None, n_never_passed=0, detail_json="",
    )
    return row


def recut_floor(e_d0: dict, e_legacy: dict) -> float:
    """Median |E(d0) - E(legacy)|: what moving the cutoff inside segments costs
    with no change in any segment's rate. The noise scale of the E contrast."""
    diffs = _paired(e_d0, e_legacy)
    return float(np.median([abs(d) for d in diffs])) if diffs else float("nan")


def hc1_row(name: str, world: str, policy: str, e_d1: dict, e_d0: dict,
            e_legacy: dict, role: str = "confirmatory") -> dict:
    return _hypothesis_row(name, _paired(e_d1, e_d0), recut_floor(e_d0, e_legacy),
                           world, policy, role=role)


def hc2_row(name: str, world: str, policy: str, f_d0: dict, f_d1: dict) -> dict:
    row = _hypothesis_row(name, _paired(f_d0, f_d1), GRID_STEP_FLOOR, world, policy)
    row["severity"] = float("nan")
    row["n_never_passed"] = sum(
        1 for d in (f_d0, f_d1) for v in d.values() if v == NEVER_PASSED
    )
    return row


def _moved(row: dict) -> bool:
    """Unadjusted criterion for the placebo: both tests at alpha AND the floor."""
    return bool(row["sign_p_raw"] <= ALPHA and row["wilcoxon_p_raw"] <= ALPHA
                and row["clears_floor"])


def build_rows(rows_in: list) -> list:
    rows: list = []

    # -- confirmatory family (m = 4) ---------------------------------------- #
    for suffix, world in (("f", "flat"), ("s", "scm")):
        rows.append(hc1_row(
            "H-C1" + suffix, world, PRIMARY_D1,
            ece_by_seed(rows_in, PRIMARY_D1, world),
            ece_by_seed(rows_in, PRIMARY_D0, world),
            ece_by_seed(rows_in, LEGACY, world),
        ))
    for suffix, world in (("f", "flat"), ("s", "scm")):
        rows.append(hc2_row(
            "H-C2" + suffix, world, PRIMARY_D1,
            frontier_by_seed(rows_in, PRIMARY_D0, world),
            frontier_by_seed(rows_in, PRIMARY_D1, world),
        ))
    conf = rows[:4]
    sign_holm = _fss.holm_adjust([r["sign_p_raw"] for r in conf])
    wil_holm = _fss.holm_adjust([r["wilcoxon_p_raw"] for r in conf])
    for r, sp, wp in zip(conf, sign_holm, wil_holm):
        r["sign_p_holm"], r["wilcoxon_p_holm"] = sp, wp
        r["confirmed"] = bool(sp <= ALPHA and wp <= ALPHA and r["clears_floor"])

    # -- placebo control (flat, unadjusted, outside the family) ------------- #
    placebo = hc1_row(
        "placebo", "flat", PLACEBO_D1,
        ece_by_seed(rows_in, PLACEBO_D1, "flat"),
        ece_by_seed(rows_in, PLACEBO_D0, "flat"),
        ece_by_seed(rows_in, LEGACY, "flat"),
        role="control",
    )
    placebo["confirmed"] = _moved(placebo)   # True = the placebo MOVED
    rows.append(placebo)

    # -- descriptive: one frontier row, one E row, one diagnostics row per cell
    for cell in _rgs.policy_cells():
        policy, world = cell["policy_id"], cell["world"]
        f = list(frontier_by_seed(rows_in, policy, world).values())
        row = _row_defaults()
        row.update(metric="cell_frontier", hypothesis="", world=world, policy_id=policy,
                   role="descriptive", direction="n/a", n_seeds=len(f),
                   median_stat=float(np.median(f)) if f else float("nan"),
                   mean_stat=float(np.mean(f)) if f else float("nan"),
                   n_never_passed=sum(1 for x in f if x == NEVER_PASSED),
                   detail_json=json.dumps({"min": min(f), "max": max(f)} if f else {}))
        rows.append(row)
        e = list(ece_by_seed(rows_in, policy, world).values())
        row = _row_defaults()
        row.update(metric="cell_ece", hypothesis="", world=world, policy_id=policy,
                   severity=PRIMARY_SEVERITY, role="descriptive", direction="n/a",
                   n_seeds=len(e),
                   median_stat=float(np.median(e)) if e else float("nan"),
                   mean_stat=float(np.mean(e)) if e else float("nan"),
                   detail_json=json.dumps({"min": min(e), "max": max(e)} if e else {}))
        rows.append(row)
        row = _row_defaults()
        row.update(metric="cell_diagnostics", hypothesis="", world=world,
                   policy_id=policy, role="descriptive", direction="n/a",
                   n_seeds=len(f),
                   detail_json=json.dumps(diag_confusion(rows_in, policy, world),
                                          sort_keys=True))
        rows.append(row)
    return rows


def write_stats_csv(rows: list, out: Path) -> pd.DataFrame:
    frame = pd.DataFrame(rows, columns=SEGMENT_STATS_FIELDS)
    for col in _ROUND4:
        frame[col] = frame[col].apply(lambda v: v if pd.isna(v) else round(float(v), 4))
    out.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(out, index=False)
    return frame


def print_summary(rows: list) -> None:
    print("CLDD Option C segmented selection -- stats summary")
    print("output: " + str(OUT_CSV))
    print("primary contrast: %s vs %s" % (PRIMARY_D1, PRIMARY_D0))
    print("")
    conf = [r for r in rows if r["metric"] == "hypothesis" and r["role"] == "confirmatory"]
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
    print("")
    placebo = next(r for r in rows if r["role"] == "control")
    print("placebo [flat] %s: median=%+.4f sign %d/%d p=%.3e; floor=%.4f -> %s"
          % (placebo["policy_id"], placebo["median_stat"], placebo["sign_k"],
             placebo["sign_n"], placebo["sign_p_raw"], placebo["floor"],
             "MOVED" if placebo["confirmed"] else "held"))
    hc1f = next(r for r in conf if r["hypothesis"] == "H-C1f")
    if hc1f["confirmed"] and placebo["confirmed"]:
        print("  QUALIFY: H-C1f confirmed but the placebo moved too -- the shift is not "
              "attributable to a risk-relevant direction")
    print("")
    wall = all(r["confirmed"] for r in conf if r["hypothesis"].startswith("H-C2"))
    print("overlap-wall explanation: %s (stated as measured only if H-C2f AND H-C2s "
          "are confirmed)" % ("SUPPORTED" if wall else "NOT SUPPORTED"))
    print("")
    for r in rows:
        if r["metric"] == "cell_diagnostics":
            print("diagnostics [%s] %s: %s" % (r["world"], r["policy_id"], r["detail_json"]))


def main() -> int:
    rows_in = _read_rows(SEG_CSV)

    miss = missing_cells(rows_in)
    if miss:
        print("FAIL-CLOSED: missing cells -- confirmatory stats are unevaluable")
        print("  missing (%d): %s" % (len(miss), miss[:10]))
        return 1

    problems = ic1_check(SEG_CSV, SPACED_FR, fields=FR_FIELDS, seeds=SEEDS, worlds=WORLDS)
    if problems:
        print("I-C1 BYTE-IDENTITY EMBED GATE FAILED (driver-plumbing bug or build drift):")
        for p in problems[:20]:
            print("  " + p)
        print("  (%d problems total)" % len(problems))
        return 1
    print("I-C1 embed gate: PASS (legacy cells string-equal to the spaced artifact)")
    print("")

    rows = build_rows(rows_in)
    write_stats_csv(rows, OUT_CSV)
    print_summary(rows)
    return 0


if __name__ == "__main__":
    sys.exit(main())
