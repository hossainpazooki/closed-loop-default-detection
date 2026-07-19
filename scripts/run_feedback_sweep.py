"""v3 profit-decomposition sweep driver: 450 FeedbackLoop runs, one subprocess each.

    python scripts/run_feedback_sweep.py --list-keys     # enumerate the 450 keys, no runs
    python scripts/run_feedback_sweep.py --quick          # pilot: 6 runs (seed 1000, sev 0.4)
    python scripts/run_feedback_sweep.py                  # full matrix, --workers 4 default
    python scripts/run_feedback_sweep.py --workers 8

Matrix (spec docs/superpowers/specs/2026-07-14-cldd-v3-design.md section 4, decision
records 7-8): seeds {1000 + 16*i : i = 0..24} x severity {0.2, 0.4, 1.0} x
exploration_rate {0, 0.05} x arm {treatment, frozen, prior}, n_generations=12,
generator="scm" -> 450 runs, 5400 generation rows. Arms map to FeedbackLoop flags:

    treatment: retrain=True,  policy_mode="model"   (today's FeedbackLoop, byte-identical)
    frozen:    retrain=False, policy_mode="model"
    prior:     retrain=True,  policy_mode="prior"

Memory discipline (precedent: artifacts/run_sweep_25_driver.py, scripts/run_seed_sweep.py):
two evaluations sharing a process have exhausted memory before, so every (seed, severity,
eps, arm) run gets its OWN subprocess, never batched. A run's key is the 4-tuple
``(seed, selection_severity, exploration_rate, arm)``.

Shard-per-run output: each run writes its 12 generation rows to
``artifacts/feedback_sweep_parts/<key>.csv`` -- no concurrent appends to a shared file, so
``--workers N`` (default 4) is safe: each worker thread blocks on its own subprocess and
then writes only its own shard file. Resume = skip any key whose shard file already exists.

Shard filename encoding (implementation choice -- the spec pins the key TUPLE, not a
literal string format): ``seed{seed}_sev{severity}_eps{eps}_{arm}.csv`` with '.' replaced
by 'p' in the two float fields, e.g. seed=1000, severity=0.2, eps=0.05, arm="frozen" ->
``seed1000_sev0p2_eps0p05_frozen.csv``. Deterministic, ASCII, filesystem-safe, used
identically for writing shards and for the resume/done check.

The final artifact ``artifacts/feedback_profit_sweep.csv`` is built by concatenating ALL
450 shards in deterministic key order (the matrix enumeration order: seed, then severity,
then exploration_rate, then arm, matching the nested-loop order in section 4) -- it is only
written once every one of the 450 shards exists on disk; a partial run (including --quick,
whose 6 keys are a subset of the 450) never touches it. Never appends to, and never
confused with, the existing committed ``artifacts/feedback_generations.csv`` (a different,
6-generation x 3-seed artifact from v2/run_feedback.py) -- that file is untouched by this
script.

ASCII-only output (Windows console, cp1252).
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import threading
from pathlib import Path

import pandas as pd

from cldd import config

# --------------------------------------------------------------------------- #
# Matrix definition (spec section 4, decision records 7-8)

SEEDS = [1000 + 16 * i for i in range(25)]  # 1000, 1016, ..., 1384
SEVERITIES = [0.2, 0.4, 1.0]
EPS_GRID = [0.0, 0.05]
ARMS = ["treatment", "frozen", "prior"]
N_GENERATIONS = 12
GENERATOR = "scm"

ARM_KWARGS = {
    "treatment": {"retrain": True, "policy_mode": "model"},
    "frozen": {"retrain": False, "policy_mode": "model"},
    "prior": {"retrain": True, "policy_mode": "prior"},
}

# Sweep CSV column order -- verbatim, spec section 4.
FIELDS = [
    "seed", "selection_severity", "exploration_rate", "arm", "generation", "policy",
    "funded_rate", "funded_default_rate", "book_profit", "explored_profit",
    "declined_ece", "declined_mean_pd", "declined_base_rate", "all_ece",
    "declined_empc", "declined_emp_h",
    "diag_propensity_auc", "diag_ess_ratio", "diag_below_floor", "diag_flagged",
    "n_explored", "explored_defaults",
]

# round(4) convention (matches run_feedback.py) -- everything float-valued except the
# echoed sweep-key fields (seed/selection_severity/exploration_rate/arm/generation/policy)
# and the bool/int passthrough fields (diag_flagged, n_explored, explored_defaults).
ROUND_FIELDS = [
    "funded_rate", "funded_default_rate", "book_profit", "explored_profit",
    "declined_ece", "declined_mean_pd", "declined_base_rate", "all_ece",
    "declined_empc", "declined_emp_h",
    "diag_propensity_auc", "diag_ess_ratio", "diag_below_floor",
]

ROOT = Path(__file__).resolve().parents[1]
PARTS_DIR = config.ARTIFACTS_DIR / "feedback_sweep_parts"
FINAL_OUT = config.ARTIFACTS_DIR / "feedback_profit_sweep.csv"

_CHILD = """\
import json
from cldd import FeedbackLoop

res = FeedbackLoop(
    selection_severity={severity!r},
    n_generations={n_generations!r},
    exploration_rate={eps!r},
    generator={generator!r},
    seed={seed!r},
    retrain={retrain!r},
    policy_mode={policy_mode!r},
).run()

rows = []
for g in res.generations:
    m, d = g.metrics, g.diagnostics
    rows.append({{
        "seed": {seed!r},
        "selection_severity": {severity!r},
        "exploration_rate": {eps!r},
        "arm": {arm!r},
        "generation": g.generation,
        "policy": g.policy,
        "funded_rate": g.funded_rate,
        "funded_default_rate": g.funded_default_rate,
        "book_profit": g.book_profit,
        "explored_profit": g.explored_profit,
        "declined_ece": m.declined_ece,
        "declined_mean_pd": m.declined_mean_pd,
        "declined_base_rate": m.declined_base_rate,
        "all_ece": m.all_ece,
        "declined_empc": m.declined_empc,
        "declined_emp_h": m.declined_emp_h,
        "diag_propensity_auc": d.propensity_auc,
        "diag_ess_ratio": d.ess_ratio,
        "diag_below_floor": d.unfunded_below_floor,
        "diag_flagged": d.flagged,
        "n_explored": g.n_explored,
        "explored_defaults": g.explored_defaults,
    }})
print(json.dumps(rows))
"""


# --------------------------------------------------------------------------- #
# Key / matrix helpers


def _fmt(x: float) -> str:
    """ASCII, filesystem-safe encoding of a float for shard filenames."""
    return str(x).replace(".", "p").replace("-", "neg")


def format_key(seed: int, severity: float, eps: float, arm: str) -> str:
    return f"seed{seed}_sev{_fmt(severity)}_eps{_fmt(eps)}_{arm}"


def enumerate_matrix() -> list[tuple[int, float, float, str]]:
    """Full 450-run matrix in deterministic (seed, severity, eps, arm) order."""
    keys = []
    for seed in SEEDS:
        for severity in SEVERITIES:
            for eps in EPS_GRID:
                for arm in ARMS:
                    keys.append((seed, severity, eps, arm))
    return keys


def enumerate_pilot() -> list[tuple[int, float, float, str]]:
    """--quick slice: seed 1000 x severity 0.4 x all six (arm, eps) cells."""
    keys = []
    for eps in EPS_GRID:
        for arm in ARMS:
            keys.append((1000, 0.4, eps, arm))
    return keys


def shard_path(key: tuple[int, float, float, str]) -> Path:
    seed, severity, eps, arm = key
    return PARTS_DIR / f"{format_key(seed, severity, eps, arm)}.csv"


# --------------------------------------------------------------------------- #
# Run + write


def run_one(key: tuple[int, float, float, str]) -> list[dict]:
    seed, severity, eps, arm = key
    kwargs = ARM_KWARGS[arm]
    child = _CHILD.format(
        seed=seed,
        severity=severity,
        eps=eps,
        arm=arm,
        n_generations=N_GENERATIONS,
        generator=GENERATOR,
        retrain=kwargs["retrain"],
        policy_mode=kwargs["policy_mode"],
    )
    out = subprocess.run(
        [sys.executable, "-c", child],
        capture_output=True, text=True, check=True,
    )
    rows = json.loads(out.stdout.strip().splitlines()[-1])
    for row in rows:
        for f in ROUND_FIELDS:
            if row.get(f) is not None:
                row[f] = round(row[f], 4)
    return rows


def write_shard(key: tuple[int, float, float, str], rows: list[dict]) -> None:
    PARTS_DIR.mkdir(parents=True, exist_ok=True)
    path = shard_path(key)
    df = pd.DataFrame(rows)[FIELDS]
    df.to_csv(path, index=False)


_print_lock = threading.Lock()


def _log(msg: str) -> None:
    with _print_lock:
        print(msg, flush=True)


def run_and_write(key: tuple[int, float, float, str]) -> None:
    seed, severity, eps, arm = key
    _log(f"running seed={seed} severity={severity} eps={eps} arm={arm} ...")
    rows = run_one(key)
    write_shard(key, rows)
    _log(f"  wrote {shard_path(key).name} ({len(rows)} rows)")


# --------------------------------------------------------------------------- #
# Concatenation


def missing_shards(keys: list[tuple[int, float, float, str]]) -> list[tuple[int, float, float, str]]:
    return [k for k in keys if not shard_path(k).exists()]


def concat_shards(keys: list[tuple[int, float, float, str]], out_path: Path) -> pd.DataFrame:
    """Concatenate shards for ``keys`` (already verified present) in that order."""
    frames = [pd.read_csv(shard_path(k)) for k in keys]
    df = pd.concat(frames, ignore_index=True)[FIELDS]
    config.ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
    df.to_csv(out_path, index=False)
    return df


def maybe_build_final(matrix: list[tuple[int, float, float, str]]) -> None:
    """Build artifacts/feedback_profit_sweep.csv iff ALL 450 full-matrix shards exist.

    Never triggered by --quick alone (its 6 keys are a strict subset of the 450).
    """
    missing = missing_shards(matrix)
    if missing:
        _log(
            f"{len(matrix) - len(missing)}/{len(matrix)} full-matrix shards present; "
            f"skipping {FINAL_OUT.name} (need all {len(matrix)})"
        )
        return
    df = concat_shards(matrix, FINAL_OUT)
    _log(f"wrote {FINAL_OUT}  ({len(df)} rows, {len(matrix)} runs)")


# --------------------------------------------------------------------------- #


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--quick", action="store_true",
                     help="pilot slice only: seed 1000 x severity 0.4 x all six "
                          "(arm, eps) cells = 6 runs")
    ap.add_argument("--workers", type=int, default=4,
                     help="parallel subprocess workers (default 4); each run is still "
                          "its own subprocess, shards make this concurrency-safe")
    ap.add_argument("--list-keys", action="store_true",
                     help="print the run keys for the selected matrix and exit; "
                          "launches no runs")
    ap.add_argument("--concat-only", action="store_true",
                     help="attempt to build feedback_profit_sweep.csv from whatever "
                          "shards already exist on disk (full matrix only); launches "
                          "no runs")
    args = ap.parse_args()

    full_matrix = enumerate_matrix()
    keys = enumerate_pilot() if args.quick else full_matrix

    if args.list_keys:
        for k in keys:
            seed, severity, eps, arm = k
            print(format_key(seed, severity, eps, arm))
        print(f"TOTAL {len(keys)} keys ({'pilot' if args.quick else 'full matrix'})")
        return

    if args.concat_only:
        maybe_build_final(full_matrix)
        return

    todo = [k for k in keys if not shard_path(k).exists()]
    skipped = len(keys) - len(todo)
    if skipped:
        _log(f"skipping {skipped}/{len(keys)} keys (shard already present)")
    if not todo:
        _log("nothing to run -- all requested shards already present")
    else:
        _log(f"running {len(todo)} keys with {args.workers} worker(s) ...")
        if args.workers <= 1:
            for k in todo:
                run_and_write(k)
        else:
            from concurrent.futures import ThreadPoolExecutor, as_completed

            with ThreadPoolExecutor(max_workers=args.workers) as ex:
                futs = {ex.submit(run_and_write, k): k for k in todo}
                for fut in as_completed(futs):
                    fut.result()  # re-raise any subprocess failure

    if not args.quick:
        maybe_build_final(full_matrix)
    else:
        present = len(full_matrix) - len(missing_shards(full_matrix))
        _log(
            f"pilot run complete; {present}/{len(full_matrix)} full-matrix shards "
            f"present overall (feedback_profit_sweep.csv not written by --quick)"
        )


if __name__ == "__main__":
    main()
