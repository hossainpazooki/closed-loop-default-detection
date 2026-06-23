"""Fidelity gate: real-vs-synthetic marginal comparison for the SCM generator.

This is the upstream **VERIFY FIDELITY** stage. Before the closed loop trusts a
:class:`cldd.scm.StructuralBorrowerGenerator` cohort as a stand-in for the real
Intuit SMB underwriting data, we check that the synthetic marginals actually look
like the real ones. The gate compares, per quantity:

* the **labeled default base rate** (real: only prior-approved/matured loans carry
  a ``default_flag``; we drop nulls — that labeled pool ran ~17.4%),
* the **has_linked_bank_feed rate**,
* the **bank-feed missingness** (fraction of rows with a null bank-feed column),
* for each modeled **continuous** feature, the p1 / p50 / p99 quantiles, and
* for each modeled **categorical** feature, the top-category frequencies.

Each check carries a pass/fail against a tolerance:

* base rate ............ absolute +/- 0.03
* feed rate ............ absolute +/- 0.05
* missingness .......... absolute +/- 0.05
* continuous quantiles . within 30% *relative* for p50/p99 (50% for the noisier
                         p1 left tail), measured against a standard-deviation
                         floor so near-zero reference quantiles (e.g. revenue
                         trend, centered on ~0) are judged on the feature's spread
                         rather than its near-zero level

Categorical top-frequency checks are reported (and tolerance-checked at +/- 0.05
absolute) but, because the SCM categoricals are exogenous draws calibrated to the
real level probabilities, they default to *informational* unless you flip
``strict_categoricals=True``.

Nothing here mutates the generator or touches other modules; import via
``cldd.fidelity`` (the package ``__init__`` is intentionally left alone).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

from .scm import StructuralBorrowerGenerator

# --------------------------------------------------------------------------- #
# Configuration
# --------------------------------------------------------------------------- #

#: Default location of the real Intuit dataset (configurable via ``data_dir``).
DEFAULT_DATA_DIR = Path(
    "C:/Users/hossa/dev/intuit-techweek-hackathon/"
    "intuit-techweek-nyc-hackathon-2026/dataset"
)

#: Continuous features compared on p1/p50/p99 (modeled in the SCM marginals).
CONTINUOUS_FEATURES = (
    "stated_annual_revenue",
    "stated_time_in_business",
    "requested_amount",
    "observed_monthly_revenue_avg_3mo",
    "observed_revenue_trend_3mo",
    "observed_revenue_volatility",
    "observed_cash_balance_p10",
    "aggregate_credit_utilization",
    "existing_debt_obligations",
    "invoice_payment_delinquency_rate",
    "vintage_years",
)

#: Categorical features compared on top-category frequencies.
CATEGORICAL_FEATURES = (
    "sector",
    "geography_region",
    "employee_count_bucket",
    "owner_personal_credit_band",
    "application_channel",
)

#: One bank-feed column whose null-fraction defines bank-feed missingness.
_MISSINGNESS_PROBE = "observed_monthly_revenue_avg_3mo"

#: Tolerances.
BASE_RATE_TOL = 0.03          # absolute
FEED_RATE_TOL = 0.05          # absolute
MISSINGNESS_TOL = 0.05        # absolute
QUANTILE_REL_TOL = 0.30       # relative (fraction), for p50/p99
QUANTILE_TAIL_REL_TOL = 0.50  # relative (fraction), for the noisier p1 left tail
QUANTILE_STD_FLOOR = 1.0      # absolute band = tol * max(|real|, STD_FLOOR*std)
CATEGORICAL_TOL = 0.05        # absolute, per top category


# --------------------------------------------------------------------------- #
# Report dataclasses
# --------------------------------------------------------------------------- #


@dataclass
class FidelityCheck:
    """One real-vs-synthetic comparison with a pass/fail verdict."""

    name: str
    real: float
    synth: float
    tolerance: float
    kind: str             # "abs" or "rel"
    passed: bool
    counts: bool = True   # does this check count toward the overall verdict?

    @property
    def diff(self) -> float:
        return float(self.synth - self.real)

    @property
    def rel_diff(self) -> float:
        denom = abs(self.real) if abs(self.real) > 1e-12 else 1e-12
        return float((self.synth - self.real) / denom)


@dataclass
class FidelityReport:
    """Collection of fidelity checks plus an overall pass/fail."""

    checks: list[FidelityCheck] = field(default_factory=list)
    real_n_labeled: int = 0
    synth_n: int = 0
    data_dir: str = ""

    @property
    def counting_checks(self) -> list[FidelityCheck]:
        return [c for c in self.checks if c.counts]

    @property
    def passed(self) -> bool:
        return all(c.passed for c in self.counting_checks)

    @property
    def n_failed(self) -> int:
        return sum(not c.passed for c in self.counting_checks)

    def get(self, name: str) -> FidelityCheck:
        for c in self.checks:
            if c.name == name:
                return c
        raise KeyError(name)

    def to_table(self) -> str:
        """Human-readable fixed-width table of every check."""
        header = (
            f"FIDELITY REPORT  (real labeled n={self.real_n_labeled:,}, "
            f"synthetic n={self.synth_n:,})\n"
            f"data_dir: {self.data_dir}\n"
        )
        cols = ("check", "real", "synth", "diff", "tol", "verdict")
        rows = [cols]
        for c in self.checks:
            if c.kind == "rel":
                diff_s = f"{c.rel_diff:+.1%}"
                tol_s = f"<{c.tolerance:.0%} rel"
            else:
                diff_s = f"{c.diff:+.4f}"
                tol_s = f"+/-{c.tolerance:.3f}"
            verdict = "PASS" if c.passed else "FAIL"
            if not c.counts:
                verdict += "*"
            rows.append(
                (c.name, f"{c.real:.4f}", f"{c.synth:.4f}", diff_s, tol_s, verdict)
            )
        widths = [max(len(r[i]) for r in rows) for i in range(len(cols))]
        lines = []
        for ri, r in enumerate(rows):
            line = "  ".join(r[i].ljust(widths[i]) for i in range(len(cols)))
            lines.append(line)
            if ri == 0:
                lines.append("  ".join("-" * widths[i] for i in range(len(cols))))
        overall = "PASSED" if self.passed else f"FAILED ({self.n_failed} check(s))"
        footer = (
            f"\nOVERALL: {overall}    "
            f"(* = informational, not counted toward verdict)"
        )
        return header + "\n" + "\n".join(lines) + "\n" + footer

    def get_score(self) -> float:
        """SDMetrics-style 0..1 quality score.

        The score is the fraction of **counting** checks that passed -- i.e.
        ``len(passed counting checks) / len(counting_checks)``. Informational
        checks (``counts=False``) are excluded, matching how :attr:`passed` and
        :attr:`n_failed` treat them. Returns ``float('nan')`` when there are no
        counting checks (nothing to score).
        """
        counting = self.counting_checks
        if not counting:
            return float("nan")
        n_passed = sum(c.passed for c in counting)
        return float(n_passed) / float(len(counting))

    def get_details(self) -> pd.DataFrame:
        """SDMetrics-style per-check detail table as a DataFrame.

        One row per check (all checks, counting and informational) with columns
        ``[check, real, synth, diff, tolerance, kind, passed, counts]``. The
        ``diff`` column uses each check's signed ``.diff`` for ``kind=="abs"``
        checks and its signed ``.rel_diff`` for ``kind=="rel"`` checks, so the
        magnitude is directly comparable to ``tolerance`` for that row.
        """
        rows = []
        for c in self.checks:
            diff = c.rel_diff if c.kind == "rel" else c.diff
            rows.append(
                {
                    "check": c.name,
                    "real": c.real,
                    "synth": c.synth,
                    "diff": diff,
                    "tolerance": c.tolerance,
                    "kind": c.kind,
                    "passed": c.passed,
                    "counts": c.counts,
                }
            )
        columns = [
            "check", "real", "synth", "diff", "tolerance", "kind", "passed", "counts",
        ]
        return pd.DataFrame(rows, columns=columns)


# --------------------------------------------------------------------------- #
# Loaders
# --------------------------------------------------------------------------- #


def load_real(data_dir: str | Path = DEFAULT_DATA_DIR, split: str = "train") -> pd.DataFrame:
    """Load a split of the real Intuit dataset as a DataFrame.

    Parameters
    ----------
    data_dir : path to the dataset directory (defaults to :data:`DEFAULT_DATA_DIR`).
    split : one of ``"train"``, ``"validation"``, ``"test"`` (file ``<split>.csv``).
    """
    path = Path(data_dir) / f"{split}.csv"
    if not path.exists():
        raise FileNotFoundError(f"real dataset not found: {path}")
    return pd.read_csv(path)


def load_synthetic(
    n_applicants: int = 12000,
    seed: int = 42,
    generator: StructuralBorrowerGenerator | None = None,
    **generator_kwargs,
) -> dict:
    """Build (or accept) a :class:`StructuralBorrowerGenerator` cohort dict.

    Pass a pre-built ``generator`` to reuse it, or let this construct one with the
    given ``n_applicants`` / ``seed`` / extra ``generator_kwargs``.
    """
    if generator is None:
        generator = StructuralBorrowerGenerator(
            n_applicants=n_applicants, seed=seed, **generator_kwargs
        )
    return generator.generate_cohort()


# --------------------------------------------------------------------------- #
# Per-quantity computation
# --------------------------------------------------------------------------- #


def _real_base_rate(real: pd.DataFrame) -> tuple[float, int]:
    """Labeled default base rate over rows that actually carry a ``default_flag``."""
    s = real["default_flag"].dropna()
    return float(s.mean()), int(len(s))


def _quantile_check(name: str, real_vals, synth_vals, q: float, tag: str) -> FidelityCheck:
    rv = np.asarray(real_vals, dtype=float)
    rq = float(np.nanquantile(rv, q))
    sq = float(np.nanquantile(np.asarray(synth_vals, dtype=float), q))
    # Relative tolerance with a *standard-deviation* floor: a quantile sitting near
    # zero (e.g. revenue trend, which is centered on ~0) is judged against a band
    # that scales with the feature's spread, not its (near-zero) level. So the
    # absolute pass-band is ``tol * max(|real|, std)`` -- equivalently "within tol
    # relative, OR within tol of one standard deviation". The p1 left tail is
    # intrinsically noisier than p50/p99, so it gets the wider tail tolerance.
    std = float(np.nanstd(rv))
    tol = QUANTILE_TAIL_REL_TOL if tag == "p1" else QUANTILE_REL_TOL
    band = tol * max(abs(rq), QUANTILE_STD_FLOOR * std)
    passed = abs(sq - rq) <= band
    return FidelityCheck(
        name=name, real=rq, synth=sq, tolerance=tol,
        kind="rel", passed=passed, counts=True,
    )


def _top_category_checks(
    name: str, real_series: pd.Series, synth_series: pd.Series, top_k: int, counts: bool
) -> list[FidelityCheck]:
    real_freq = real_series.dropna().round().astype(int).value_counts(normalize=True)
    synth_freq = synth_series.dropna().round().astype(int).value_counts(normalize=True)
    checks: list[FidelityCheck] = []
    for level in list(real_freq.index[:top_k]):
        rf = float(real_freq.get(level, 0.0))
        sf = float(synth_freq.get(level, 0.0))
        checks.append(
            FidelityCheck(
                name=f"{name}=={level} freq", real=rf, synth=sf,
                tolerance=CATEGORICAL_TOL, kind="abs",
                passed=abs(sf - rf) <= CATEGORICAL_TOL, counts=counts,
            )
        )
    return checks


# --------------------------------------------------------------------------- #
# Top-level entry point
# --------------------------------------------------------------------------- #


def compute_fidelity(
    real: pd.DataFrame,
    cohort: dict,
    *,
    strict_categoricals: bool = False,
) -> FidelityReport:
    """Compare a real DataFrame against an SCM cohort dict; return a report.

    Parameters
    ----------
    real : real dataset split (e.g. from :func:`load_real`).
    cohort : an SCM cohort dict (from :func:`load_synthetic` / ``generate_cohort``).
    strict_categoricals : count categorical frequency checks toward the verdict.
    """
    synth = cohort["features"]
    report = FidelityReport(synth_n=len(synth))

    # ---- labeled default base rate (absolute) ----
    real_base, n_labeled = _real_base_rate(real)
    report.real_n_labeled = n_labeled
    synth_base = float(np.asarray(cohort["true_default"]).mean())
    report.checks.append(
        FidelityCheck(
            name="default_base_rate", real=real_base, synth=synth_base,
            tolerance=BASE_RATE_TOL, kind="abs",
            passed=abs(synth_base - real_base) <= BASE_RATE_TOL,
        )
    )

    # ---- has_linked_bank_feed rate (absolute) ----
    real_feed = float(real["has_linked_bank_feed"].mean())
    synth_feed = float((synth["has_linked_bank_feed"] > 0.5).mean())
    report.checks.append(
        FidelityCheck(
            name="has_linked_bank_feed_rate", real=real_feed, synth=synth_feed,
            tolerance=FEED_RATE_TOL, kind="abs",
            passed=abs(synth_feed - real_feed) <= FEED_RATE_TOL,
        )
    )

    # ---- bank-feed missingness (absolute) ----
    real_miss = float(real[_MISSINGNESS_PROBE].isna().mean())
    synth_miss = float(synth[_MISSINGNESS_PROBE].isna().mean())
    report.checks.append(
        FidelityCheck(
            name="bank_feed_missingness", real=real_miss, synth=synth_miss,
            tolerance=MISSINGNESS_TOL, kind="abs",
            passed=abs(synth_miss - real_miss) <= MISSINGNESS_TOL,
        )
    )

    # ---- continuous quantiles (relative) ----
    for feat in CONTINUOUS_FEATURES:
        if feat not in real.columns or feat not in synth.columns:
            continue
        rv = real[feat].to_numpy()
        sv = synth[feat].to_numpy()
        for q, tag in ((0.01, "p1"), (0.50, "p50"), (0.99, "p99")):
            report.checks.append(_quantile_check(f"{feat} {tag}", rv, sv, q, tag))

    # ---- categorical top-frequencies (informational unless strict) ----
    for feat in CATEGORICAL_FEATURES:
        if feat not in real.columns or feat not in synth.columns:
            continue
        report.checks.extend(
            _top_category_checks(
                feat, real[feat], synth[feat], top_k=3, counts=strict_categoricals
            )
        )

    return report


def run_fidelity_gate(
    data_dir: str | Path = DEFAULT_DATA_DIR,
    split: str = "train",
    n_applicants: int = 12000,
    seed: int = 42,
    *,
    generator: StructuralBorrowerGenerator | None = None,
    strict_categoricals: bool = False,
    **generator_kwargs,
) -> FidelityReport:
    """Load real data + build a cohort + compute the full fidelity report."""
    real = load_real(data_dir, split=split)
    cohort = load_synthetic(
        n_applicants=n_applicants, seed=seed, generator=generator, **generator_kwargs
    )
    report = compute_fidelity(real, cohort, strict_categoricals=strict_categoricals)
    report.data_dir = str(data_dir)
    return report
