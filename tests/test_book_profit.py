"""Tests for :func:`cldd.emp.realized_book_profit` (v3 spec section 1.1): the
additive book-P&L helper for ``FeedbackLoop``. Hand-computed miniature cohorts,
matching ``tests/test_emp.py``'s no-Monte-Carlo discipline -- every array here
is a fixed literal, no ``np.random`` anywhere.
"""

from __future__ import annotations

import hashlib
import subprocess
import sys

import numpy as np
import pytest

from cldd.emp import LoanEconomics, realized_book_profit

# --------------------------------------------------------------------------- #
# 1. All-good book.
# --------------------------------------------------------------------------- #


def test_all_good_book_all_funded():
    """No defaulters, everyone funded: total profit is the sum of the good-loan
    formula A*(f + r_term) over all rows; denominator is n * mean(A) over the
    (identical) full cohort."""
    econ = LoanEconomics()
    y = np.zeros(4)
    default_day = np.full(4, np.nan)
    amt = np.array([1000.0, 2000.0, 1500.0, 2500.0])
    funded = np.array([True, True, True, True])

    result = realized_book_profit(y, default_day, amt, funded, econ)

    per_row = amt * (econ.origination_fee_rate + econ.r_term)
    expected = float(np.sum(per_row)) / (4 * float(np.mean(amt)))
    assert result == pytest.approx(expected)


def test_all_good_book_partially_funded_uses_full_cohort_denominator():
    """Only 2 of 4 good rows funded: numerator sums the funded rows only, but
    the denominator still uses the mean requested_amount over ALL 4 rows, not
    just the 2 funded ones -- this is the full-cohort-denominator contract."""
    econ = LoanEconomics()
    y = np.zeros(4)
    default_day = np.full(4, np.nan)
    amt = np.array([1000.0, 2000.0, 1500.0, 2500.0])
    funded = np.array([True, False, True, False])

    result = realized_book_profit(y, default_day, amt, funded, econ)

    funded_profit = amt[funded] * (econ.origination_fee_rate + econ.r_term)
    full_cohort_mean_a = float(np.mean(amt))  # mean over all 4, not the 2 funded
    expected = float(np.sum(funded_profit)) / (4 * full_cohort_mean_a)
    assert result == pytest.approx(expected)
    # Sanity: this must differ from a (wrong) funded-only-mean denominator.
    funded_only_mean_a = float(np.mean(amt[funded]))
    wrong = float(np.sum(funded_profit)) / (4 * funded_only_mean_a)
    assert result != pytest.approx(wrong)


# --------------------------------------------------------------------------- #
# 2. All-default at day 0 / day TERM_DAYS / day 90 (imputation + fallback).
# --------------------------------------------------------------------------- #


def test_all_default_day_zero_all_funded():
    """t=0 <= TERM_DAYS (body): lambda = 1 - f, profit = A*(f - 1) per row
    (exact clipped formula, no imputation involved)."""
    econ = LoanEconomics()
    y = np.ones(3)
    default_day = np.zeros(3)
    amt = np.array([1000.0, 2000.0, 500.0])
    funded = np.array([True, True, True])

    result = realized_book_profit(y, default_day, amt, funded, econ)

    per_row = amt * (econ.origination_fee_rate - 1.0)
    expected = float(np.sum(per_row)) / (3 * float(np.mean(amt)))
    assert result == pytest.approx(expected)


def test_all_default_day_term_all_funded():
    """t = TERM_DAYS (body boundary): lambda = 0 (full recovery), profit equals
    the good-loan formula A*(f + r_term) exactly."""
    econ = LoanEconomics()
    y = np.ones(3)
    default_day = np.full(3, float(econ.term_days))
    amt = np.array([1000.0, 2000.0, 500.0])
    funded = np.array([True, True, True])

    result = realized_book_profit(y, default_day, amt, funded, econ)

    per_row = amt * (econ.origination_fee_rate + econ.r_term)
    expected = float(np.sum(per_row)) / (3 * float(np.mean(amt)))
    assert result == pytest.approx(expected)


def test_all_default_day_ninety_all_funded_empty_body_fallback():
    """All rows are past TERM_DAYS (day-90 mass) so the COHORT body is empty:
    decision-5 fallback is lambda = 1 (full loss), profit = -A per funded row.
    (Basis is the full cohort per the Rev 2.1 amendment; cohort == funded here.)"""
    econ = LoanEconomics()
    y = np.ones(3)
    default_day = np.full(3, 90.0)
    amt = np.array([1000.0, 2000.0, 500.0])
    funded = np.array([True, True, True])

    result = realized_book_profit(y, default_day, amt, funded, econ)

    expected = float(np.sum(-amt)) / (3 * float(np.mean(amt)))
    assert result == pytest.approx(expected)


def test_day_ninety_imputation_uses_cohort_body_mean():
    """Mixed body + day-90 tail, ALL funded (cohort == funded): the day-90 row
    is priced at the mean body lambda of the cohort's body defaulters (day 0
    and day TERM_DAYS here), not any global constant."""
    econ = LoanEconomics()
    y = np.array([1.0, 1.0, 1.0])
    default_day = np.array([0.0, float(econ.term_days), 90.0])
    amt = np.array([1000.0, 2000.0, 1500.0])
    funded = np.array([True, True, True])

    result = realized_book_profit(y, default_day, amt, funded, econ)

    lam0 = 1.0 - econ.origination_fee_rate  # day-0 body lambda
    lam_term = 0.0  # day-TERM_DAYS body lambda
    body_mean = np.mean([lam0, lam_term])
    per_row_profit = np.array(
        [
            amt[0] * (econ.origination_fee_rate - 1.0),
            amt[1] * (econ.origination_fee_rate + econ.r_term),
            -body_mean * amt[2],
        ]
    )
    expected = float(np.sum(per_row_profit)) / (3 * float(np.mean(amt)))
    assert result == pytest.approx(expected)


# --------------------------------------------------------------------------- #
# 3. Mixed funded mask (good + body + tail, some declined).
# --------------------------------------------------------------------------- #


def test_mixed_funded_mask_full_cohort_denominator_arithmetic():
    """6-row cohort: 2 good, 1 body defaulter (day 10), 1 body defaulter
    (day TERM_DAYS), 1 day-90 tail defaulter, 1 declined good row. Only 5 of
    the 6 rows are funded (the last good row is declined) -- numerator excludes
    it, denominator's mean(A) still includes it (full cohort, n=6)."""
    econ = LoanEconomics()
    y = np.array([0.0, 0.0, 1.0, 1.0, 1.0, 0.0])
    default_day = np.array([np.nan, np.nan, 10.0, float(econ.term_days), 90.0, np.nan])
    amt = np.array([1000.0, 1200.0, 1500.0, 2000.0, 1800.0, 2500.0])
    funded = np.array([True, True, True, True, True, False])

    result = realized_book_profit(y, default_day, amt, funded, econ)

    f = funded
    fy, fday, famt = y[f], default_day[f], amt[f]
    is_default = fy == 1
    body_mask = is_default & (fday <= econ.term_days)
    tail_mask = is_default & (fday > econ.term_days)
    good_mask = ~is_default

    profit = np.empty(f.sum())
    profit[good_mask] = famt[good_mask] * (econ.origination_fee_rate + econ.r_term)
    t_body = fday[body_mask]
    profit[body_mask] = famt[body_mask] * (
        econ.origination_fee_rate + (t_body / econ.term_days) * (1.0 + econ.r_term) - 1.0
    )
    body_mean_lambda = float(np.mean(np.clip(1.0 - econ.origination_fee_rate
                                              - (t_body / econ.term_days) * (1.0 + econ.r_term),
                                              0.0, 1.0)))
    profit[tail_mask] = -body_mean_lambda * famt[tail_mask]

    full_cohort_mean_a = float(np.mean(amt))  # n=6, includes the declined row
    expected = float(np.sum(profit)) / (6 * full_cohort_mean_a)
    assert result == pytest.approx(expected)


def test_nothing_funded_returns_zero_when_denom_nonzero():
    """Empty funded mask: numerator is an empty-array sum = 0.0; denominator
    is still nonzero (full-cohort mean requested_amount), so the result is
    exactly 0.0, not None or NaN."""
    econ = LoanEconomics()
    y = np.array([0.0, 1.0, 1.0])
    default_day = np.array([np.nan, 10.0, 90.0])
    amt = np.array([1000.0, 2000.0, 1500.0])
    funded = np.array([False, False, False])

    result = realized_book_profit(y, default_day, amt, funded, econ)
    assert result == pytest.approx(0.0)


# --------------------------------------------------------------------------- #
# 4. Flat cohort -> None.
# --------------------------------------------------------------------------- #


def test_flat_cohort_default_day_none_returns_none():
    """default_day=None (no planted timing, the flat-generator contract):
    realized_book_profit returns None outright, mirroring emp_harness."""
    y = np.array([0.0, 1.0, 0.0, 1.0])
    amt = np.array([1000.0, 2000.0, 1500.0, 2500.0])
    funded = np.array([True, True, False, True])

    result = realized_book_profit(y, None, amt, funded, LoanEconomics())
    assert result is None


def test_flat_cohort_default_day_none_uses_default_economics():
    """None default_day short-circuits before any economics is touched, so the
    result is None regardless of the economics argument."""
    y = np.array([0.0, 1.0])
    amt = np.array([1000.0, 2000.0])
    funded = np.array([True, False])

    assert realized_book_profit(y, None, amt, funded) is None
    assert realized_book_profit(y, None, amt, funded, LoanEconomics()) is None


# --------------------------------------------------------------------------- #
# 5. Cross-process float determinism.
# --------------------------------------------------------------------------- #

_DETERMINISM_SNIPPET = """
import numpy as np
from cldd.emp import realized_book_profit, LoanEconomics

econ = LoanEconomics()
y = np.array([0.0, 0.0, 1.0, 1.0, 1.0, 0.0, 1.0, 0.0])
default_day = np.array(
    [np.nan, np.nan, 10.0, float(econ.term_days), 90.0, np.nan, 45.0, np.nan]
)
amt = np.array([1000.0, 1200.0, 1500.0, 2000.0, 1800.0, 2500.0, 1300.0, 2200.0])
funded = np.array([True, True, True, True, True, False, True, False])

result = realized_book_profit(y, default_day, amt, funded, econ)

payload = repr(result)
import hashlib
print(hashlib.sha256(payload.encode("utf-8")).hexdigest())
"""


def _compute_reference_hash() -> str:
    import numpy as _np

    from cldd.emp import LoanEconomics as _LoanEconomics
    from cldd.emp import realized_book_profit as _realized_book_profit

    econ = _LoanEconomics()
    y = _np.array([0.0, 0.0, 1.0, 1.0, 1.0, 0.0, 1.0, 0.0])
    default_day = _np.array(
        [_np.nan, _np.nan, 10.0, float(econ.term_days), 90.0, _np.nan, 45.0, _np.nan]
    )
    amt = _np.array([1000.0, 1200.0, 1500.0, 2000.0, 1800.0, 2500.0, 1300.0, 2200.0])
    funded = _np.array([True, True, True, True, True, False, True, False])

    result = _realized_book_profit(y, default_day, amt, funded, econ)

    payload = repr(result)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def test_cross_process_float_determinism():
    """The sha256 of the serialized realized_book_profit result, recomputed in
    a fresh subprocess, matches an in-process recomputation exactly -- no
    RNG/platform-order float drift in the helper."""
    proc = subprocess.run(
        [sys.executable, "-c", _DETERMINISM_SNIPPET],
        capture_output=True,
        text=True,
        check=True,
    )
    subprocess_hash = proc.stdout.strip()
    in_process_hash = _compute_reference_hash()

    assert subprocess_hash == in_process_hash


# --------------------------------------------------------------------------- #
# 5. Pricing basis: cohort-invariant imputation (spec Rev 2.1 amendment).
#    H4's "arithmetic identity" (spec section 3) requires per-row profits to be
#    subset-independent: pricing the day-90 imputation on the priced slice's own
#    body mean makes book P&L non-additive across slices and broke the pilot
#    gate (max abs err ~2e-4 vs 1e-6 tol, 2026-07-19). Basis = FULL COHORT.
# --------------------------------------------------------------------------- #


def test_h4_additivity_identity_across_book_and_explored_slice():
    """rbp(policy|explored) - rbp(policy) must equal rbp(explored) exactly:
    the frozen arm's H4 identity at unit scale. Requires a pricing basis that
    does not shift when the explored slice adds body defaulters."""
    econ = LoanEconomics()
    y = np.array([0.0, 1.0, 1.0, 1.0, 0.0, 0.0])
    default_day = np.array([np.nan, 30.0, 90.0, 10.0, np.nan, np.nan])
    amt = np.array([1000.0, 2000.0, 1500.0, 800.0, 1200.0, 900.0])
    policy = np.array([True, True, True, False, False, False])
    explored = np.array([False, False, False, True, True, False])
    funded = policy | explored

    diff = realized_book_profit(y, default_day, amt, funded, econ) - realized_book_profit(
        y, default_day, amt, policy, econ
    )
    assert diff == pytest.approx(
        realized_book_profit(y, default_day, amt, explored, econ), rel=1e-12
    )


def test_day_ninety_imputation_basis_is_cohort_not_funded_slice():
    """A funded day-90 row with an empty FUNDED body but a non-empty COHORT body
    is priced at the cohort's body mean, not the lambda=1 fallback: the
    imputation basis is a planted cohort property, invariant to who funds."""
    econ = LoanEconomics()
    y = np.array([1.0, 0.0, 1.0, 1.0])
    default_day = np.array([90.0, np.nan, 0.0, float(econ.term_days)])
    amt = np.array([1000.0, 1000.0, 1000.0, 1000.0])
    funded = np.array([True, True, False, False])

    result = realized_book_profit(y, default_day, amt, funded, econ)

    lam0 = 1.0 - econ.origination_fee_rate  # day-0 body lambda
    cohort_body_mean = np.mean([lam0, 0.0])  # day-TERM_DAYS lambda is 0
    expected = (-cohort_body_mean * amt[0] + amt[1] * (econ.origination_fee_rate + econ.r_term)) / (
        4 * float(np.mean(amt))
    )
    assert result == pytest.approx(expected)
