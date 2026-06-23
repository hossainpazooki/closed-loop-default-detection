"""Tests for the additive SDMetrics-style accessors on FidelityReport.

These need NO real data: we hand-construct a FidelityReport from a handful of
FidelityCheck instances (a mix of passed/failed and counting/informational) and
assert that get_score() / get_details() behave as documented, while the existing
.passed / .n_failed properties are unchanged by the additions.
"""

from __future__ import annotations

import math

import pandas as pd

from cldd.fidelity import FidelityCheck, FidelityReport


def _sample_checks() -> list[FidelityCheck]:
    # Two counting checks pass, one counting check fails, plus one informational
    # (counts=False) check that fails -> counting pass-fraction is 2/3.
    return [
        FidelityCheck(
            name="abs_pass", real=0.20, synth=0.21, tolerance=0.05,
            kind="abs", passed=True, counts=True,
        ),
        FidelityCheck(
            name="rel_pass", real=100.0, synth=110.0, tolerance=0.30,
            kind="rel", passed=True, counts=True,
        ),
        FidelityCheck(
            name="abs_fail", real=0.20, synth=0.40, tolerance=0.05,
            kind="abs", passed=False, counts=True,
        ),
        FidelityCheck(
            name="info_fail", real=0.10, synth=0.30, tolerance=0.05,
            kind="abs", passed=False, counts=False,
        ),
    ]


def test_get_score_in_range_and_expected_fraction() -> None:
    report = FidelityReport(checks=_sample_checks())
    score = report.get_score()
    # 3 counting checks, 2 of them passed -> 2/3.
    assert 0.0 <= score <= 1.0
    assert score == 2.0 / 3.0


def test_get_score_all_pass_is_one_all_fail_is_zero() -> None:
    all_pass = FidelityReport(checks=[
        FidelityCheck("a", 0.1, 0.1, 0.05, "abs", True, True),
        FidelityCheck("b", 0.2, 0.2, 0.05, "abs", True, True),
    ])
    all_fail = FidelityReport(checks=[
        FidelityCheck("a", 0.1, 0.9, 0.05, "abs", False, True),
        FidelityCheck("b", 0.2, 0.9, 0.05, "abs", False, True),
    ])
    assert all_pass.get_score() == 1.0
    assert all_fail.get_score() == 0.0


def test_get_score_nan_when_no_counting_checks() -> None:
    # Only informational checks -> nothing to score.
    report = FidelityReport(checks=[
        FidelityCheck("info", 0.1, 0.2, 0.05, "abs", False, False),
    ])
    assert math.isnan(report.get_score())

    # Empty report likewise has no counting checks.
    assert math.isnan(FidelityReport().get_score())


def test_get_details_columns_and_one_row_per_check() -> None:
    checks = _sample_checks()
    report = FidelityReport(checks=checks)
    df = report.get_details()

    assert isinstance(df, pd.DataFrame)
    assert list(df.columns) == [
        "check", "real", "synth", "diff", "tolerance", "kind", "passed", "counts",
    ]
    assert len(df) == len(checks)
    assert list(df["check"]) == [c.name for c in checks]


def test_get_details_diff_uses_abs_or_rel_per_kind() -> None:
    report = FidelityReport(checks=_sample_checks())
    df = report.get_details().set_index("check")

    # abs check: diff column is the signed absolute difference (synth - real).
    assert df.loc["abs_pass", "diff"] == 0.21 - 0.20
    # rel check: diff column is the signed relative difference.
    assert df.loc["rel_pass", "diff"] == (110.0 - 100.0) / 100.0


def test_existing_passed_and_n_failed_unchanged() -> None:
    report = FidelityReport(checks=_sample_checks())
    # One counting check fails; the informational failure does not count.
    assert report.passed is False
    assert report.n_failed == 1

    all_pass = FidelityReport(checks=[
        FidelityCheck("a", 0.1, 0.1, 0.05, "abs", True, True),
        FidelityCheck("info", 0.1, 0.9, 0.05, "abs", False, False),
    ])
    assert all_pass.passed is True
    assert all_pass.n_failed == 0
