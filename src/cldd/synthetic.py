"""Synthetic SMB applicant cohort generator with planted default ground truth.

This is the **generate** stage of the closed loop: it plants a true
``default_flag`` for *every* applicant and then hides the labels through a
prior-underwriter approval policy — exactly the **selective-labels** structure
of the Intuit SMB challenge.

Two ground-truth facts are planted and known only to the harness:

1. ``true_default`` — sampled for **all** applicants from a latent risk model
   that is a known function of the observed features *plus a small unobserved
   confounder*. This is the truth a real lender never sees for the declines.
2. ``approved`` — the prior policy funds the lowest-risk ``approval_rate``
   fraction by a *selection score*. ``selection_severity`` controls how tightly
   that score tracks true risk:

   * ``severity = 0`` — approval is independent of true risk (selection at
     random; declines and approvals share the same default distribution).
   * ``severity = 1`` — approval tracks the full latent risk, *including the
     unobserved confounder*, so the declined pool is the high-risk tail and part
     of the selection is invisible to any observed-feature propensity model.

Severity is the corruption axis the loop escalates to find the model's operating
frontier — "selection regimes real data cannot probe". All randomness flows
through one seeded ``numpy.random.Generator`` for byte-identical reproducibility.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from . import config

#: Observed feature columns exposed to the PD model. A realistic subset of the
#: challenge's 44-column schema — enough to be credible, not exhaustive. Bank-feed
#: columns are NaN when the applicant did not link a feed (structural missingness
#: is itself signal).
FEATURE_COLUMNS = [
    "stated_annual_revenue",
    "requested_amount",
    "vintage_years",
    "aggregate_credit_utilization",
    "existing_debt_obligations",
    "recent_inquiries_count_6mo",
    "prior_loans_count",
    "prior_loans_default_count",
    "has_linked_bank_feed",
    "observed_monthly_revenue_avg_3mo",  # bank-feed gated
    "observed_overdraft_count_3mo",      # bank-feed gated
    "payroll_regularity_score",          # bank-feed gated
]

#: Columns that are null exactly when ``has_linked_bank_feed`` is False.
BANK_FEED_COLUMNS = [
    "observed_monthly_revenue_avg_3mo",
    "observed_overdraft_count_3mo",
    "payroll_regularity_score",
]


def _zscore(x: np.ndarray) -> np.ndarray:
    """NaN-aware standardization; missing entries contribute 0 to the latent risk."""
    x = np.asarray(x, dtype=float)
    mean = np.nanmean(x)
    std = np.nanstd(x)
    if not np.isfinite(std) or std == 0:
        std = 1.0
    z = (x - mean) / std
    return np.nan_to_num(z, nan=0.0)


class SyntheticBorrowerGenerator:
    """Generate a synthetic SMB applicant cohort with planted default ground truth."""

    def __init__(
        self,
        n_applicants: int = config.DEFAULT_N_APPLICANTS,
        selection_severity: float = 0.0,
        approval_rate: float = config.DEFAULT_APPROVAL_RATE,
        target_base_rate: float = config.TARGET_BASE_DEFAULT_RATE,
        bank_feed_rate: float = 0.64,
        unobserved_strength: float = 0.7,
        seed: int = config.RANDOM_SEED,
    ) -> None:
        if not 0.0 <= selection_severity <= 1.0:
            raise ValueError(f"selection_severity must be in [0, 1]; got {selection_severity}")
        if not 0.0 < approval_rate < 1.0:
            raise ValueError(f"approval_rate must be in (0, 1); got {approval_rate}")
        self.n_applicants = n_applicants
        self.selection_severity = selection_severity
        self.approval_rate = approval_rate
        self.target_base_rate = target_base_rate
        self.bank_feed_rate = bank_feed_rate
        self.unobserved_strength = unobserved_strength
        self.seed = seed
        self.rng = np.random.Generator(np.random.PCG64(seed))

    # ------------------------------------------------------------------ #
    # Presets
    # ------------------------------------------------------------------ #

    @classmethod
    def unit(cls, seed: int = config.RANDOM_SEED, **kwargs) -> "SyntheticBorrowerGenerator":
        return cls(n_applicants=1500, seed=seed, **kwargs)

    @classmethod
    def benchmark(cls, seed: int = config.RANDOM_SEED, **kwargs) -> "SyntheticBorrowerGenerator":
        return cls(n_applicants=8000, seed=seed, **kwargs)

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #

    def generate_cohort(self) -> dict:
        """Return one cohort dict with features + planted ground truth.

        Keys
        ----
        features : pd.DataFrame
            Observed model matrix (``FEATURE_COLUMNS``), NaN for unlinked feeds.
        true_default : np.ndarray[int]
            Planted default outcome for **all** applicants (the hidden truth).
        approved : np.ndarray[bool]
            Prior-policy funding mask; outcomes are observable only here.
        prior_score : np.ndarray[float]
            The selection score (lower = safer = funded first).
        ground_truth : dict
            severity / base_rate / approval_rate / seed / n_applicants.
        """
        features = self._draw_features()
        latent_risk = self._latent_risk(features)  # includes unobserved confounder
        true_default = (self.rng.random(self.n_applicants) < _sigmoid(latent_risk)).astype(int)
        approved, prior_score = self._apply_selection(latent_risk)

        return {
            "features": features,
            "true_default": true_default,
            "approved": approved,
            "prior_score": prior_score,
            "ground_truth": {
                "selection_severity": self.selection_severity,
                "base_rate": float(true_default.mean()),
                "approval_rate": float(approved.mean()),
                "seed": self.seed,
                "n_applicants": self.n_applicants,
            },
        }

    # ------------------------------------------------------------------ #
    # Internals
    # ------------------------------------------------------------------ #

    def _draw_features(self) -> pd.DataFrame:
        rng = self.rng
        n = self.n_applicants

        stated_annual_revenue = rng.lognormal(mean=12.4, sigma=0.7, size=n)        # ~$240k median
        requested_amount = np.clip(rng.lognormal(mean=9.7, sigma=0.55, size=n), 5_000, 50_000)
        vintage_years = rng.gamma(shape=2.0, scale=2.5, size=n)
        aggregate_credit_utilization = np.clip(rng.beta(2.0, 3.0, size=n), 0.0, 1.0)
        existing_debt_obligations = rng.lognormal(mean=10.5, sigma=0.9, size=n)
        recent_inquiries_count_6mo = rng.poisson(lam=1.8, size=n)
        prior_loans_count = rng.poisson(lam=1.2, size=n)
        # Defaults among prior loans rise with utilization (latent link to risk).
        prior_default_p = np.clip(0.10 + 0.25 * aggregate_credit_utilization, 0.0, 1.0)
        prior_loans_default_count = rng.binomial(np.maximum(prior_loans_count, 0), prior_default_p)

        has_feed = rng.random(n) < self.bank_feed_rate
        observed_monthly_revenue_avg_3mo = stated_annual_revenue / 12.0 * rng.lognormal(0.0, 0.15, size=n)
        observed_overdraft_count_3mo = rng.poisson(lam=0.8, size=n).astype(float)
        payroll_regularity_score = np.clip(rng.beta(5.0, 2.0, size=n), 0.0, 1.0)

        df = pd.DataFrame(
            {
                "stated_annual_revenue": stated_annual_revenue,
                "requested_amount": requested_amount,
                "vintage_years": vintage_years,
                "aggregate_credit_utilization": aggregate_credit_utilization,
                "existing_debt_obligations": existing_debt_obligations,
                "recent_inquiries_count_6mo": recent_inquiries_count_6mo.astype(float),
                "prior_loans_count": prior_loans_count.astype(float),
                "prior_loans_default_count": prior_loans_default_count.astype(float),
                "has_linked_bank_feed": has_feed.astype(float),
                "observed_monthly_revenue_avg_3mo": observed_monthly_revenue_avg_3mo,
                "observed_overdraft_count_3mo": observed_overdraft_count_3mo,
                "payroll_regularity_score": payroll_regularity_score,
            },
            columns=FEATURE_COLUMNS,
        )

        # Structural missingness: bank-feed signals are null without a linked feed.
        df.loc[~has_feed, BANK_FEED_COLUMNS] = np.nan
        return df

    def _latent_risk(self, df: pd.DataFrame) -> np.ndarray:
        """Known logistic risk function over observed features + an unobserved confounder."""
        debt_to_revenue = df["existing_debt_obligations"].to_numpy() / np.maximum(
            df["stated_annual_revenue"].to_numpy(), 1.0
        )
        prior_default_rate = df["prior_loans_default_count"].to_numpy() / (
            df["prior_loans_count"].to_numpy() + 1.0
        )
        has_feed = df["has_linked_bank_feed"].to_numpy() > 0.5

        # Unobserved confounder: drives true risk AND (at high severity) selection,
        # but is never exposed to the PD model — this is what bounds the frontier.
        u = self.rng.standard_normal(self.n_applicants)

        logit = (
            +0.60 * _zscore(df["aggregate_credit_utilization"].to_numpy())
            + 0.50 * _zscore(debt_to_revenue)
            + 0.40 * _zscore(df["recent_inquiries_count_6mo"].to_numpy())
            + 0.40 * _zscore(df["observed_overdraft_count_3mo"].to_numpy())
            + 0.50 * _zscore(prior_default_rate)
            - 0.40 * _zscore(df["payroll_regularity_score"].to_numpy())
            - 0.30 * _zscore(np.log(df["stated_annual_revenue"].to_numpy()))
            - 0.30 * _zscore(df["vintage_years"].to_numpy())
            + 0.20 * (~has_feed).astype(float)  # no feed => slightly riskier (signal)
            + self.unobserved_strength * u
        )
        # Shift the intercept so the planted base rate lands near the target.
        logit += _solve_intercept(logit, self.target_base_rate)
        return logit

    def _apply_selection(self, latent_risk: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        """Fund the lowest-risk ``approval_rate`` fraction by a severity-blended score.

        ``prior_score`` blends standardized true latent risk with independent
        noise: at severity 0 it is pure noise (random selection), at severity 1 it
        is the full latent risk (tightest selection, partly on the unobservable).
        """
        sev = self.selection_severity
        noise = self.rng.standard_normal(self.n_applicants)
        prior_score = sev * _zscore(latent_risk) + (1.0 - sev) * noise  # lower == safer
        cutoff = np.quantile(prior_score, self.approval_rate)
        approved = prior_score <= cutoff
        return approved, prior_score


def _sigmoid(x: np.ndarray) -> np.ndarray:
    return 1.0 / (1.0 + np.exp(-x))


def _solve_intercept(logit_no_intercept: np.ndarray, target_rate: float) -> float:
    """Bisection for the intercept ``c`` s.t. ``mean(sigmoid(logit + c)) == target``."""
    lo, hi = -10.0, 10.0
    for _ in range(60):
        mid = 0.5 * (lo + hi)
        rate = float(np.mean(_sigmoid(logit_no_intercept + mid)))
        if rate < target_rate:
            lo = mid
        else:
            hi = mid
    return 0.5 * (lo + hi)
