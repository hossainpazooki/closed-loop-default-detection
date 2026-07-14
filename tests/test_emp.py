"""Tests for the EMP measurement layer (``cldd.emp``): the literature EMPC closed
form (Verbraken/Bravo/Weber/Baesens 2014, EJOR 238(2):505-513, Eqs. 13/15) and the
harness-derived EMP from planted default timing + loan economics. Pure numpy, zero
RNG anywhere -- every cohort here is a hand-picked, fully deterministic array (no
``np.random``), matching the module's own no-Monte-Carlo discipline.
"""

from __future__ import annotations

import hashlib
import subprocess
import sys

import numpy as np
import pytest

from cldd import config
from cldd.emp import (
    EMPCParams,
    EMPResult,
    LoanEconomics,
    _roc_hull_vertices,
    empc_literature,
    emp_harness,
    loss_fractions,
    realized_profits,
)

# --------------------------------------------------------------------------- #
# 1. Hand-computed convex-hull cases.
# --------------------------------------------------------------------------- #


def test_empc_perfect_ranking_hand_computed():
    """n=4, perfect separation (all defaulters score above all goods).

    ROC vertices (r1, r0), before dedup/hull: (0,0)->(0,.5)->(0,1)->(.5,1)->(1,1).
    (0,0) and (0,.5) are dominated (same FPR, lower TPR) and drop out; the
    remaining collinear midpoint (.5,1) sits exactly on the (0,1)-(1,1) segment
    and drops too, leaving the two-vertex hull [(0,1), (1,1)].

    pi0 = pi1 = 0.5. dr0 over the single hull segment is 0 -> lambda_1 = inf
    (the segment is a pure FPR cost with zero TPR gain), so k = 0 (only
    lambda_0 = 0 qualifies as < 1) and lambda_{k+1} is capped to 1.

    EMP = (1-p0-p1) * [(pi0*r0_0/2)*(1^2-0^2) - ROI*pi1*r1_0*(1-0)]
          + p1*(pi0*r0_1 - ROI*pi1*r1_1)
        = 0.35 * [(0.5*1.0/2)*1 - 0.2644*0.5*0*1] + 0.10*(0.5*1.0 - 0.2644*0.5*1.0)
        = 0.35 * 0.25 + 0.10 * 0.3678
        = 0.0875 + 0.03678 = 0.12428

    eta = (1-p0-p1)*(pi0*r0_0+pi1*r1_0)*(1-0) + p1*(pi0*r0_1+pi1*r1_1)
        = 0.35*(0.5*1.0+0.5*0) + 0.10*(0.5+0.5) = 0.35*0.5 + 0.10 = 0.275
    optimal_fraction = 1 - eta = 0.725
    """
    y = np.array([1, 1, 0, 0], dtype=float)
    scores = np.array([2, 1, 0, -1], dtype=float)  # defaulters ranked riskiest

    result = empc_literature(y, scores)

    assert result.n == 4
    assert result.emp == pytest.approx(0.12428)
    assert result.optimal_fraction == pytest.approx(0.725)


def test_empc_mixed_ranking_hand_computed_with_surviving_hull_vertex():
    """n=6, 3 defaulters / 3 goods, ranking order (riskiest first) pos,neg,pos,
    pos,neg,neg. This is the 'random-like' case: the ROC has a genuine
    non-trivial intermediate hull vertex (unlike the perfect-separation case,
    which collapses to two points).

    Raw ROC vertices (r1, r0): (0,0), (0,1/3), (1/3,1/3), (1/3,2/3), (1/3,1),
    (2/3,1), (1,1). Dedup to max-r0-per-r1: (0,1/3), (1/3,1), (2/3,1), (1,1).
    Convex-hull scan drops (2/3,1) (collinear with (1/3,1)-(1,1)), leaving the
    3-vertex hull [(0,1/3), (1/3,1), (1,1)] -- verified directly below via the
    private hull helper, then EMPC is hand-derived from those exact vertices.
    """
    y = np.array([1, 0, 1, 1, 0, 0], dtype=float)
    scores = np.array([6, 5, 4, 3, 2, 1], dtype=float)

    r1_hull, r0_hull = _roc_hull_vertices(y, scores)
    np.testing.assert_allclose(r1_hull, [0.0, 1.0 / 3.0, 1.0])
    np.testing.assert_allclose(r0_hull, [1.0 / 3.0, 1.0, 1.0])

    # pi0 = pi1 = 0.5 (3 of each class).
    pi0 = pi1 = 0.5
    roi, p0, p1 = config.EMPC_ROI, config.EMPC_P0, config.EMPC_P1
    mix = 1.0 - p0 - p1

    dr0 = [1.0 - 1.0 / 3.0, 1.0 - 1.0]  # [2/3, 0]
    dr1 = [1.0 / 3.0 - 0.0, 1.0 - 1.0 / 3.0]  # [1/3, 2/3]

    lam1 = roi * pi1 * dr1[0] / (pi0 * dr0[0])  # finite: dr0[0] > 0
    assert dr0[1] == 0.0  # second segment is the inf-cost closing segment
    # k = max{i | lambda_i < 1}: lambda_0=0 and lambda_1=lam1 both < 1;
    # lambda_2 would be +inf (dr0[1]=0) so it does not qualify -> k=1.
    k = 1
    lam = [0.0, lam1, 1.0]  # lambda_{k+1} capped to 1 for use in the sum

    term0 = (pi0 * r0_hull[0] / 2.0) * (lam[1] ** 2 - lam[0] ** 2) - roi * pi1 * r1_hull[
        0
    ] * (lam[1] - lam[0])
    term1 = (pi0 * r0_hull[1] / 2.0) * (lam[2] ** 2 - lam[1] ** 2) - roi * pi1 * r1_hull[
        1
    ] * (lam[2] - lam[1])
    expected_emp = mix * (term0 + term1) + p1 * (pi0 * r0_hull[k + 1] - roi * pi1 * r1_hull[k + 1])

    eta0 = (pi0 * r0_hull[0] + pi1 * r1_hull[0]) * (lam[1] - lam[0])
    eta1 = (pi0 * r0_hull[1] + pi1 * r1_hull[1]) * (lam[2] - lam[1])
    expected_eta = mix * (eta0 + eta1) + p1 * (pi0 * r0_hull[k + 1] + pi1 * r1_hull[k + 1])
    expected_fraction = 1.0 - expected_eta

    result = empc_literature(y, scores)
    assert result.n == 6
    assert result.emp == pytest.approx(expected_emp)
    assert result.optimal_fraction == pytest.approx(expected_fraction)
    # Sanity pin against the independently-verified decimal values.
    assert result.emp == pytest.approx(0.10987614899999998)
    assert result.optimal_fraction == pytest.approx(0.6898016666666666)


# --------------------------------------------------------------------------- #
# 2. Monotone-transform invariance, both entry points.
# --------------------------------------------------------------------------- #


def test_empc_invariant_to_monotone_transforms():
    y = np.array([1, 0, 1, 1, 0, 0], dtype=float)
    scores = np.array([6.0, 5.0, 4.0, 3.0, 2.0, 1.0])

    base = empc_literature(y, scores)
    linear = empc_literature(y, 2.0 * scores + 1.0)
    sigmoid = empc_literature(y, 1.0 / (1.0 + np.exp(-scores)))

    assert linear == base
    assert sigmoid.n == base.n
    assert sigmoid.emp == pytest.approx(base.emp)
    assert sigmoid.optimal_fraction == pytest.approx(base.optimal_fraction)


def test_emp_harness_invariant_to_monotone_transforms():
    y = np.array([1, 0, 1, 1, 0, 0], dtype=float)
    scores = np.array([6.0, 5.0, 4.0, 3.0, 2.0, 1.0])
    default_day = np.array([10.0, np.nan, 40.0, 90.0, np.nan, np.nan])
    amt = np.array([1000.0, 2000.0, 1500.0, 2500.0, 1200.0, 1800.0])
    econ = LoanEconomics()

    base = emp_harness(y, scores, default_day, amt, econ)
    linear = emp_harness(y, 2.0 * scores + 1.0, default_day, amt, econ)
    sigmoid = emp_harness(y, 1.0 / (1.0 + np.exp(-scores)), default_day, amt, econ)

    assert linear == base
    assert sigmoid == base


# --------------------------------------------------------------------------- #
# 3. A strictly better ranking never yields lower EMP on the same rows.
# --------------------------------------------------------------------------- #


def test_empc_better_ranking_never_lower_emp():
    """A perfect ranking's ROC hull weakly dominates any other ranking's hull
    pointwise (r0 >= any achievable r0 at the same r1), so EMPC(perfect) >=
    EMPC(anything else) on the same labels -- and strictly so whenever the
    'anything else' ranking is imperfect, as here."""
    y = np.array([1, 0, 1, 0, 1, 0, 1, 0], dtype=float)
    imperfect_scores = np.array([3, 7, 1, 5, 8, 2, 6, 4], dtype=float)
    perfect_scores = y.copy()

    worse = empc_literature(y, imperfect_scores)
    better = empc_literature(y, perfect_scores)

    assert better.emp >= worse.emp
    assert better.emp > worse.emp  # strict for this cohort (verified numerically)


def test_emp_harness_better_ranking_never_lower_emp():
    y = np.array([1, 0, 1, 0, 1, 0, 1, 0], dtype=float)
    imperfect_scores = np.array([3, 7, 1, 5, 8, 2, 6, 4], dtype=float)
    perfect_scores = y.copy()
    default_day = np.array([np.nan, np.nan, 10.0, np.nan, 25.0, np.nan, 90.0, np.nan])
    amt = np.array([1000.0, 2000.0, 1500.0, 2500.0, 3000.0, 1200.0, 1800.0, 2200.0])
    econ = LoanEconomics()

    worse = emp_harness(y, imperfect_scores, default_day, amt, econ)
    better = emp_harness(y, perfect_scores, default_day, amt, econ)

    assert better.emp >= worse.emp
    assert better.emp > worse.emp  # strict for this cohort (verified numerically)


# --------------------------------------------------------------------------- #
# 4. Degenerate harness cases, hand-derived from the spec-1 formulas.
# --------------------------------------------------------------------------- #


def test_loss_fractions_all_day_zero():
    """t=0 <= TERM_DAYS: lambda = clip(1 - f - 0, 0, 1) = 1 - f (fee still
    collected even though the borrower defaults immediately)."""
    econ = LoanEconomics()
    y = np.ones(5)
    default_day = np.zeros(5)

    lam = loss_fractions(y, default_day, econ)
    expected = 1.0 - econ.origination_fee_rate
    np.testing.assert_allclose(lam, expected)

    profit = realized_profits(y, default_day, np.full(5, 1000.0), econ)
    np.testing.assert_allclose(profit, 1000.0 * (econ.origination_fee_rate - 1.0))


def test_loss_fractions_all_day_term():
    """t = TERM_DAYS: lambda = clip(-(f + r_term), 0, 1) = 0 (full recovery);
    profit equals the good-loan formula A*(f + r_term) exactly."""
    econ = LoanEconomics()
    y = np.ones(5)
    default_day = np.full(5, float(econ.term_days))

    lam = loss_fractions(y, default_day, econ)
    np.testing.assert_allclose(lam, 0.0)

    amt = np.full(5, 1000.0)
    profit = realized_profits(y, default_day, amt, econ)
    np.testing.assert_allclose(profit, amt * (econ.origination_fee_rate + econ.r_term))


def test_loss_fractions_all_day_ninety_empty_body_fallback():
    """All defaulters past TERM_DAYS (the day-90 mass) with an EMPTY body in
    this call's own rows: decision-5 fallback is lambda = 1 (full loss), so
    profit = -A."""
    econ = LoanEconomics()
    y = np.ones(5)
    default_day = np.full(5, 90.0)

    lam = loss_fractions(y, default_day, econ)
    np.testing.assert_allclose(lam, 1.0)

    amt = np.array([1000.0, 2000.0, 500.0, 1500.0, 2500.0])
    profit = realized_profits(y, default_day, amt, econ)
    np.testing.assert_allclose(profit, -amt)


def test_loss_fractions_day_ninety_uses_mean_of_nonempty_body():
    """Mixed body + tail: the tail rows are priced at the mean of THIS call's
    body lambdas, not a global constant."""
    econ = LoanEconomics()
    y = np.array([1.0, 1.0, 1.0])
    default_day = np.array([0.0, econ.term_days, 90.0])  # body: t=0 and t=term

    lam = loss_fractions(y, default_day, econ)
    body_mean = np.mean([1.0 - econ.origination_fee_rate, 0.0])
    np.testing.assert_allclose(lam, [1.0 - econ.origination_fee_rate, 0.0, body_mean])


def test_loss_fractions_goods_are_nan():
    econ = LoanEconomics()
    y = np.array([0.0, 1.0, 0.0])
    default_day = np.array([np.nan, 30.0, np.nan])
    lam = loss_fractions(y, default_day, econ)
    assert np.isnan(lam[0]) and np.isnan(lam[2])
    assert not np.isnan(lam[1])


# --------------------------------------------------------------------------- #
# 5. emp_harness vs brute-force cutoff scan; optimal_fraction direction.
# --------------------------------------------------------------------------- #


def test_emp_harness_agrees_with_brute_force_cutoff_scan():
    y = np.array([0, 1, 0, 1, 1, 0, 0, 1, 0, 1, 0, 0], dtype=float)
    default_day = np.array(
        [np.nan, 5.0, np.nan, 55.0, 90.0, np.nan, np.nan, 20.0, np.nan, 60.0, np.nan, np.nan]
    )
    amt = np.array(
        [1200, 800, 2200, 1700, 900, 3100, 1400, 2600, 1900, 2100, 1300, 2000], dtype=float
    )
    scores = np.array([0.4, 0.9, 0.1, 0.7, 0.95, 0.3, 0.2, 0.85, 0.5, 0.75, 0.15, 0.35])
    econ = LoanEconomics()

    result = emp_harness(y, scores, default_day, amt, econ)

    n = len(y)
    profits = realized_profits(y, default_day, amt, econ)
    order = np.argsort(scores, kind="stable")
    sorted_profits = profits[order]
    mean_a = amt.mean()

    best_total = None
    best_s = None
    for s in range(n + 1):
        total = float(np.sum(sorted_profits[:s]))
        if best_total is None or total > best_total:
            best_total = total
            best_s = s

    assert result.n == n
    assert result.emp == pytest.approx(best_total / (n * mean_a))
    assert result.optimal_fraction == pytest.approx(best_s / n)


def test_emp_harness_perfect_classifier_low_base_rate_approves_most():
    """A perfect ranking at a low base rate should approve most of the
    population (reject only the true defaulters) -- optimal_fraction > 0.5."""
    n = 40
    y = np.zeros(n)
    y[3] = 1.0
    y[27] = 1.0  # 2/40 = 5% base rate
    default_day = np.where(y == 1, np.array([10.0] * n), np.nan)
    # deterministic non-uniform amounts, no RNG: a simple linear-congruential
    # style formula so the cohort is not trivially uniform.
    amt = np.array([500.0 + ((137 * i + 53) % 4500) for i in range(n)])
    scores = y.copy()  # perfect separation, ties within class

    econ = LoanEconomics()
    result = emp_harness(y, scores, default_day, amt, econ)

    assert result.optimal_fraction > 0.5
    assert result.n == n


# --------------------------------------------------------------------------- #
# 6. Cross-process float determinism.
# --------------------------------------------------------------------------- #

_DETERMINISM_SNIPPET = """
import numpy as np
from cldd.emp import empc_literature, emp_harness, LoanEconomics

y = np.array([1, 0, 1, 1, 0, 0, 1, 0], dtype=float)
scores = np.array([6.0, 5.0, 4.0, 3.0, 2.0, 1.0, 7.0, 0.5])
r = empc_literature(y, scores)

default_day = np.array([10.0, np.nan, 40.0, 90.0, np.nan, np.nan, 55.0, np.nan])
amt = np.array([1000.0, 2000.0, 1500.0, 2500.0, 1200.0, 1800.0, 2100.0, 1300.0])
h = emp_harness(y, scores, default_day, amt, LoanEconomics())

payload = repr((r.emp, r.optimal_fraction, r.n, h.emp, h.optimal_fraction, h.n))
import hashlib
print(hashlib.sha256(payload.encode("utf-8")).hexdigest())
"""


def _compute_reference_hash() -> str:
    import numpy as _np

    from cldd.emp import LoanEconomics as _LoanEconomics
    from cldd.emp import emp_harness as _emp_harness
    from cldd.emp import empc_literature as _empc_literature

    y = _np.array([1, 0, 1, 1, 0, 0, 1, 0], dtype=float)
    scores = _np.array([6.0, 5.0, 4.0, 3.0, 2.0, 1.0, 7.0, 0.5])
    r = _empc_literature(y, scores)

    default_day = _np.array([10.0, _np.nan, 40.0, 90.0, _np.nan, _np.nan, 55.0, _np.nan])
    amt = _np.array([1000.0, 2000.0, 1500.0, 2500.0, 1200.0, 1800.0, 2100.0, 1300.0])
    h = _emp_harness(y, scores, default_day, amt, _LoanEconomics())

    payload = repr((r.emp, r.optimal_fraction, r.n, h.emp, h.optimal_fraction, h.n))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def test_cross_process_float_determinism():
    """The sha256 of a serialized (EMPResult, EMPResult) pair, recomputed in a
    fresh subprocess, matches an in-process recomputation exactly -- no
    RNG/platform-order float drift anywhere in the module."""
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
# 7. Degenerate EMPResult contract.
# --------------------------------------------------------------------------- #


def test_empc_single_class_returns_nan_result():
    all_defaults = empc_literature(np.array([1.0, 1.0, 1.0]), np.array([1.0, 2.0, 3.0]))
    all_goods = empc_literature(np.array([0.0, 0.0, 0.0]), np.array([1.0, 2.0, 3.0]))

    for result, n in ((all_defaults, 3), (all_goods, 3)):
        assert np.isnan(result.emp)
        assert np.isnan(result.optimal_fraction)
        assert result.n == n


def test_empc_empty_input_returns_nan_result():
    result = empc_literature(np.array([]), np.array([]))
    assert np.isnan(result.emp)
    assert np.isnan(result.optimal_fraction)
    assert result.n == 0


def test_emp_harness_none_without_default_day():
    y = np.array([1.0, 0.0, 1.0])
    scores = np.array([0.9, 0.1, 0.8])
    amt = np.array([1000.0, 2000.0, 1500.0])
    assert emp_harness(y, scores, None, amt) is None


def test_emp_harness_empty_input_returns_nan_result():
    result = emp_harness(np.array([]), np.array([]), np.array([]), np.array([]))
    assert isinstance(result, EMPResult)
    assert np.isnan(result.emp)
    assert np.isnan(result.optimal_fraction)
    assert result.n == 0


# --------------------------------------------------------------------------- #
# Sanity: params/economics default from config (single source of truth).
# --------------------------------------------------------------------------- #


def test_empc_params_and_loan_economics_default_from_config():
    params = EMPCParams()
    assert params.p0 == config.EMPC_P0
    assert params.p1 == config.EMPC_P1
    assert params.roi == config.EMPC_ROI

    econ = LoanEconomics()
    assert econ.term_days == config.TERM_DAYS
    assert econ.apr == config.APR
    assert econ.origination_fee_rate == config.ORIGINATION_FEE_RATE
    assert econ.r_term == pytest.approx(config.APR * config.TERM_DAYS / 365.0)
