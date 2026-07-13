"""Paired significance test for the strong-cohort g-computation gap.

This script hardens docs/assessment.md's informal "~8 SE above zero" claim for the
severity-0.4 counterfactual into a proper paired hypothesis test. For each
severity it takes the 25-seed ``strong_gap`` column (naive_strong minus
gcomp_strong, i.e. how much the g-computation correction reduces strong-cohort
error relative to the naive baseline) and runs two complementary one-sided
tests against a null of zero gap:

  * Wilcoxon signed-rank test (non-parametric, alternative="greater"), which
    makes no normality assumption about the paired differences; and
  * a one-sample paired t-test (scipy.stats.ttest_1samp against 0.0,
    alternative="greater"), which is the parametric analogue and the formal
    version of the "SE above zero" heuristic.

CRITICAL FRAMING. At severity 0.4 the gap is both statistically significant and
materially large (+0.0134), so the g-computation advantage is real and
deployable there. At severity 1.0 the gap is *statistically significant in sign*
(the tests reject the zero-gap null) but its magnitude is negligible (+0.0017).
Significance is not a deployable effect: we therefore claim NO deployable
advantage at full severity despite the small p-values. The collapse of the gap
as severity rises from 0.4 to 1.0 is the actual finding.

Deterministic: reads a committed CSV and runs closed-form/exact statistics.
There is no randomness and no seeding required. ASCII-only stdout for the
Windows cp1252 console.

Run from the CLDD repo root with the pinned interpreter:
  .venv\\Scripts\\python.exe scripts/paired_significance.py
"""

from __future__ import annotations

import csv
from pathlib import Path

from scipy import stats

REPO_ROOT = Path(__file__).resolve().parent.parent
SWEEP_CSV = REPO_ROOT / "artifacts" / "seed_sweep_25.csv"
OUT_CSV = REPO_ROOT / "artifacts" / "paired_significance.csv"

SEVERITIES = (0.4, 1.0)


def load_strong_gaps(path: Path):
    """Return {severity_rounded: [strong_gap, ...]} from the seed sweep CSV."""
    by_sev: dict[float, list[float]] = {round(s, 4): [] for s in SEVERITIES}
    with path.open(newline="") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            sev = round(float(row["severity"]), 4)
            if sev in by_sev:
                by_sev[sev].append(float(row["strong_gap"]))
    return by_sev


def sample_sd(values):
    """Sample standard deviation (ddof=1)."""
    n = len(values)
    mean = sum(values) / n
    var = sum((v - mean) ** 2 for v in values) / (n - 1)
    return var ** 0.5


def main():
    by_sev = load_strong_gaps(SWEEP_CSV)

    rows = []
    for sev in SEVERITIES:
        key = round(sev, 4)
        gaps = by_sev[key]
        n = len(gaps)
        mean = sum(gaps) / n
        sd = sample_sd(gaps)
        n_positive = sum(1 for g in gaps if g > 0.0)

        # One-sided Wilcoxon signed-rank: is the median gap greater than 0?
        wilcoxon = stats.wilcoxon(gaps, alternative="greater")
        # One-sample paired t-test against a 0.0 gap, one-sided greater.
        ttest = stats.ttest_1samp(gaps, 0.0, alternative="greater")

        rows.append(
            {
                "severity": sev,
                "n": n,
                "mean": mean,
                "sd": sd,
                "n_positive": n_positive,
                "wilcoxon_W": float(wilcoxon.statistic),
                "wilcoxon_p": float(wilcoxon.pvalue),
                "t_stat": float(ttest.statistic),
                "t_p": float(ttest.pvalue),
            }
        )

    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "severity",
        "n",
        "mean",
        "sd",
        "n_positive",
        "wilcoxon_W",
        "wilcoxon_p",
        "t_stat",
        "t_p",
    ]
    with OUT_CSV.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)

    print("Paired significance test on 25-seed strong_gap (alt=greater)")
    print("source: " + str(SWEEP_CSV))
    print("output: " + str(OUT_CSV))
    print("")
    for row in rows:
        print("severity %.1f  (n=%d)" % (row["severity"], row["n"]))
        print("  mean strong_gap = %+.4f   sd = %.4f   positive = %d/%d"
              % (row["mean"], row["sd"], row["n_positive"], row["n"]))
        print("  Wilcoxon  W = %.1f   p = %.3e"
              % (row["wilcoxon_W"], row["wilcoxon_p"]))
        print("  paired t  t = %.3f   p = %.3e"
              % (row["t_stat"], row["t_p"]))
        print("")
    print("NOTE: severity 1.0 is significant in SIGN but the magnitude")
    print("(+0.0017) is negligible -- no deployable advantage is claimed there.")


if __name__ == "__main__":
    main()
