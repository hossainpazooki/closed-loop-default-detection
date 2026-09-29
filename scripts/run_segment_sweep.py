"""CLDD Option C segmented-selection sweep (frontier leg, both worlds).

Policy cells x worlds x 25 spaced seeds = 400 loop runs
  -> artifacts/segment_frontier.csv  (leading policy columns + the
     frontier_sweep_spaced.csv schema + control/diagnostic columns)

Cells:
  legacy                      the single global cutoff (policy None), both worlds.
                              Re-runs the spaced configurations exactly, so it is
                              the I-C1 byte-identity embed cell.
  attack features x depths    knockout of one end-quintile of a RISK-RELEVANT
                              observed feature, both worlds.
  placebo feature x depths    the same knockout on a feature with NO risk
                              coefficient and an independent draw (flat only --
                              the SCM has no such column in its risk logit AND
                              its DAG).

Same discipline as scripts/run_surface_sweep.py, whose helpers this driver
imports rather than copies: ONE SUBPROCESS PER RUN, strictly sequential,
resumable append keyed on (policy_id, world, seed), ASCII-only stdout. No
committed artifact is ever written; artifacts/surface_env.json is READ, never
rewritten.

Usage:
    python scripts/run_segment_sweep.py --pilot     # ~2 min gate, run FIRST
    python scripts/run_segment_sweep.py             # full matrix (~70 min)
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import platform
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

SEEDS = list(_rss.SEEDS)                      # the spaced set {1000 + 16i}
WORLDS = tuple(_rss.WORLDS)                   # ("flat", "scm")
FR_FIELDS = list(_rss.FR_FIELDS)
SPACED_FR = _rss.SPACED_FR                    # frontier_sweep_spaced_v4env.csv
ENV_MANIFEST = _rss.ENV_MANIFEST              # surface_env.json (read-only here)

APPROVAL_RATE = 0.6                           # config.DEFAULT_APPROVAL_RATE
N_SEGMENTS = 5
DEPTHS = [0.0, 0.5, 1.0]
# (feature, knockout_end): the end a lender would actually decline.
ATTACK_FEATURES = [("aggregate_credit_utilization", "high"), ("vintage_years", "low")]
PLACEBO_FEATURE = ("requested_amount", "high")
PLACEBO_DEPTHS = [0.0, 1.0]
PLACEBO_WORLDS = ("flat",)
LEGACY = "legacy"

SEG_OUT = ROOT / "artifacts" / "segment_frontier.csv"
PILOT_DIR = ROOT / "artifacts" / "segment_pilot"

POLICY_FIELDS = ["policy_id", "segment_feature", "knockout_end", "knockout_depth"]
EXTRA_FIELDS = ["control_metric", "approval_rate", "propensity_auc", "ess_ratio",
                "unfunded_below_floor", "diag_flagged"]
SEG_FIELDS = POLICY_FIELDS + FR_FIELDS + EXTRA_FIELDS

PILOT_LOOP_BUDGET_S = 60.0


def policy_id(feature: str, end: str, depth: float) -> str:
    return f"{feature}:{end}:d{depth:.1f}"


def policy_cells() -> list:
    """Every (policy, world) cell of the matrix, as dicts. 16 cells x 25 seeds = 400."""
    cells = [{"policy_id": LEGACY, "feature": "", "end": "", "depth": None, "world": w}
             for w in WORLDS]
    for feature, end in ATTACK_FEATURES:
        for depth in DEPTHS:
            for w in WORLDS:
                cells.append({"policy_id": policy_id(feature, end, depth),
                              "feature": feature, "end": end, "depth": depth, "world": w})
    feature, end = PLACEBO_FEATURE
    for depth in PLACEBO_DEPTHS:
        for w in PLACEBO_WORLDS:
            cells.append({"policy_id": policy_id(feature, end, depth),
                          "feature": feature, "end": end, "depth": depth, "world": w})
    return cells


_SEG_CHILD = """\
import json
from cldd.loop import SelectiveLabelsLoop
from cldd.selection import SegmentedSelection, knockout_rates

feature, end, depth = {feature!r}, {end!r}, {depth!r}
kwargs = None
if depth is not None:
    kwargs = {{"selection_policy": SegmentedSelection(
        feature, knockout_rates(depth, {approval_rate}, {n_segments}), knockout_end=end)}}
loop = SelectiveLabelsLoop(
    improve_mode="both", generator={generator!r}, seed={seed}, generator_kwargs=kwargs,
)
result = loop.run()
frontier = result.frontier_severity
for r in result.rounds:
    d = r.diagnostics
    row = {{
        "policy_id": {policy_id!r},
        "segment_feature": feature,
        "knockout_end": end,
        "knockout_depth": "" if depth is None else depth,
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
        "control_metric": r.control_metric,
        "approval_rate": r.approval_rate,
        "propensity_auc": d.propensity_auc,
        "ess_ratio": d.ess_ratio,
        "unfunded_below_floor": d.unfunded_below_floor,
        "diag_flagged": d.flagged,
    }}
    print(json.dumps(row))
"""


def child_code(cell: dict, seed: int) -> str:
    return _SEG_CHILD.format(
        feature=cell["feature"], end=cell["end"], depth=cell["depth"],
        approval_rate=APPROVAL_RATE, n_segments=N_SEGMENTS,
        generator=cell["world"], seed=seed, policy_id=cell["policy_id"],
    )


def _key(row: dict) -> tuple:
    return (row["policy_id"], row["generator"], int(row["seed"]))


def missing_keys(out: Path) -> list:
    done = _rss._done_keys(out, _key)
    return [(c["policy_id"], c["world"], s) for c in policy_cells() for s in SEEDS
            if (c["policy_id"], c["world"], s) not in done]


def run_matrix(out: Path) -> None:
    done = _rss._done_keys(out, _key)
    cells = policy_cells()
    total = len(cells) * len(SEEDS)
    n = 0
    for cell in cells:
        for seed in SEEDS:
            n += 1
            label = f"policy={cell['policy_id']} world={cell['world']} seed={seed}"
            if (cell["policy_id"], cell["world"], seed) in done:
                print(f"[{n}/{total}] skip {label}", flush=True)
                continue
            print(f"[{n}/{total}] loop {label} ...", flush=True)
            rows = _rss._run_child(child_code(cell, seed))
            for row in rows:
                _rss._append(out, SEG_FIELDS, row)
            frontier = rows[-1]["frontier_severity"] if rows else None
            print(f"  {len(rows)} rounds, frontier_severity={frontier}", flush=True)
    print(f"segment sweep complete -> {out} (missing keys: {len(missing_keys(out))})",
          flush=True)


# --------------------------------------------------------------------------- #
# Pilot gate -- must pass BEFORE the matrix is launched
# --------------------------------------------------------------------------- #

def current_env() -> dict:
    """The same fields scripts/run_spaced_sweeps.py records, computed read-only."""
    import numpy
    import sklearn
    return {
        "python_implementation": platform.python_implementation(),
        "python_version": platform.python_version(),
        "python_build": list(platform.python_build()),
        "platform": platform.platform(),
        "machine": platform.machine(),
        "numpy": numpy.__version__,
        "scikit_learn": sklearn.__version__,
    }


def env_drift(manifest_path: Path = ENV_MANIFEST) -> list:
    """Fields where this build differs from the recorded one. Informational: the
    byte-identity match below is the gate, this explains a failure of it."""
    recorded = json.loads(manifest_path.read_text(encoding="utf-8"))
    now = current_env()
    return [f"{k}: recorded {recorded.get(k)!r} != current {now.get(k)!r}"
            for k in sorted(set(recorded) | set(now)) if recorded.get(k) != now.get(k)]


def _cell(policy: str, world: str) -> dict:
    for c in policy_cells():
        if c["policy_id"] == policy and c["world"] == world:
            return c
    raise KeyError((policy, world))


def run_pilot() -> int:
    print("PILOT GATE (Option C) -- seed %d only" % SEEDS[0], flush=True)
    seed = SEEDS[0]
    failures: list = []
    PILOT_DIR.mkdir(parents=True, exist_ok=True)
    pilot_csv = PILOT_DIR / "pilot_segment.csv"
    if pilot_csv.exists():
        pilot_csv.unlink()    # pilot scratch only -- committed artifacts are never touched

    drift = env_drift()
    for line in drift:
        print("env drift: " + line, flush=True)
    if not drift:
        print("env: matches artifacts/surface_env.json", flush=True)

    # (b1) non-vacuity + isolation, in-process: a knockout moves the funding mask
    # and ONLY the funding mask.
    print("isolation: knockout vs legacy cohorts, both worlds ...", flush=True)
    sys.path.insert(0, str(ROOT / "src"))
    import numpy as np
    import pandas as pd
    from cldd.loop import make_generator
    from cldd.selection import SegmentedSelection, knockout_rates
    feature, end = ATTACK_FEATURES[0]
    knock = SegmentedSelection(feature, knockout_rates(1.0, APPROVAL_RATE, N_SEGMENTS),
                               knockout_end=end)
    for world in WORLDS:
        kw = dict(severity=0.4, seed=seed, n_applicants=1000, approval_rate=APPROVAL_RATE)
        base = make_generator(world, **kw).generate_cohort()
        seg = make_generator(world, **kw, selection_policy=knock).generate_cohort()
        try:
            pd.testing.assert_frame_equal(base["features"], seg["features"])
        except AssertionError:
            failures.append(f"isolation [{world}]: features moved under a policy")
        if not np.array_equal(base["true_default"], seg["true_default"]):
            failures.append(f"isolation [{world}]: planted defaults moved under a policy")
        if np.array_equal(base["approved"], seg["approved"]):
            failures.append(f"non-vacuity [{world}]: funding mask identical under a knockout")
        if seg["approved"][seg["segment"] == 0].any():
            failures.append(f"non-vacuity [{world}]: knocked-out segment has funded rows")

    # loop pilot runs: legacy + the attack feature at depth 0 and 1, both worlds.
    d0, d1 = policy_id(feature, end, 0.0), policy_id(feature, end, 1.0)
    for world in WORLDS:
        for pol in (LEGACY, d0, d1):
            t0 = time.monotonic()
            print(f"loop pilot {pol} [{world}] seed={seed} ...", flush=True)
            rows = _rss._run_child(child_code(_cell(pol, world), seed))
            dt = time.monotonic() - t0
            for row in rows:
                _rss._append(pilot_csv, SEG_FIELDS, row)
            print(f"  {len(rows)} rounds in {dt:.0f} s", flush=True)
            if dt > PILOT_LOOP_BUDGET_S:
                failures.append(
                    f"budget trip-wire: {pol} [{world}] took {dt:.0f} s "
                    f"> {PILOT_LOOP_BUDGET_S:.0f} s -- STOP, re-scope by spec revision"
                )

    # (a) I-C1 in miniature: legacy pilot rows == committed spaced rows.
    got = _rss._rows_by_key(pilot_csv, lambda r: (r["policy_id"], r["generator"]))
    ref = _rss._rows_by_key(SPACED_FR, lambda r: (r["generator"], int(r["seed"])))
    for world in WORLDS:
        want = ref.get((world, seed), [])
        if not want:
            failures.append(f"I-C1 {world}: reference cell absent (gate cannot verify)")
            continue
        failures += _rss._string_match(got.get((LEGACY, world), []), want, FR_FIELDS,
                                       f"I-C1 legacy [{world}]")

    # (b2) non-vacuity at the loop level: round 0 moves between depth 0 and depth 1.
    for world in WORLDS:
        r0, r1 = got.get((d0, world), []), got.get((d1, world), [])
        if not r0 or not r1:
            failures.append(f"non-vacuity [{world}]: missing pilot rows")
        elif r0[0]["control_metric"] == r1[0]["control_metric"]:
            failures.append(f"non-vacuity [{world}]: round-0 control metric identical "
                            f"at depth 0 and depth 1")

    print("", flush=True)
    if failures:
        for msg in failures:
            print("FAIL: " + msg, flush=True)
        if drift:
            print("NOTE: the build differs from the recorded one (see env drift above). "
                  "If I-C1 failed in the last digits only, re-anchor by spec revision "
                  "(v4 Amendment Rev 1.1 precedent) -- never loosen the comparison.",
                  flush=True)
        print("PILOT GATE FAIL -- DO NOT launch the matrix", flush=True)
        return 1
    print("PILOT GATE PASS -- byte-match + isolation + non-vacuity + budget all hold; "
          "matrix may launch", flush=True)
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--pilot", action="store_true", help="run the pilot gate only")
    args = ap.parse_args()
    if args.pilot:
        return run_pilot()
    run_matrix(SEG_OUT)
    miss = missing_keys(SEG_OUT)
    print(f"SEGMENT SWEEP COMPLETE -- missing keys: {len(miss)}", flush=True)
    return 0 if not miss else 1


if __name__ == "__main__":
    sys.exit(main())
