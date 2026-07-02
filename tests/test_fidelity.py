"""Tests for the fidelity gate (the VERIFY FIDELITY stage).

These assert that a StructuralBorrowerGenerator cohort passes the gate against the
real Intuit data: labeled default base rate, has_linked_bank_feed rate, bank-feed
missingness, and a couple of continuous quantiles, all within tolerance. We use a
reasonably large cohort (n>=8000) so the quantiles are stable.

If the real dataset is not present the data-backed tests skip rather than fail, so
the suite stays green in environments without the dataset.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pandas as pd
import pytest

from cldd.fidelity import (
    BASE_RATE_TOL,
    DEFAULT_DATA_DIR,
    FEED_RATE_TOL,
    MISSINGNESS_TOL,
    compute_fidelity,
    load_real,
    load_synthetic,
)

_N = 10000
_SEED = 42


@pytest.fixture(scope="module")
def real() -> pd.DataFrame:
    try:
        return load_real(DEFAULT_DATA_DIR, split="train")
    except FileNotFoundError:
        pytest.skip(f"real dataset not found under {DEFAULT_DATA_DIR}")


@pytest.fixture(scope="module")
def cohort() -> dict:
    return load_synthetic(n_applicants=_N, seed=_SEED)


@pytest.fixture(scope="module")
def report(real, cohort):
    return compute_fidelity(real, cohort)


def test_overall_gate_passes(report):
    assert report.passed, f"fidelity gate failed:\n{report.to_table()}"


def test_base_rate_within_tolerance(report):
    c = report.get("default_base_rate")
    assert c.passed
    assert abs(c.diff) <= BASE_RATE_TOL


def test_feed_rate_within_tolerance(report):
    c = report.get("has_linked_bank_feed_rate")
    assert c.passed
    assert abs(c.diff) <= FEED_RATE_TOL


def test_missingness_within_tolerance(report):
    c = report.get("bank_feed_missingness")
    assert c.passed
    assert abs(c.diff) <= MISSINGNESS_TOL


@pytest.mark.parametrize(
    "name",
    [
        "stated_annual_revenue p50",
        "requested_amount p50",
        "aggregate_credit_utilization p50",
    ],
)
def test_continuous_quantiles_within_tolerance(report, name):
    c = report.get(name)
    assert c.passed, f"{name}: real={c.real:.4f} synth={c.synth:.4f} ({c.rel_diff:+.1%})"


def test_table_is_renderable(report):
    table = report.to_table()
    assert "FIDELITY REPORT" in table
    assert "OVERALL" in table


def test_determinism_same_seed(real):
    a = compute_fidelity(real, load_synthetic(n_applicants=_N, seed=_SEED))
    b = compute_fidelity(real, load_synthetic(n_applicants=_N, seed=_SEED))
    assert a.get("default_base_rate").synth == b.get("default_base_rate").synth


# --------------------------------------------------------------------------- #
# Portable data-dir behavior (CLDD_DATA_DIR)
# --------------------------------------------------------------------------- #


def test_load_real_missing_dir_raises_with_env_hint(tmp_path):
    """load_real on a nonexistent dir raises FileNotFoundError naming CLDD_DATA_DIR.

    Guards the portable knob's discoverability: the error must point the user at
    the CLDD_DATA_DIR environment variable, not just fail opaquely.
    """
    missing = tmp_path / "nope"
    with pytest.raises(FileNotFoundError) as excinfo:
        load_real(missing, split="train")
    assert "CLDD_DATA_DIR" in str(excinfo.value)


def test_cldd_data_dir_env_overrides_default(tmp_path):
    """CLDD_DATA_DIR overrides DEFAULT_DATA_DIR at module import time.

    Resolution happens at import, so we assert it in a fresh subprocess with the
    env var set -- this keeps the in-process module (and the rest of the suite)
    untouched, no reload side effects.
    """
    target = tmp_path / "some_data_dir"
    target.mkdir()
    code = (
        "import cldd.fidelity as f; "
        "print(str(f.DEFAULT_DATA_DIR))"
    )
    env = dict(**__import__("os").environ)
    env["CLDD_DATA_DIR"] = str(target)
    result = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        env=env,
    )
    assert result.returncode == 0, result.stderr
    assert Path(result.stdout.strip()) == target
