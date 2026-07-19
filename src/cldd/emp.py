"""Expected-maximum-profit (EMP) reporting layer — the v2 measurement axis.

Prices the frontier the loop already measures; **never** a loop-control input
(spec: ``docs/superpowers/specs/2026-07-13-cldd-v2-emp-design.md``). Two
variants, side by side:

* :func:`empc_literature` — the Verbraken/Bravo/Weber/Baesens EMPC closed form
  over the ROC convex hull (EJOR 238(2):505-513, Eqs. 13/15), with the
  benchmark-standard prior ``h(lambda)`` and ROI from :mod:`cldd.config`
  (``EMPC_P0/EMPC_P1/EMPC_ROI``). Benchmark-comparable by construction.
* :func:`emp_harness` — the same expectation, but per-defaulter loss fractions
  are derived from the harness's own planted default timing and loan economics
  (``TERM_DAYS``/``APR``/``ORIGINATION_FEE_RATE``). SCM cohorts only: the flat
  generator plants no timing, so :func:`emp_harness` returns ``None`` there.

Both variants report ``emp`` as expected profit per applicant **as a fraction
of mean per-loan exposure** (exposure = ``requested_amount``), so the two
columns are directly comparable. Both consume ``scores`` as a ranking only and
are invariant to strictly monotone transforms.

Reading caveats (documented in README + CSV column notes):

* Planted default timing is **marginally spec-shaped but conditionally
  cosmetic** — independent of features/risk given default status — so harness
  EMP is EMPC with an *empirical* h(lambda), resting on unfitted timing:
  verified experiment, not verified result.
* ``days_to_default`` carries a ~22.5% post-term point mass at day 90 whose
  intra-term payment history the generator does not model; those rows are
  priced at the cohort's **mean body lambda** (defaults with t <= TERM_DAYS),
  a stated deterministic imputation. Fallback when the body is empty:
  lambda = 1.

Pure numpy, zero RNG — no Monte Carlo anywhere; deterministic per cohort.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from . import config

__all__ = [
    "EMPCParams",
    "LoanEconomics",
    "EMPResult",
    "empc_literature",
    "emp_harness",
    "loss_fractions",
    "realized_profits",
    "realized_book_profit",
]


@dataclass(frozen=True)
class EMPCParams:
    """Literature EMPC prior (source-verified constants live in ``config``)."""

    p0: float = config.EMPC_P0
    p1: float = config.EMPC_P1
    roi: float = config.EMPC_ROI


@dataclass(frozen=True)
class LoanEconomics:
    """Loan economics for the harness-derived variant, from ``config``."""

    term_days: int = config.TERM_DAYS
    apr: float = config.APR
    origination_fee_rate: float = config.ORIGINATION_FEE_RATE

    @property
    def r_term(self) -> float:
        """Term finance rate: APR pro-rated over the term."""
        return self.apr * self.term_days / 365.0


@dataclass
class EMPResult:
    """EMP of one score ranking on one (sub)population.

    ``emp`` is expected profit per applicant as a fraction of mean per-loan
    exposure; ``optimal_fraction`` is the fraction of the population the
    EMP-optimal cutoff APPROVES (= 1 - the literature's "fraction rejected").
    """

    emp: float
    optimal_fraction: float
    n: int


def _cross(o: tuple[float, float], a: tuple[float, float], b: tuple[float, float]) -> float:
    """2D cross product of (a-o) x (b-o); >0 = left turn (CCW), <0 = right turn (CW)."""
    return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])


def _roc_hull_vertices(y_true: np.ndarray, scores: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Upper convex hull of the empirical ROC, as (r1, r0) vertex arrays.

    r0_i = fraction of defaulters (cases) flagged at cutoff i (TPR); r1_i = fraction
    of goods flagged (FPR). Vertices are built by sweeping cutoffs from the highest
    score down (rejecting progressively more), grouping tied scores into one step
    so the curve is threshold-well-defined, then taking the upper convex hull —
    the achievable frontier — via a monotone-chain scan. Includes (0,0) and (1,1)
    in the candidate set (spec); either may be dominated and dropped by the hull.
    """
    is_pos = y_true == 1
    n_pos = int(is_pos.sum())
    n_neg = len(y_true) - n_pos

    uniq_desc = np.unique(scores)[::-1]
    r0 = np.empty(uniq_desc.size + 1)
    r1 = np.empty(uniq_desc.size + 1)
    r0[0] = 0.0
    r1[0] = 0.0
    cum_pos = 0
    cum_neg = 0
    for i, s in enumerate(uniq_desc):
        mask = scores == s
        cum_pos += int(np.sum(is_pos & mask))
        cum_neg += int(np.sum(~is_pos & mask))
        r0[i + 1] = cum_pos / n_pos
        r1[i + 1] = cum_neg / n_neg

    # Keep only the last (max-r0) point of each contiguous r1 run: strictly
    # dominated intermediate points (same FPR, lower TPR) can never sit on the
    # upper hull, and de-duplicating first keeps the r1 sequence strictly
    # increasing for the monotone-chain scan below.
    keep = np.empty(r1.size, dtype=bool)
    keep[:-1] = r1[1:] != r1[:-1]
    keep[-1] = True
    r0_d = r0[keep]
    r1_d = r1[keep]

    hull: list[tuple[float, float]] = []
    for x, y in zip(r1_d.tolist(), r0_d.tolist()):
        p = (x, y)
        while len(hull) >= 2 and _cross(hull[-2], hull[-1], p) >= 0:
            hull.pop()
        hull.append(p)

    r1_hull = np.array([p[0] for p in hull])
    r0_hull = np.array([p[1] for p in hull])
    return r1_hull, r0_hull


def empc_literature(
    y_true: np.ndarray,
    scores: np.ndarray,
    params: EMPCParams | None = None,
) -> EMPResult:
    """Verbraken et al. EMPC via the ROC convex hull. Deterministic, no sampling.

    Follows EJOR 238(2):505-513 Eqs. 13/15 exactly (see module docstring and the
    v2 design spec). ``scores`` is consumed as a ranking only (higher = riskier);
    invariant to strictly monotone transforms. Degenerate inputs (empty input or
    a single class present) return ``EMPResult(nan, nan, n)``.
    """
    if params is None:
        params = EMPCParams()
    y_true = np.asarray(y_true, dtype=float)
    scores = np.asarray(scores, dtype=float)
    n = y_true.shape[0]
    if n == 0:
        return EMPResult(float("nan"), float("nan"), n)

    n_pos = int(np.sum(y_true == 1))
    n_neg = n - n_pos
    if n_pos == 0 or n_neg == 0:
        return EMPResult(float("nan"), float("nan"), n)

    pi0 = n_pos / n  # P(default) -- "cases" convention (decision/contract)
    pi1 = 1.0 - pi0

    r1_hull, r0_hull = _roc_hull_vertices(y_true, scores)
    m = r1_hull.size - 1  # number of hull segments; hull has m+1 vertices, 0..m

    dr0 = np.diff(r0_hull)
    dr1 = np.diff(r1_hull)
    lam = np.zeros(m + 1)  # lambda_0 := 0 (Eq13)
    for i in range(m):
        if dr0[i] > 0:
            lam[i + 1] = params.roi * pi1 * dr1[i] / (pi0 * dr0[i])
        else:
            # Zero TPR gain for nonzero FPR gain (only possible on the closing
            # segment of a concave hull): infinite marginal cost.
            lam[i + 1] = np.inf

    # k := max{i | lambda_i < 1}; lambda_0 = 0 always qualifies, so this is safe.
    k = int(np.max(np.where(lam < 1.0)[0]))

    # r0_{k+1}/r1_{k+1} for the Eq15 correction term. If k reaches the last hull
    # index m (every lambda_i, i=0..m, is < 1 -- an edge case for low-pi0/high-ROI
    # inputs), there is no vertex m+1; the natural extension is to hold at the
    # hull's terminal point (1,1), i.e. reuse vertex m.
    kp1 = k + 1 if k + 1 <= m else m
    r0_kp1 = r0_hull[kp1]
    r1_kp1 = r1_hull[kp1]

    mix = 1.0 - params.p0 - params.p1

    total = 0.0
    eta_sum = 0.0
    for i in range(k + 1):
        li = lam[i]
        li1 = 1.0 if i == k else lam[i + 1]  # lambda_{k+1} is capped to 1 (Eq13)
        total += (pi0 * r0_hull[i] / 2.0) * (li1**2 - li**2) - params.roi * pi1 * r1_hull[
            i
        ] * (li1 - li)
        eta_sum += (pi0 * r0_hull[i] + pi1 * r1_hull[i]) * (li1 - li)

    emp = mix * total + params.p1 * (pi0 * r0_kp1 - params.roi * pi1 * r1_kp1)
    eta = mix * eta_sum + params.p1 * (pi0 * r0_kp1 + pi1 * r1_kp1)

    return EMPResult(float(emp), float(1.0 - eta), n)


def loss_fractions(
    y_true: np.ndarray,
    default_day: np.ndarray,
    economics: LoanEconomics | None = None,
) -> np.ndarray:
    """Per-row planted loss fraction lambda for defaulters (NaN for goods).

    Body defaulters (``default_day <= term_days``): lambda is the exact clipped
    formula from the harness economics (spec section 1) -- amount-independent, a
    pure function of ``t``. Tail/day-90 defaulters (``default_day > term_days``):
    priced at this call's own body mean lambda (decision 5), falling back to
    lambda = 1 when the body is empty (e.g. an all-day-90 cohort).
    """
    if economics is None:
        economics = LoanEconomics()
    y_true = np.asarray(y_true, dtype=float)
    default_day = np.asarray(default_day, dtype=float)
    n = y_true.shape[0]

    r_term = economics.r_term
    f = economics.origination_fee_rate
    term = float(economics.term_days)

    is_default = y_true == 1
    body_mask = is_default & (default_day <= term)
    tail_mask = is_default & (default_day > term)

    lam = np.full(n, np.nan)

    if np.any(body_mask):
        t_body = default_day[body_mask]
        lam_body = np.clip(1.0 - f - (t_body / term) * (1.0 + r_term), 0.0, 1.0)
        lam[body_mask] = lam_body
        mean_body_lambda = float(np.mean(lam_body))
    else:
        mean_body_lambda = 1.0  # decision-5 fallback: empty body

    if np.any(tail_mask):
        lam[tail_mask] = mean_body_lambda

    return lam


def realized_profits(
    y_true: np.ndarray,
    default_day: np.ndarray,
    requested_amount: np.ndarray,
    economics: LoanEconomics | None = None,
) -> np.ndarray:
    """Per-row realized profit in dollars if the loan is funded (all rows).

    Good loans and body defaulters use the exact (unclipped) collections formula
    from the harness economics (spec section 1) -- a defaulter who pays through
    to ``t = term_days`` realizes the same profit as a good loan by construction.
    Tail/day-90 defaulters are priced at ``-lambda * A`` using the (already
    clipped, decision-5-imputed) lambda from :func:`loss_fractions`.
    """
    if economics is None:
        economics = LoanEconomics()
    y_true = np.asarray(y_true, dtype=float)
    default_day = np.asarray(default_day, dtype=float)
    requested_amount = np.asarray(requested_amount, dtype=float)
    n = y_true.shape[0]

    r_term = economics.r_term
    f = economics.origination_fee_rate
    term = float(economics.term_days)

    is_default = y_true == 1
    body_mask = is_default & (default_day <= term)
    tail_mask = is_default & (default_day > term)
    good_mask = ~is_default

    profit = np.empty(n, dtype=float)
    profit[good_mask] = requested_amount[good_mask] * (f + r_term)

    if np.any(body_mask):
        t_body = default_day[body_mask]
        profit[body_mask] = requested_amount[body_mask] * (
            f + (t_body / term) * (1.0 + r_term) - 1.0
        )

    if np.any(tail_mask):
        lam = loss_fractions(y_true, default_day, economics)
        profit[tail_mask] = -lam[tail_mask] * requested_amount[tail_mask]

    return profit


def realized_book_profit(
    y_true: np.ndarray,
    default_day: np.ndarray | None,
    requested_amount: np.ndarray,
    funded: np.ndarray,
    economics: LoanEconomics | None = None,
) -> float | None:
    """Realized book P&L of the funded rows, normalized by full-cohort exposure.

    Reuses :func:`realized_profits` priced over the FULL cohort, then sums the
    funded rows -- so day-90 rows take the decision-5 mean-body imputation with
    the mean computed from the *cohort's* body defaulters (lambda = 1 fallback
    when the cohort body is empty, see :func:`loss_fractions`). The basis is a
    planted cohort property, invariant to who funds: pricing on the funded
    slice's own body mean made book P&L non-additive across slices and broke
    the H4 arithmetic identity at the pilot gate (spec Rev 2.1 amendment,
    2026-07-19). Returns ``None`` when timing columns are absent (flat cohorts,
    ``default_day is None``), mirroring :func:`emp_harness`. **SCM-only, like
    everything in v3.**

    Units: total realized profit of funded rows / (n_applicants * mean
    ``requested_amount`` over the FULL cohort, not funded-only) -- profit per
    applicant as a fraction of cohort mean exposure (v2 decision 6 extended);
    the full-cohort denominator keeps arms with different funded counts
    comparable and paired differences well-defined.

    Pure numpy, zero RNG, deterministic.
    """
    if default_day is None:
        return None

    y_true = np.asarray(y_true, dtype=float)
    default_day = np.asarray(default_day, dtype=float)
    requested_amount = np.asarray(requested_amount, dtype=float)
    funded = np.asarray(funded, dtype=bool)
    n = y_true.shape[0]

    mean_a = float(np.mean(requested_amount)) if n > 0 else 0.0
    denom = n * mean_a
    if denom == 0.0:
        return float("nan")

    profits = realized_profits(y_true, default_day, requested_amount, economics)
    return float(np.sum(profits[funded])) / denom


def emp_harness(
    y_true: np.ndarray,
    scores: np.ndarray,
    default_day: np.ndarray | None,
    requested_amount: np.ndarray,
    economics: LoanEconomics | None = None,
) -> EMPResult | None:
    """Harness-derived EMP from planted timing; ``None`` without timing columns.

    Ranks rows safest-first (ascending score, stable sort -- scores are a ranking
    only, never used as probabilities) and finds the approval cutoff that
    maximizes cumulative realized profit, normalized by ``n * mean(requested_
    amount)`` (decision 6). Degenerate empty input returns ``EMPResult(nan, nan,
    n)``; a flat cohort (``default_day is None``) returns ``None``.
    """
    if default_day is None:
        return None

    y_true = np.asarray(y_true, dtype=float)
    scores = np.asarray(scores, dtype=float)
    requested_amount = np.asarray(requested_amount, dtype=float)
    n = y_true.shape[0]
    if n == 0:
        return EMPResult(float("nan"), float("nan"), n)

    profits = realized_profits(y_true, default_day, requested_amount, economics)
    order = np.argsort(scores, kind="stable")  # safest (lowest score) first
    cum_profit = np.concatenate(([0.0], np.cumsum(profits[order])))  # index s = approve s safest

    mean_a = float(np.mean(requested_amount))
    best_s = int(np.argmax(cum_profit))  # first occurrence on ties (np.argmax)
    denom = n * mean_a
    emp = cum_profit[best_s] / denom if denom != 0.0 else float("nan")

    return EMPResult(float(emp), best_s / n, n)
