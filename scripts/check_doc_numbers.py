"""Doc-number gate: every empirical figure quoted in the LIVING docs must
recompute from a committed artifact (assessment III.3, "mechanize the
doc-number gate").

The repo rule "numbers come from committed artifacts" has fired twice as a
manual discipline (assessment II.5); this script turns it into a gate. For each
registered claim it recomputes the value(s) from the raw committed CSV, formats
them at exactly the precision the doc quotes, and asserts the resulting literal
appears in the doc. Both failure modes fail the gate:

* the doc quotes a number the artifact no longer supports (drift in either);
* the doc was rewritten so the registered literal is gone (the claim registry
  itself has drifted -- unevaluable, and unevaluable is a FAILURE, not a pass).

Scope: README.md plus registered figures in docs/validation.md (living docs). ``docs/assessment.md``, the handoff briefs
and specs are **dated provenance snapshots** ("dated docs stay dated") -- their
figures are frozen records of their own review moments and must never be
"fixed", so gating them against artifacts would be wrong the first time an
artifact is legitimately superseded. CHANGELOG entries are dated release notes,
same exclusion. If a figure is added to another living doc, register it here.

Comparison discipline: literals are compared after whitespace normalization
(the README hard-wraps mid-claim), and values are formatted at the DOC'S quoted
precision -- a gate stricter than what the doc actually says would only emit
false alarms. Unicode in literals (minus signs, check marks) is preserved;
stdout stays ASCII via backslash-escaping.

Usage:
    python scripts/check_doc_numbers.py        # exit 0 iff every claim passes

Wired into CI via tests/test_doc_numbers.py (runs in every pytest job; the
computations are closed-form over committed CSVs, so the gate is not
version-sensitive and carries no ``pinned`` marker).
"""
from __future__ import annotations

import csv
import importlib.util
import re
import sys
from pathlib import Path

import numpy as np
from scipy import stats

ROOT = Path(__file__).resolve().parents[1]
ARTIFACTS = ROOT / "artifacts"

# Every artifact CSV a claim reads. tests/test_doc_numbers.py asserts each is
# git-TRACKED, not merely present: artifacts/* is gitignore-default-deny, so a
# file can exist locally yet be absent on CI/clones, where the fail-closed gate
# then fails (this exact bug shipped 2026-07-29 with feedback_profit_sweep.csv
# — the repo's third unexcepted-artifact incident). Add here when a new claim
# reads a new file, and add the matching `!artifacts/...` gitignore exception.
ARTIFACTS_READ = [
    "loop_frontier.csv",
    "loop_frontier_scm.csv",
    "seed_sweep_25.csv",
    "seed_sweep_spaced.csv",
    "frontier_sweep.csv",
    "frontier_sweep_spaced.csv",
    "exploration_frontier.csv",
    "feedback_profit_sweep.csv",
    "surface_frontier.csv",
    "surface_counterfactual.csv",
]

MINUS = "−"   # the README's minus sign
CHECK = "✓"
CROSS = "✗"

_FSS = None  # lazily imported scripts/feedback_sweep_stats.py module


def _feedback_stats_module():
    global _FSS
    if _FSS is None:
        spec = importlib.util.spec_from_file_location(
            "feedback_sweep_stats", Path(__file__).resolve().parent / "feedback_sweep_stats.py"
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        _FSS = mod
    return _FSS


# --------------------------------------------------------------------------- #
# Formatting helpers -- match the README's quoting conventions exactly
# --------------------------------------------------------------------------- #

def signed(v: float, dp: int) -> str:
    """+0.0017 / −0.0028 -- explicit sign, README's unicode minus."""
    r = round(v, dp)
    sign = MINUS if r < 0 else "+"
    return sign + ("%." + str(dp) + "f") % abs(r)


def sci_short(p: float) -> str:
    """1.4901e-07 -> '1.5e-7' (no zero-padded exponent)."""
    return ("%.1e" % p).replace("e-0", "e-")


def sci_padded(p: float) -> str:
    """2.325e-06 -> '2.3e-06' (zero-padded exponent, feedback table style)."""
    return "%.1e" % p


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", text)


# --------------------------------------------------------------------------- #
# Artifact loading (plain csv module; no artifact is ever written)
# --------------------------------------------------------------------------- #

def _rows(name: str) -> list[dict]:
    path = ARTIFACTS / name
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _by_severity(rows: list[dict], value_col: str) -> dict[float, dict]:
    """{selection_severity: row} -- fails if a severity repeats."""
    out: dict[float, dict] = {}
    for r in rows:
        sev = round(float(r["selection_severity"]), 4)
        if sev in out:
            raise ValueError(f"duplicate severity {sev} in artifact")
        out[sev] = r
    if not out:
        raise ValueError(f"no rows with {value_col}")
    return out


SEVERITY_GRID = (0.0, 0.2, 0.4, 0.6)

# Doc-verb operationalizations: the README's qualitative language is
# conditional on these re-derivations. A claim REFUSES its literals (raises,
# gate goes red) when the recomputed data no longer supports the verb --
# same pattern as claim_surface_verdicts' floor re-derivation.
ALPHA = 0.05                # "significant" / "replicates" / "the effect survives"
MAJORITY = 13               # "positive on k/25 seeds" language needs a majority of 25
NEGLIGIBLE_FRACTION = 0.5   # "negligible at full severity": |mean gap at sev 1.0|
                            # must be under this fraction of the sev-0.4 mean gap


# --------------------------------------------------------------------------- #
# Claims. Each returns a list of literals that must appear in the doc.
# A claim may additionally assert computational facts (bounds, verdicts);
# any exception = FAIL (fail-closed: unevaluable is not a pass).
# --------------------------------------------------------------------------- #

def claim_frontier_table_seed42() -> list[str]:
    """README single-seed frontier table <- loop_frontier.csv / loop_frontier_scm.csv."""
    flat = _by_severity(_rows("loop_frontier.csv"), "naive_declined_ece")
    scm = _by_severity(_rows("loop_frontier_scm.csv"), "naive_declined_ece")

    def cells(sevmap, col):
        return [float(sevmap[s][col]) for s in SEVERITY_GRID]

    def marks(sevmap):
        return [sevmap[s]["passed"] == "True" for s in SEVERITY_GRID]

    naive = cells(flat, "naive_declined_ece")
    ipw_flat = cells(flat, "reweight_declined_ece")
    ipw_scm = cells(scm, "reweight_declined_ece")
    pass_flat, pass_scm = marks(flat), marks(scm)

    def m(ok):  # bold cell with the loop's own pass/fail mark
        return CHECK if ok else CROSS

    return [
        "| Naive declined ECE (flat world) | %.3f | %.3f | %.3f | %.3f |" % tuple(naive),
        "| **IPW-corrected** (flat world) | %.3f | %.3f | **%.3f %s** | **%.3f %s** |"
        % (ipw_flat[0], ipw_flat[1], ipw_flat[2], m(pass_flat[2]), ipw_flat[3], m(pass_flat[3])),
        "| **IPW-corrected** (SCM world) | %.3f | %.3f | **%.3f %s** | **%.3f %s** |"
        % (ipw_scm[0], ipw_scm[1], ipw_scm[2], m(pass_scm[2]), ipw_scm[3], m(pass_scm[3])),
    ]


def _strong_gaps(csv_name: str, severity: float) -> list[float]:
    return [
        float(r["strong_gap"])
        for r in _rows(csv_name)
        if round(float(r["severity"]), 4) == severity
    ]


def claim_counterfactual_headline() -> list[str]:
    """README v1 headline <- seed_sweep_25.csv + seed_sweep_spaced.csv
    (Wilcoxon recomputed in-process for both designs)."""
    rows = _rows("seed_sweep_25.csv")
    g04 = _strong_gaps("seed_sweep_25.csv", 0.4)
    g10 = _strong_gaps("seed_sweep_25.csv", 1.0)
    naive04 = [float(r["naive_strong"]) for r in rows if round(float(r["severity"]), 4) == 0.4]
    assert len(g04) == 25 and len(g10) == 25, "expected 25 seeds per severity"

    naive_mean = float(np.mean(naive04))
    gap_mean = float(np.mean(g04))
    gcomp_mean = naive_mean - gap_mean
    pct = 100.0 * gap_mean / naive_mean
    n_pos = sum(1 for g in g04 if g > 0)
    p = float(stats.wilcoxon(g04, alternative="greater").pvalue)

    s04 = _strong_gaps("seed_sweep_spaced.csv", 0.4)
    assert len(s04) == 25, "expected 25 spaced seeds at severity 0.4"
    sp_pos = sum(1 for g in s04 if g > 0)
    sp_p = float(stats.wilcoxon(s04, alternative="greater").pvalue)

    g10_mean = float(np.mean(g10))
    assert gap_mean > 0 and n_pos >= MAJORITY and p < ALPHA, (
        "README 'cuts ... MAE' verb no longer supported (direction/majority/significance)")
    assert sp_pos >= MAJORITY and sp_p < ALPHA, (
        "README independent-replication phrasing no longer significant on the spaced set")
    assert abs(g10_mean) < NEGLIGIBLE_FRACTION * gap_mean, (
        "README 'collapses to a negligible' no longer holds at full severity")

    return [
        "strong-propagation counterfactual MAE from %.3f to %.3f (%s%.1f%%, "
        "positive on %d/%d seeds, Wilcoxon p = %s; on an independent spaced "
        "seed set: %d/%d, p = %s)"
        % (naive_mean, gcomp_mean, MINUS, pct, n_pos, len(g04), sci_short(p),
           sp_pos, len(s04), sci_short(sp_p)),
        "collapses to a negligible %s at full severity" % signed(g10_mean, 4),
    ]


def claim_frontier_distribution() -> list[str]:
    """README v2 frontier-distribution table <- frontier_sweep.csv."""
    rows = _rows("frontier_sweep.csv")
    literals = []
    for generator, label in (("flat", "flat"), ("scm", "SCM")):
        by_seed = {}
        for r in rows:
            if r["generator"] == generator:
                by_seed[int(r["seed"])] = r["frontier_severity"]
        values = sorted(float(v) for v in by_seed.values() if v not in ("", "None"))
        assert len(values) == 25, f"{generator}: expected 25 seeds, got {len(values)}"
        median = values[len(values) // 2]
        at_04 = sum(1 for v in values if abs(v - 0.4) < 1e-9)
        at_02 = sum(1 for v in values if abs(v - 0.2) < 1e-9)
        literals.append(
            "| %s | %.1f | **%.1f** | %.1f | %d/25 | %d/25 |"
            % (label, values[0], median, values[-1], at_04, at_02)
        )
    return literals


def claim_emp_disagreement() -> list[str]:
    """README v2 EMP table (SCM, naive, declined) <- loop_frontier_scm.csv."""
    scm = _by_severity(_rows("loop_frontier_scm.csv"), "naive_declined_empc")
    empc = [float(scm[s]["naive_declined_empc"]) for s in SEVERITY_GRID]
    emp_h = [float(scm[s]["naive_declined_emp_h"]) for s in SEVERITY_GRID]
    return [
        "| Literature `empc` (naive) | %.4f | %.4f | %.4f | **%.4f ↑** |" % tuple(empc),
        "| Harness `emp_h` (naive) | %.4f | %.4f | %.4f | **%.4f ↓** |" % tuple(emp_h),
    ]


def claim_exploration_price() -> list[str]:
    """README exploration price tag <- exploration_frontier.csv (seed 42, 10%, sev 0.6)."""
    rows = [
        r for r in _rows("exploration_frontier.csv")
        if int(r["seed"]) == 42
        and abs(float(r["exploration_rate"]) - 0.1) < 1e-9
        and abs(float(r["selection_severity"]) - 0.6) < 1e-9
    ]
    assert len(rows) == 1, f"expected exactly one (42, 0.1, 0.6) row, got {len(rows)}"
    r = rows[0]
    n = int(r["n_explored"])
    cost = float(r["exploration_cost"])
    defaults = int(r["explored_defaults"])
    per_label = round(cost / n / 100.0) * 100  # README rounds to the nearest $100
    return [
        "buys **%d labels for $%s** — about **$%s per label**, of which %d are realized defaults"
        % (n, format(round(cost), ","), format(int(per_label), ","), defaults),
    ]


def claim_feedback_hypotheses() -> list[str]:
    """README v3 hypothesis table + H4 + alarm + run count <- feedback_profit_sweep.csv,
    recomputed through scripts/feedback_sweep_stats.py (the committed stats pipeline)."""
    fss = _feedback_stats_module()
    df = fss.load_full_csv()
    rows = fss.build_stats_rows(df)

    hyp = {
        r["hypothesis"]: r
        for r in rows
        if r["metric"] == "hypothesis" and r["severity"] == 0.4
    }
    h1, h2, h3 = hyp["H1"], hyp["H2"], hyp["H3"]
    # The README's verdict column must match the recomputed verdicts.
    assert h1["confirmed"] is True, "H1 no longer confirms"
    assert h2["confirmed"] is False and h3["confirmed"] is False, "H2/H3 verdict drift"

    literals = [
        "| H1 feedback accumulation costs money (treatment %s frozen, ε=0) | **%s** | %d/%d | "
        "**confirmed** (p_holm %s, clears the %.4f noise floor) |"
        % (MINUS, signed(h1["median_per_seed_stat"], 4), h1["sign_k"], h1["sign_n"],
           sci_padded(h1["sign_p_holm"]), h1["floor"]),
        "| H2 the policy switch costs money (frozen %s prior, ε=0) | %s | %d/%d | "
        "**not confirmed — measured opposite in direction** |"
        % (MINUS, signed(h2["median_per_seed_stat"], 4), h2["sign_k"], h2["sign_n"]),
        "| H3 exploration buys profit back (treatment ε=.05 %s ε=0) | %s | %d/%d | "
        "**not confirmed** |"
        % (MINUS, signed(h3["median_per_seed_stat"], 4), h3["sign_k"], h3["sign_n"]),
    ]

    # Run count: 25 seeds x 3 severities x 2 exploration rates x 3 arms.
    n_runs = len(df.drop_duplicates(["seed", "selection_severity", "exploration_rate", "arm"]))
    literals.append("= **%d runs**" % n_runs)

    # H4 integrity identity: the README quotes the measured max error (2 sig
    # figs); the hard invariant is the spec tolerance, asserted here. (The
    # gate's first run caught the old "<=1e-10" bound being marginally false:
    # the true max error is 1.0000000567e-10.)
    h4 = [r for r in rows if r["metric"] == "h4_identity"]
    n_checked = int(sum(r["identity_n_checked"] for r in h4))
    max_err = max(float(r["identity_max_abs_error"]) for r in h4)
    assert all(r["identity_passed"] for r in h4), "H4 identity fails spec tolerance"
    literals.append(
        "holds with max |error| %s across all %d checked rows"
        % (("%.1e" % max_err), n_checked)
    )

    # Alarm immediacy: every eps=0 treatment run alarms at generation 1-2;
    # severity 0.4 alarms 25/25 at generation 1.
    t_ece = fss.summarize_t_ece(fss.t_ece_distribution(df))
    for (sev, eps), s in t_ece.items():
        if abs(eps) < 1e-9:
            late = [g for g in s["counts"] if g == "never" or int(g) > 2]
            assert not late, f"eps=0 severity {sev}: alarm not at generation 1-2 ({s['counts']})"
    cell = t_ece[(0.4, 0.0)]
    literals.append(
        "(severity 0.4: %d/%d at generation 1)" % (cell["n_immediate_gen1"], cell["n_runs"])
    )
    return literals


def claim_spaced_replication() -> list[str]:
    """README "Caveat, measured" block <- seed_sweep_spaced.csv / frontier_sweep_spaced.csv."""
    s04 = _strong_gaps("seed_sweep_spaced.csv", 0.4)
    s10 = _strong_gaps("seed_sweep_spaced.csv", 1.0)
    assert len(s04) == 25 and len(s10) == 25, "expected 25 spaced seeds per severity"
    p04 = float(stats.wilcoxon(s04, alternative="greater").pvalue)

    s04_mean = float(np.mean(s04))
    assert s04_mean > 0 and sum(1 for g in s04 if g > 0) >= MAJORITY and p04 < ALPHA, (
        "README 'the effect survives' verb no longer supported by the spaced design")
    assert abs(float(np.mean(s10))) < NEGLIGIBLE_FRACTION * s04_mean, (
        "README 'negligible in magnitude' at full severity no longer holds")

    literals = [
        "%s ± %.4f, positive on %d/25 seeds, Wilcoxon p = %s"
        % (signed(float(np.mean(s04)), 4), float(np.std(s04, ddof=1)),
           sum(1 for g in s04 if g > 0), sci_short(p04)),
        "the spaced gap is %s ± %.4f"
        % (signed(float(np.mean(s10)), 4), float(np.std(s10, ddof=1))),
    ]

    rows = _rows("frontier_sweep_spaced.csv")
    parts = {}
    for generator in ("flat", "scm"):
        by_seed = {}
        for r in rows:
            if r["generator"] == generator:
                by_seed[int(r["seed"])] = r["frontier_severity"]
        values = sorted(float(v) for v in by_seed.values() if v not in ("", "None"))
        assert len(values) == 25, f"{generator}: expected 25 spaced seeds"
        parts[generator] = (
            values[len(values) // 2],
            sum(1 for v in values if abs(v - 0.4) < 1e-9),
            sum(1 for v in values if abs(v - 0.2) < 1e-9),
        )
    literals.append(
        "flat median %.1f (%d/25 at 0.4, %d/25 at 0.2), SCM median **%.1f** "
        "(%d/25 at 0.4, %d/25 at 0.2)"
        % (parts["flat"] + parts["scm"])
    )

    # Collapse by seed first -- the same basis claim_frontier_distribution uses.
    # (The sweep CSV carries one row per loop ITERATION; a median over raw rows
    # is a different statistic and reads 0.4 where the per-seed median is 0.2.)
    orig_by_seed = {}
    for r in _rows("frontier_sweep.csv"):
        if r["generator"] == "scm":
            orig_by_seed[int(r["seed"])] = r["frontier_severity"]
    orig_vals = sorted(
        float(v) for v in orig_by_seed.values() if v not in ("", "None")
    )
    assert len(orig_vals) == 25, "expected 25 original SCM seeds"
    assert parts["scm"][0] != orig_vals[len(orig_vals) // 2], (
        "README 'does **not** replicate' verb: spaced and original SCM medians now agree")
    return literals


def claim_package_version() -> list[str]:
    """README version mentions <- pyproject.toml (regex, not tomllib: CI floor is 3.10)."""
    text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    m = re.search(r'^version = "([^"]+)"', text, re.MULTILINE)
    assert m, "no version in pyproject.toml"
    version = m.group(1)
    cff = (ROOT / "CITATION.cff").read_text(encoding="utf-8")
    m_cff = re.search(r"^version: (.+)$", cff, re.MULTILINE)
    assert m_cff and m_cff.group(1).strip() == version, (
        f"CITATION.cff version {m_cff and m_cff.group(1)!r} != pyproject {version!r}"
    )
    return [
        "# the library (PyPI, v%s)" % version,
        "`%s` **alpha** on [PyPI]" % version,
        "version = {%s}," % version,
    ]


def claim_test_count() -> list[str]:
    """README suite size <- live pytest collection (both -q output formats handled)."""
    import subprocess
    out = subprocess.run(
        [sys.executable, "-m", "pytest", "--collect-only", "-q"],
        capture_output=True, text=True, cwd=ROOT,
    ).stdout
    node_ids = [ln for ln in out.splitlines() if "::" in ln]
    if node_ids:
        n = len(node_ids)
    else:  # pytest >= 9 -q prints per-file "path: count" lines instead
        per_file = re.findall(r"^tests[/\\].*: (\d+)$", out, re.MULTILINE)
        assert per_file, f"could not parse pytest collection output:\n{out[-500:]}"
        n = sum(int(c) for c in per_file)
    return ["`pytest` — %d tests, all synthetic" % n]


def claim_surface_run_counts() -> list[str]:
    """docs/validation.md v4 gates section <- surface CSV run-group counts."""
    frontier_runs = len({
        (r["generator"], r["unobserved_strength"], r["seed"])
        for r in _rows("surface_frontier.csv")
    })
    cf_runs = len({
        (r["unobserved_strength"], r["severity"], r["seed"])
        for r in _rows("surface_counterfactual.csv")
    })
    return ["(%d loop runs + %d counterfactual evals)" % (frontier_runs, cf_runs)]


def claim_pinned_environment() -> list[str]:
    """docs/validation.md pins <- requirements-dev.txt (Rev-1.1 incident class:
    prose pins drifting from the requirements file). Registered once; the doc
    quotes it twice -- containment checking cannot count occurrences."""
    text = (ROOT / "requirements-dev.txt").read_text(encoding="utf-8")

    def pin_of(pkg: str) -> str:
        m = re.search(r"^%s==([\w.]+)$" % re.escape(pkg), text, re.MULTILINE)
        assert m, f"{pkg} not exact-pinned in requirements-dev.txt"
        return m.group(1)

    return ["**scikit-learn %s / numpy %s**" % (pin_of("scikit-learn"), pin_of("numpy"))]


def claim_suite_counts() -> list[str]:
    """docs/validation.md troubleshooting + pinned-marker sentence <- live
    collection (same recompute idiom as claim_test_count; two extra pytest
    collections per gate run, ~seconds, accepted)."""
    import subprocess

    def collect(*args) -> int:
        out = subprocess.run(
            [sys.executable, "-m", "pytest", "--collect-only", "-q", *args],
            capture_output=True, text=True, cwd=ROOT,
        ).stdout
        node_ids = [ln for ln in out.splitlines() if "::" in ln]
        if node_ids:
            return len(node_ids)
        per_file = re.findall(r"^tests[/\\].*: (\d+)$", out, re.MULTILINE)
        assert per_file, f"could not parse pytest collection output:\n{out[-500:]}"
        return sum(int(c) for c in per_file)

    total = collect()
    pinned = collect("-m", "pinned")
    words = {6: "six"}  # spelled out per doc style; extend if the set grows
    return [
        "the full suite passes (%d tests)" % total,
        "The **%s** float-sensitive tests are marked `pinned`"
        % words.get(pinned, str(pinned)),
    ]


def claim_surface_verdicts() -> list[str]:
    """README "The cause, tested" (v4) <- surface_frontier.csv / surface_counterfactual.csv.

    Recomputes the corner count, the strength-median profile, H-S1f's sign test
    (exact binomial, Holm x4), and the gap-direction medians. Also re-derives all
    four confirmatory floor checks and refuses to emit the "not confirmed" literal
    unless every one of them actually fails its floor -- the gate must not let the
    README claim a falsification the data no longer supports.
    """
    import math

    strengths = (0.0, 0.2, 0.4, 0.55, 0.7, 1.0)
    frontier: dict = {}
    for r in _rows("surface_frontier.csv"):
        key = (float(r["unobserved_strength"]), r["generator"], int(r["seed"]))
        frontier[key] = float(r["frontier_severity"])
    seeds = sorted({k[2] for k in frontier})
    assert len(seeds) == 25, "expected 25 surface seeds"

    med = {}
    for v in strengths:
        for w in ("flat", "scm"):
            vals = sorted(frontier[(v, w, s)] for s in seeds)
            assert len(vals) == 25, f"missing cells at ({v}, {w})"
            med[(v, w)] = vals[12]
    low = {med[(v, w)] for v in strengths[:5] for w in ("flat", "scm")}
    assert len(low) == 1 and med[(1.0, "flat")] == med[(1.0, "scm")], \
        "strength-median profile no longer uniform; README v4 text is stale"
    low_med, high_med = low.pop(), med[(1.0, "flat")]

    corner = sum(1 for s in seeds if frontier[(0.0, "flat", s)] == 0.4)

    d1f = [frontier[(0.0, "flat", s)] - frontier[(0.7, "flat", s)] for s in seeds]
    moved = [d for d in d1f if d != 0]
    pos = sum(1 for d in moved if d > 0)
    n = len(moved)
    p_sign = sum(math.comb(n, k) for k in range(pos, n + 1)) / 2 ** n
    holm = min(1.0, 4 * p_sign)

    gap: dict = {}
    for r in _rows("surface_counterfactual.csv"):
        key = (float(r["unobserved_strength"]), float(r["severity"]), int(r["seed"]))
        gap[key] = float(r["strong_gap"])

    def gap_med(v: float, sev: float) -> float:
        vals = sorted(gap[(v, sev, s)] for s in seeds)
        assert len(vals) == 25, f"missing cf cells at ({v}, {sev})"
        return vals[12]

    # all-four floor re-derivation (H-S1: one grid step; H-S2: strength-0 scale)
    d1s = [frontier[(0.0, "scm", s)] - frontier[(0.55, "scm", s)] for s in seeds]
    d2a = [gap[(0.55, 0.4, s)] - gap[(0.0, 0.4, s)] for s in seeds]
    delta = lambda v, s: gap[(v, 0.4, s)] - gap[(v, 1.0, s)]
    d2b = [delta(0.55, s) - delta(0.0, s) for s in seeds]
    fl2a = sorted(abs(gap[(0.0, 0.4, s)]) for s in seeds)[12]
    fl2b = sorted(abs(delta(0.0, s)) for s in seeds)[12]
    medians = [sorted(d)[12] for d in (d1f, d1s, d2a, d2b)]
    floors = [0.2, 0.2, fl2a, fl2b]
    assert all(m < f for m, f in zip(medians, floors)), \
        "a confirmatory hypothesis now clears its floor; the 'not confirmed' README claim is stale"

    return [
        "all four hypotheses were **not confirmed**",
        "At strength 0.0 the flat world's frontier sits at 0.4 on %d/25 seeds" % corner,
        "median frontier severity is **%.1f** at every strength up to 0.7 and moves to "
        "**%.1f** only at strength 1.0, in both worlds" % (low_med, high_med),
        "%d/%d of the seeds that moved did so in the predicted direction "
        "(Holm-adjusted sign-test p = %.3f)" % (pos, n, holm),
        "gap at severity 0.4 goes %s → %s → %s as strength rises"
        % tuple(signed(gap_med(v, 0.4), 4) for v in (0.0, 0.55, 1.0)),
    ]


CLAIMS = [
    ("frontier-table-seed42", "README.md", claim_frontier_table_seed42),
    ("counterfactual-headline", "README.md", claim_counterfactual_headline),
    ("frontier-distribution", "README.md", claim_frontier_distribution),
    ("emp-disagreement", "README.md", claim_emp_disagreement),
    ("exploration-price", "README.md", claim_exploration_price),
    ("feedback-hypotheses", "README.md", claim_feedback_hypotheses),
    ("spaced-replication", "README.md", claim_spaced_replication),
    ("surface-verdicts", "README.md", claim_surface_verdicts),
    ("package-version", "README.md", claim_package_version),
    ("test-count", "README.md", claim_test_count),
    ("surface-run-counts", "docs/validation.md", claim_surface_run_counts),
    ("pinned-environment", "docs/validation.md", claim_pinned_environment),
    ("suite-counts", "docs/validation.md", claim_suite_counts),
]


# --------------------------------------------------------------------------- #
# Gate
# --------------------------------------------------------------------------- #

def check_claims(doc_texts: dict[str, str] | None = None) -> list[dict]:
    """Evaluate every claim. ``doc_texts`` overrides doc content (for tests).

    Returns one result dict per claim:
    {"id", "doc", "ok": bool, "missing": [literal, ...], "error": str | None}
    """
    texts: dict[str, str] = {}
    results = []
    for claim_id, doc, fn in CLAIMS:
        if doc not in texts:
            if doc_texts is not None and doc in doc_texts:
                texts[doc] = doc_texts[doc]
            else:
                texts[doc] = (ROOT / doc).read_text(encoding="utf-8")
        norm_doc = _norm(texts[doc])
        try:
            literals = fn()
        except Exception as exc:  # fail-closed: unevaluable is a failure
            results.append({"id": claim_id, "doc": doc, "ok": False,
                            "missing": [], "error": f"{type(exc).__name__}: {exc}"})
            continue
        missing = [lit for lit in literals if _norm(lit) not in norm_doc]
        results.append({"id": claim_id, "doc": doc, "ok": not missing,
                        "missing": missing, "error": None})
    return results


def _ascii(s: str) -> str:
    return s.encode("ascii", "backslashreplace").decode("ascii")


def main() -> int:
    results = check_claims()
    n_bad = 0
    for r in results:
        if r["ok"]:
            print("PASS  %-24s (%s)" % (r["id"], r["doc"]))
            continue
        n_bad += 1
        if r["error"]:
            print("FAIL  %-24s UNEVALUABLE: %s" % (r["id"], _ascii(r["error"])))
        for lit in r["missing"]:
            print("FAIL  %-24s literal not found in %s:" % (r["id"], r["doc"]))
            print("      expected: %s" % _ascii(lit))
    print()
    if n_bad:
        print("DOC-NUMBER GATE: FAIL (%d of %d claims)" % (n_bad, len(results)))
        return 1
    print("DOC-NUMBER GATE: PASS (%d claims, all recomputed from artifacts)" % len(results))
    return 0


if __name__ == "__main__":
    sys.exit(main())
