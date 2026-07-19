"""Analysis for the CLDD v3 FeedbackLoop profit-decomposition sweep.

    python scripts/feedback_sweep_stats.py            # full 450-run matrix
    python scripts/feedback_sweep_stats.py --pilot     # 6-run pilot gate only

Recomputes every published v3 number from a committed CSV (repo discipline: no
number is ever quoted from memory). Two modes:

* **Full mode** (default): reads ``artifacts/feedback_profit_sweep.csv`` (the
  450-run x 12-generation sweep written by ``scripts/run_feedback_sweep.py``)
  and computes the spec section 3 statistics for H1, H2, H3, H3a; the H4
  integrity identity; and the T_ece alarm-immediacy distribution (the 25-seed
  re-verification of decision record 6). Writes
  ``artifacts/feedback_sweep_stats.csv`` and prints an ASCII summary.
* **Pilot mode** (``--pilot``): reads every shard CSV under
  ``artifacts/feedback_sweep_parts/`` (whatever filename convention
  ``run_feedback_sweep.py`` chose -- this script only assumes the per-row
  column schema is the sweep CSV's schema, not any particular filename) and
  asserts ONLY the H4 identity, at severity 0.4, to float tolerance. This is
  the spec section 4 "fail mechanically in minutes" gate that must pass before
  the full 450-run matrix is allowed to launch -- it does not attempt H1/H2/H3
  (those need the full 25-seed matrix; a 1-seed sign test / Wilcoxon is
  statistically meaningless). Exits non-zero on failure, per spec section 5.

Statistics implemented (spec section 3): per seed, the mean over generations
1..11 of the per-generation paired difference in ``book_profit`` (or, for H3a,
``book_profit - explored_profit``, the policy-book-only slice). Exact sign test
(``scipy.stats.binomtest``) and Wilcoxon signed-rank (``scipy.stats.wilcoxon``),
both one-sided in the hypothesis's stated direction. Holm correction is applied
across the H1-H3 family (m=3), separately within the sign-test p-values and the
Wilcoxon p-values, and ONLY at the confirmatory severity (0.4) -- both corrected
p-values must clear alpha=0.05 for a hypothesis to be reported "confirmed", and
even then only if it also clears the pre-registered effect floor. Severities
0.2 and 1.0 get the identical statistics computed and published as replication
panels (labeled secondary, no Holm correction, no "confirmed" verdict) -- see
decision record 9. H3a is always secondary and outside the Holm family.

The effect floor (spec section 3): for each severity, pool the absolute
generation-to-generation ``book_profit`` differences within every prior-arm,
eps-0 run (11 successive diffs per seed x 25 seeds); the floor is the median of
that pool.

The H4 identity (spec section 3, an integrity control, not a discovery claim):
because the frozen arm's deployed model and policy funding are eps-invariant
by construction (spec section 1.2), for every (seed, generation) the paired
difference frozen(eps=0.05).book_profit - frozen(eps=0).book_profit must equal
explored_profit(frozen, eps=0.05) - explored_profit(frozen, eps=0) (the eps=0
side never explores, so its explored_profit is always 0.0) to float tolerance.
A failed identity blocks publication of H1-H3 until explained (spec section
10.5).

Registered-defect note (carried verbatim per spec section 5, printed in every
run's summary and written into the stats CSV): the 0.10 TARGET_DECLINED_ECE
threshold is the loop's operative alarm but an arbitrary constant, and
10-equal-width-bin ECE is a noisy control statistic (assessment defect 5). v3
uses the alarm because it is what the harness *does*; it does not defend the
constant.

Deterministic: no RNG anywhere in this script -- it only reads a committed CSV
and runs closed-form/exact statistics (scipy binomtest / wilcoxon are exact and
deterministic given the input sample). ASCII-only stdout for the Windows cp1252
console.

Output CSV schema (``artifacts/feedback_sweep_stats.csv``): one row per
(metric, hypothesis-or-label, severity[, exploration_rate]) combination, in a
single flat table so every published number lives in one place. ``metric`` is
one of ``"hypothesis"`` (H1/H2/H3/H3a rows), ``"h4_identity"`` (one row per
severity), or ``"t_ece_distribution"`` (one row per severity x exploration_rate
cell, with the generation->count histogram JSON-encoded in ``detail_json``
since it doesn't fit a fixed column). Descriptive statistics (means, medians,
the floor) are rounded to 4dp per ``run_feedback.py``'s convention; p-values
and the H4 identity's max absolute error are left at full float precision
since rounding them to 4dp would silently zero out small values that matter
for the verdict.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from scipy import stats  # noqa: E402

from cldd import config  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[1]
SWEEP_CSV = REPO_ROOT / "artifacts" / "feedback_profit_sweep.csv"
SHARD_DIR = REPO_ROOT / "artifacts" / "feedback_sweep_parts"
OUT_CSV = REPO_ROOT / "artifacts" / "feedback_sweep_stats.csv"

GENERATIONS_FOR_STATS = tuple(range(1, 12))  # generations 1..11 inclusive
ALPHA = 0.05
CONFIRMATORY_SEVERITY = 0.4
H4_TOL = 1e-6

REGISTERED_DEFECT_NOTE = (
    "registered defect (assessment defect 5): the 0.10 TARGET_DECLINED_ECE "
    "threshold is the loop's operative alarm but an arbitrary constant, and "
    "10-equal-width-bin ECE is a noisy control statistic. v3 uses the alarm "
    "because it is what the harness does; it does not defend the constant."
)

# name -> (arm_a, eps_a, arm_b, eps_b, direction, value_col, role)
HYPOTHESES = {
    "H1": ("treatment", 0.0, "frozen", 0.0, "negative", "book_profit", "confirmatory"),
    "H2": ("frozen", 0.0, "prior", 0.0, "negative", "book_profit", "confirmatory"),
    "H3": ("treatment", 0.05, "treatment", 0.0, "positive", "book_profit", "confirmatory"),
    "H3a": ("treatment", 0.05, "treatment", 0.0, "positive", "policy_book_profit", "secondary"),
}

STATS_FIELDS = [
    "metric", "hypothesis", "severity", "exploration_rate", "role", "direction",
    "n_seeds", "mean_per_seed_stat", "median_per_seed_stat", "floor", "clears_floor",
    "sign_k", "sign_n", "sign_p_raw", "sign_p_holm",
    "wilcoxon_stat", "wilcoxon_p_raw", "wilcoxon_p_holm",
    "confirmed",
    "identity_n_checked", "identity_max_abs_error", "identity_passed",
    "detail_json",
]


# --------------------------------------------------------------------------- #
# Loading
# --------------------------------------------------------------------------- #

def _prepare(df: pd.DataFrame) -> pd.DataFrame:
    """Normalize dtypes and add the H3a derived column."""
    df = df.copy()
    df["selection_severity"] = df["selection_severity"].astype(float).round(4)
    df["exploration_rate"] = df["exploration_rate"].astype(float).round(4)
    df["seed"] = df["seed"].astype(int)
    df["generation"] = df["generation"].astype(int)
    df["book_profit"] = df["book_profit"].astype(float)
    df["explored_profit"] = df["explored_profit"].astype(float)
    # H3a: the policy-funded book's own P&L, stripping the explored slice out.
    df["policy_book_profit"] = df["book_profit"] - df["explored_profit"]
    return df


def load_full_csv(path: Path = SWEEP_CSV) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(
            f"{path} does not exist -- run scripts/run_feedback_sweep.py first"
        )
    return _prepare(pd.read_csv(path))


def load_pilot_shards(shard_dir: Path | None = None) -> pd.DataFrame:
    # Resolved at call time (not bound as a default argument) so tests can
    # monkeypatch the module-level SHARD_DIR and have it take effect.
    shard_dir = SHARD_DIR if shard_dir is None else shard_dir
    paths = sorted(shard_dir.glob("*.csv")) if shard_dir.exists() else []
    if not paths:
        raise FileNotFoundError(
            f"no shard CSVs found under {shard_dir} -- run "
            "scripts/run_feedback_sweep.py --quick first"
        )
    frames = [pd.read_csv(p) for p in paths]
    return _prepare(pd.concat(frames, ignore_index=True))


# --------------------------------------------------------------------------- #
# Core statistics
# --------------------------------------------------------------------------- #

def _series(df: pd.DataFrame, arm: str, eps: float, severity: float, value_col: str) -> pd.Series:
    """(seed, generation) -indexed slice of ``value_col`` for one arm/eps/severity cell."""
    sub = df[
        (df["arm"] == arm)
        & np.isclose(df["exploration_rate"], eps, atol=1e-9)
        & np.isclose(df["selection_severity"], severity, atol=1e-9)
    ]
    dup = sub.duplicated(subset=["seed", "generation"])
    if dup.any():
        raise ValueError(
            f"duplicate (seed, generation) rows for arm={arm!r} eps={eps} "
            f"severity={severity}: {sub.loc[dup, ['seed', 'generation']].to_dict('records')}"
        )
    return sub.set_index(["seed", "generation"])[value_col]


def per_seed_paired_diffs(
    df: pd.DataFrame,
    arm_a: str, eps_a: float,
    arm_b: str, eps_b: float,
    severity: float,
    value_col: str,
    generations=GENERATIONS_FOR_STATS,
) -> dict[int, float]:
    """{seed: mean over ``generations`` of (A - B) at matched generation}.

    Per spec section 3: "the mean over generations 1..11 of the per-generation
    paired difference". A seed contributes only if at least one generation is
    present in both slices.
    """
    series_a = _series(df, arm_a, eps_a, severity, value_col)
    series_b = _series(df, arm_b, eps_b, severity, value_col)
    seeds_a = {seed for seed, _gen in series_a.index}
    seeds_b = {seed for seed, _gen in series_b.index}
    result: dict[int, float] = {}
    for seed in sorted(seeds_a & seeds_b):
        diffs = []
        for gen in generations:
            key = (seed, gen)
            if key in series_a.index and key in series_b.index:
                diffs.append(float(series_a.loc[key]) - float(series_b.loc[key]))
        if diffs:
            result[seed] = float(np.mean(diffs))
    return result


def sign_test(diffs, direction: str) -> dict:
    """Exact one-sided sign test in the stated direction. Ties (exact 0) excluded."""
    vals = np.asarray(list(diffs), dtype=float)
    n_pos = int(np.sum(vals > 0))
    n_neg = int(np.sum(vals < 0))
    n = n_pos + n_neg
    k = n_pos if direction == "positive" else n_neg
    if n == 0:
        return {"k": 0, "n": 0, "p": float("nan")}
    result = stats.binomtest(k, n, 0.5, alternative="greater")
    return {"k": k, "n": n, "p": float(result.pvalue)}


def wilcoxon_test(diffs, direction: str) -> dict:
    """One-sided Wilcoxon signed-rank test against a zero-difference null."""
    vals = np.asarray(list(diffs), dtype=float)
    alt = "greater" if direction == "positive" else "less"
    if len(vals) == 0 or np.all(vals == 0.0):
        # scipy either raises ("zero_method does not handle zero differences")
        # or (newer versions) divides 0/0 with a RuntimeWarning and returns a
        # degenerate p=1.0 -- neither is a real answer, so short-circuit
        # before calling it: an all-zero paired sample is undecidable, not a
        # crash and not evidence of anything.
        return {"stat": float("nan"), "p": float("nan")}
    try:
        result = stats.wilcoxon(vals, alternative=alt)
    except ValueError:
        return {"stat": float("nan"), "p": float("nan")}
    return {"stat": float(result.statistic), "p": float(result.pvalue)}


def holm_adjust(pvalues) -> list[float]:
    """Holm step-down adjusted p-values, same order as the input.

    Standard Holm-Bonferroni: sort ascending, adjusted_(i) = max_{j<=i}
    [(m - j + 1) * p_(j)], enforced monotonic non-decreasing, clipped to 1.0.
    Matches R's ``p.adjust(method="holm")``.
    """
    pvals = np.asarray(list(pvalues), dtype=float)
    m = len(pvals)
    if m == 0:
        return []
    order = np.argsort(pvals, kind="stable")
    adjusted_sorted = np.empty(m)
    running_max = 0.0
    for rank, idx in enumerate(order):
        factor = m - rank
        val = min(1.0, float(pvals[idx]) * factor)
        running_max = max(running_max, val)
        adjusted_sorted[rank] = running_max
    adjusted = np.empty(m)
    adjusted[order] = adjusted_sorted
    return adjusted.tolist()


def effect_floor(
    df: pd.DataFrame, severity: float,
    arm: str = "prior", eps: float = 0.0, value_col: str = "book_profit",
) -> float:
    """Median of pooled |generation-to-generation diff| within prior-arm, eps-0 runs.

    Spec section 3: "for each severity, pool the absolute generation-to-generation
    book_profit differences within every prior-arm eps-0 run (11 successive diffs
    x 25 seeds); the floor is the median of that pool" -- uses the FULL 12-generation
    series (0..11), not the 1..11 statistic window.
    """
    sub = df[
        (df["arm"] == arm)
        & np.isclose(df["exploration_rate"], eps, atol=1e-9)
        & np.isclose(df["selection_severity"], severity, atol=1e-9)
    ]
    pooled: list[float] = []
    for _seed, g in sub.groupby("seed"):
        g = g.sort_values("generation")
        vals = g[value_col].to_numpy(dtype=float)
        if len(vals) >= 2:
            pooled.extend(np.abs(np.diff(vals)).tolist())
    if not pooled:
        return float("nan")
    return float(np.median(pooled))


def h4_identity_check(
    df: pd.DataFrame, severity: float,
    arm: str = "frozen", eps_hi: float = 0.05, eps_lo: float = 0.0,
    tol: float = H4_TOL,
) -> dict:
    """Per-generation identity: frozen(eps_hi).book_profit - frozen(eps_lo).book_profit
    == explored_profit(frozen, eps_hi) - explored_profit(frozen, eps_lo), to ``tol``.

    Spec section 3 (H4): "because the frozen arm's deployed model and policy
    funding are eps-invariant by section 1.2, the paired difference must equal
    the explored slice's own explored_profit, summed, to float tolerance."
    Checked per (seed, generation) here -- an accounting identity, not a
    statistical test -- across every generation present, not just 1..11.
    """
    book_hi = _series(df, arm, eps_hi, severity, "book_profit")
    book_lo = _series(df, arm, eps_lo, severity, "book_profit")
    exp_hi = _series(df, arm, eps_hi, severity, "explored_profit")
    exp_lo = _series(df, arm, eps_lo, severity, "explored_profit")
    keys = sorted(set(book_hi.index) & set(book_lo.index) & set(exp_hi.index) & set(exp_lo.index))
    errors = []
    for key in keys:
        lhs = float(book_hi.loc[key]) - float(book_lo.loc[key])
        rhs = float(exp_hi.loc[key]) - float(exp_lo.loc[key])
        errors.append(abs(lhs - rhs))
    if not errors:
        return {"n_checked": 0, "max_abs_error": float("nan"), "passed": False}
    max_err = max(errors)
    return {"n_checked": len(errors), "max_abs_error": max_err, "passed": bool(max_err <= tol)}


def t_ece_distribution(df: pd.DataFrame, target: float | None = None) -> dict:
    """{(seed, severity, eps): first generation with declined_ece > target, or None}.

    "per treatment run" (spec section 5) -- only ``arm == "treatment"`` model
    generations (generation 0 is prior-policy setup in every arm and has no
    ``policy == "model"`` row) are considered.
    """
    target = config.TARGET_DECLINED_ECE if target is None else target
    sub = df[(df["arm"] == "treatment") & (df["policy"] == "model")]
    out: dict[tuple[int, float, float], int | None] = {}
    for (seed, sev, eps), g in sub.groupby(["seed", "selection_severity", "exploration_rate"]):
        g = g.sort_values("generation")
        alarmed = g[g["declined_ece"] > target]
        out[(int(seed), float(sev), float(eps))] = (
            int(alarmed["generation"].min()) if len(alarmed) else None
        )
    return out


def summarize_t_ece(t_ece_map: dict) -> dict:
    """{(severity, eps): {"n_runs", "counts": {generation-or-'never': count}, "n_immediate_gen1"}}."""
    groups: dict[tuple[float, float], list] = {}
    for (_seed, sev, eps), gen in t_ece_map.items():
        groups.setdefault((sev, eps), []).append(gen)
    summary = {}
    for key, gens in groups.items():
        counts: dict[str, int] = {}
        for gval in gens:
            label = "never" if gval is None else str(gval)
            counts[label] = counts.get(label, 0) + 1
        summary[key] = {
            "n_runs": len(gens),
            "counts": counts,
            "n_immediate_gen1": counts.get("1", 0),
        }
    return summary


# --------------------------------------------------------------------------- #
# Row assembly (feeds artifacts/feedback_sweep_stats.csv)
# --------------------------------------------------------------------------- #

def _row_defaults() -> dict:
    return {k: float("nan") for k in STATS_FIELDS}


def compute_hypothesis_stats(df: pd.DataFrame, name: str, severity: float) -> dict:
    arm_a, eps_a, arm_b, eps_b, direction, value_col, role = HYPOTHESES[name]
    diffs_by_seed = per_seed_paired_diffs(df, arm_a, eps_a, arm_b, eps_b, severity, value_col)
    seeds = sorted(diffs_by_seed)
    diffs = [diffs_by_seed[s] for s in seeds]
    sign = sign_test(diffs, direction)
    wil = wilcoxon_test(diffs, direction)
    floor = effect_floor(df, severity)
    median_diff = float(np.median(diffs)) if diffs else float("nan")
    clears_floor = bool(diffs and not np.isnan(floor) and abs(median_diff) >= floor)

    row = _row_defaults()
    row.update(
        metric="hypothesis",
        hypothesis=name,
        severity=severity,
        role=role,
        direction=direction,
        n_seeds=len(diffs),
        mean_per_seed_stat=float(np.mean(diffs)) if diffs else float("nan"),
        median_per_seed_stat=median_diff,
        floor=floor,
        clears_floor=clears_floor,
        sign_k=sign["k"], sign_n=sign["n"], sign_p_raw=sign["p"],
        wilcoxon_stat=wil["stat"], wilcoxon_p_raw=wil["p"],
        confirmed=None,
        detail_json="",
    )
    return row


def build_stats_rows(df: pd.DataFrame) -> list[dict]:
    severities = sorted(df["selection_severity"].unique())
    rows: list[dict] = []

    for name in ("H1", "H2", "H3", "H3a"):
        for sev in severities:
            rows.append(compute_hypothesis_stats(df, name, sev))

    # Holm correction: H1-H3 only, confirmatory severity only, sign and
    # Wilcoxon families adjusted separately (spec section 3: "both tests must
    # clear it").
    conf_rows = [
        r for r in rows
        if r["hypothesis"] in ("H1", "H2", "H3") and r["severity"] == CONFIRMATORY_SEVERITY
    ]
    if len(conf_rows) == 3:
        sign_holm = holm_adjust([r["sign_p_raw"] for r in conf_rows])
        wil_holm = holm_adjust([r["wilcoxon_p_raw"] for r in conf_rows])
        for r, sp, wp in zip(conf_rows, sign_holm, wil_holm):
            r["sign_p_holm"] = sp
            r["wilcoxon_p_holm"] = wp
            r["confirmed"] = bool(sp <= ALPHA and wp <= ALPHA and r["clears_floor"])

    # H4 identity, one row per severity.
    for sev in severities:
        h4 = h4_identity_check(df, sev)
        row = _row_defaults()
        row.update(
            metric="h4_identity", hypothesis="H4", severity=sev,
            role="integrity_control", direction="n/a",
            identity_n_checked=h4["n_checked"],
            identity_max_abs_error=h4["max_abs_error"],
            identity_passed=h4["passed"],
            detail_json="",
        )
        rows.append(row)

    # T_ece distribution, one row per (severity, exploration_rate).
    t_ece_map = t_ece_distribution(df)
    summary = summarize_t_ece(t_ece_map)
    for (sev, eps), s in sorted(summary.items()):
        row = _row_defaults()
        row.update(
            metric="t_ece_distribution", hypothesis="T_ece", severity=sev,
            exploration_rate=eps, role="descriptive", direction="n/a",
            n_seeds=s["n_runs"],
            sign_k=s["n_immediate_gen1"], sign_n=s["n_runs"],
            detail_json=json.dumps(s["counts"], sort_keys=True),
        )
        rows.append(row)

    return rows


_ROUND4_FIELDS = ("mean_per_seed_stat", "median_per_seed_stat", "floor")


def write_stats_csv(rows: list[dict], out: Path = OUT_CSV) -> pd.DataFrame:
    frame = pd.DataFrame(rows, columns=STATS_FIELDS)
    for col in _ROUND4_FIELDS:
        frame[col] = frame[col].apply(lambda v: v if pd.isna(v) else round(float(v), 4))
    out.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(out, index=False)
    return frame


# --------------------------------------------------------------------------- #
# ASCII summary
# --------------------------------------------------------------------------- #

def print_ascii_summary(rows: list[dict], out: Path = OUT_CSV) -> None:
    by_metric: dict[str, list[dict]] = {}
    for r in rows:
        by_metric.setdefault(r["metric"], []).append(r)

    print("CLDD v3 feedback-loop profit-decomposition sweep -- stats summary")
    print("output: " + str(out))
    print("")

    print("H1-H3 (confirmatory, severity %.1f, Holm alpha=%.2f):" % (CONFIRMATORY_SEVERITY, ALPHA))
    for r in by_metric.get("hypothesis", []):
        if r["hypothesis"] in ("H1", "H2", "H3") and r["severity"] == CONFIRMATORY_SEVERITY:
            verdict = "CONFIRMED" if r["confirmed"] else "not confirmed"
            print(
                "  %s: median=%+.4f (n=%d seeds) sign %d/%d p_raw=%.3e p_holm=%.3e; "
                "wilcoxon p_raw=%.3e p_holm=%.3e; floor=%.4f clears_floor=%s -> %s"
                % (
                    r["hypothesis"], r["median_per_seed_stat"], r["n_seeds"],
                    r["sign_k"], r["sign_n"], r["sign_p_raw"], r["sign_p_holm"],
                    r["wilcoxon_p_raw"], r["wilcoxon_p_holm"],
                    r["floor"], r["clears_floor"], verdict,
                )
            )
    print("")

    print("H3a (secondary, policy-book-only, all severities):")
    for r in by_metric.get("hypothesis", []):
        if r["hypothesis"] == "H3a":
            print(
                "  severity %.1f: median=%+.4f (n=%d) sign %d/%d p_raw=%.3e; wilcoxon p_raw=%.3e"
                % (r["severity"], r["median_per_seed_stat"], r["n_seeds"],
                   r["sign_k"], r["sign_n"], r["sign_p_raw"], r["wilcoxon_p_raw"])
            )
    print("")

    print("Replication panels (H1-H3, severities 0.2 and 1.0, secondary, no Holm):")
    for r in by_metric.get("hypothesis", []):
        if r["hypothesis"] in ("H1", "H2", "H3") and r["severity"] != CONFIRMATORY_SEVERITY:
            print(
                "  %s severity %.1f: median=%+.4f (n=%d) sign %d/%d p_raw=%.3e; "
                "wilcoxon p_raw=%.3e; floor=%.4f clears_floor=%s"
                % (r["hypothesis"], r["severity"], r["median_per_seed_stat"], r["n_seeds"],
                   r["sign_k"], r["sign_n"], r["sign_p_raw"], r["wilcoxon_p_raw"],
                   r["floor"], r["clears_floor"])
            )
    print("")

    print("H4 integrity identity (frozen arm, eps 0.05 minus eps 0, must equal Sum explored_profit):")
    for r in by_metric.get("h4_identity", []):
        status = "PASS" if r["identity_passed"] else "FAIL"
        print(
            "  severity %.1f: n_checked=%d max_abs_error=%.10f -> %s"
            % (r["severity"], r["identity_n_checked"], r["identity_max_abs_error"], status)
        )
    print("")

    print("T_ece distribution (first treatment-arm generation with declined_ece > %.2f):"
          % config.TARGET_DECLINED_ECE)
    for r in by_metric.get("t_ece_distribution", []):
        counts = json.loads(r["detail_json"]) if r["detail_json"] else {}
        print(
            "  severity %.1f eps %.2f: n=%d, immediate(gen1)=%d/%d, full counts=%s"
            % (r["severity"], r["exploration_rate"], r["n_seeds"],
               r["sign_k"], r["sign_n"], counts)
        )
    print("")

    print(REGISTERED_DEFECT_NOTE)


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #

def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--pilot", action="store_true",
        help=(
            "pilot gate: load shards under artifacts/feedback_sweep_parts/ and "
            "assert ONLY the H4 identity at severity 0.4 (1 seed is not enough "
            "for H1-H3); exits non-zero on failure"
        ),
    )
    ap.add_argument(
        "--severity", type=float, default=CONFIRMATORY_SEVERITY,
        help="severity to check the H4 identity against in --pilot mode (default 0.4)",
    )
    args = ap.parse_args(argv)

    if args.pilot:
        df = load_pilot_shards()
        result = h4_identity_check(df, args.severity)
        print(
            "PILOT GATE -- H4 identity check (frozen arm, eps 0.05 minus eps 0, severity %.1f)"
            % args.severity
        )
        print("  rows checked: %d" % result["n_checked"])
        print("  max abs error: %.10f" % result["max_abs_error"])
        if result["passed"]:
            print("  PASS -- identity holds to float tolerance; full 450-run matrix may launch")
            print(REGISTERED_DEFECT_NOTE)
            return 0
        print("  FAIL -- H4 identity broken; DO NOT launch the full 450-run matrix")
        return 1

    df = load_full_csv()
    rows = build_stats_rows(df)
    write_stats_csv(rows)
    print_ascii_summary(rows)
    h4_rows = [r for r in rows if r["metric"] == "h4_identity"]
    if not all(r["identity_passed"] for r in h4_rows):
        print("")
        print("H4 FAILED on the full sweep -- H1-H3 publication is BLOCKED (spec section 10.5)")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
