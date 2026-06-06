"""Structural causal model for SMB borrowers with KNOWN-TRUTH counterfactuals.

This is the *causal* upgrade of :mod:`cldd.synthetic`. Where ``synthetic.py``
draws features independently and plants a logistic ``true_default``, this module
implements a **layered structural causal model (SCM)** fitted to the real Intuit
SMB underwriting data, so that the *true* post-intervention default probability of
``do(feature = value)`` is computable by propagating the change through the DAG.

The contract with :class:`cldd.loop.SelectiveLabelsLoop` is preserved: a cohort
dict with keys ``features, true_default, approved, prior_score, ground_truth`` —
so this generator is drop-in for the loop. It adds the counterfactual machinery
(``true_pd``, ``do_intervention``) plus the survival/observation fields.

Design — how known-truth interventions stay exact
--------------------------------------------------
Every node is generated as ``value = F^{-1}(Phi(z))`` where ``z`` is a per-unit
**latent Gaussian** that is a deterministic linear function of its parents'
latents plus a frozen exogenous noise term, and ``F^{-1}`` is the fitted marginal
quantile (Gaussian-copula construction). The exogenous noise draws are frozen on
``generate_cohort`` and stored on the returned :class:`SCMState`. To compute
``do(X = v)`` we:

  1. clamp node ``X``'s realized value to ``v`` (and invert it to a clamped latent
     ``z_X`` so X's *descendants* see the intervention),
  2. re-propagate every descendant of ``X`` through the same structural equations
     with the SAME frozen noise (ancestors and exogenous noise unchanged),
  3. recompute the latent default logit and return ``sigmoid(logit)``.

Because nothing but ``X``'s descendants change and the noise is identical,
``do(X = observed_value)`` reproduces the baseline ``true_pd`` exactly (no-op
invariance). The bank-feed block is a structural switch: toggling
``has_linked_bank_feed`` True regenerates the whole 6-node block from the SCM;
toggling it False deletes it (sets the block to NaN).

All randomness flows through one seeded ``numpy.random.Generator(PCG64(seed))``
for byte-identical reproducibility per seed.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd
from scipy import stats

from . import config

# --------------------------------------------------------------------------- #
# Feature columns (superset of synthetic.FEATURE_COLUMNS; covers all 16
# intervenable features + business_identity roots + prior_underwriter group).
# --------------------------------------------------------------------------- #

#: Observed model matrix exposed to the PD model and the loop. Ordered roots ->
#: self-reported -> bank-feed (gated) -> bureau -> platform -> application ->
#: prior-underwriter. Bank-feed columns are NaN when no feed is linked.
FEATURE_COLUMNS = [
    # business_identity roots
    "sector",
    "geography_region",
    "vintage_years",
    "employee_count_bucket",
    # self_reported (intervenable: stated_annual_revenue, stated_time_in_business, requested_amount)
    "stated_annual_revenue",
    "stated_time_in_business",
    "requested_amount",
    # bank_feed GATED block (all intervenable)
    "has_linked_bank_feed",
    "observed_monthly_revenue_avg_3mo",
    "observed_revenue_trend_3mo",
    "observed_revenue_volatility",
    "observed_cash_balance_p10",
    "observed_overdraft_count_3mo",
    "payroll_regularity_score",
    # bureau_credit (intervenable: aggregate_credit_utilization, recent_inquiries_count_6mo,
    #                existing_debt_obligations, owner_personal_credit_band)
    "aggregate_credit_utilization",
    "recent_inquiries_count_6mo",
    "existing_debt_obligations",
    "owner_personal_credit_band",
    # platform_engagement (intervenable: invoice_payment_delinquency_rate)
    "invoice_payment_delinquency_rate",
    "prior_loans_count",
    "prior_loans_default_count",
    # application_context (intervenable: application_channel, multi_lender_inquiry_count_30d)
    "application_channel",
    "multi_lender_inquiry_count_30d",
    "requested_amount_to_observed_revenue",  # derived
    # prior_underwriter group
    "prior_underwriter_score",
    "prior_decision",
    "prior_approved_amount",
    # derived leverage ratio (exposed; used by the risk logit)
    "debt_to_revenue",
]

#: The 16 intervenable=True features (intervention engine validates against this).
INTERVENABLE_FEATURES = (
    "stated_annual_revenue",
    "stated_time_in_business",
    "requested_amount",
    "observed_monthly_revenue_avg_3mo",
    "observed_revenue_trend_3mo",
    "observed_revenue_volatility",
    "observed_cash_balance_p10",
    "observed_overdraft_count_3mo",
    "payroll_regularity_score",
    "aggregate_credit_utilization",
    "recent_inquiries_count_6mo",
    "existing_debt_obligations",
    "owner_personal_credit_band",
    "invoice_payment_delinquency_rate",
    "application_channel",
    "multi_lender_inquiry_count_30d",
)

#: Columns null exactly when ``has_linked_bank_feed`` is False (structural switch).
BANK_FEED_COLUMNS = (
    "observed_monthly_revenue_avg_3mo",
    "observed_revenue_trend_3mo",
    "observed_revenue_volatility",
    "observed_cash_balance_p10",
    "observed_overdraft_count_3mo",
    "payroll_regularity_score",
)

#: Train [min, max] support per feature, for the in-support counterfactual check.
#: For integer/count features the check compares to [min, max] (not p99) so p99
#: integer-tie ceilings are not flagged as extrapolation (per the query spec).
FEATURE_SUPPORT = {
    "stated_annual_revenue": (156_537.0, 43_500_000.0),
    "stated_time_in_business": (0.033, 40.428),
    "requested_amount": (7_590.0, 45_903.0),
    "observed_monthly_revenue_avg_3mo": (14_996.0, 2_080_000.0),
    "observed_revenue_trend_3mo": (-2.127, 2.799),
    "observed_revenue_volatility": (0.088, 8.157),
    "observed_cash_balance_p10": (-12_373.0, 13_611.0),
    "observed_overdraft_count_3mo": (0.0, 6.0),
    "payroll_regularity_score": (0.0, 1.0),
    "aggregate_credit_utilization": (0.002, 0.993),
    "recent_inquiries_count_6mo": (0.0, 6.0),
    "existing_debt_obligations": (970.0, 69_239.0),
    "owner_personal_credit_band": (0.0, 4.0),
    "invoice_payment_delinquency_rate": (0.003, 0.912),
    "application_channel": (0.0, 2.0),
    "multi_lender_inquiry_count_30d": (0.0, 5.0),
    "vintage_years": (0.0, 60.0),
    "existing_debt_obligations_": (970.0, 69_239.0),
}

_NUMERIC_NOOP_TOL = lambda v: 1e-6 + 1e-3 * abs(float(v))  # noqa: E731 (query-spec tolerance)


# --------------------------------------------------------------------------- #
# Fitted marginal quantile transforms: u in (0,1) -> feature value.
# Each verified vs real median/p99 in the marginals spec.
# --------------------------------------------------------------------------- #


def _q_lognormal(u, mu, sigma):
    return np.exp(mu + sigma * stats.norm.ppf(u))


def _q_normal(u, mu, sigma, lo=None, hi=None):
    x = mu + sigma * stats.norm.ppf(u)
    if lo is not None:
        x = np.maximum(x, lo)
    if hi is not None:
        x = np.minimum(x, hi)
    return x


def _q_gamma(u, a, scale, lo=None):
    x = stats.gamma.ppf(u, a, scale=scale)
    if lo is not None:
        x = np.maximum(x, lo)
    return x


def _q_beta(u, a, b):
    return stats.beta.ppf(u, a, b)


def _q_poisson(u, lam):
    return stats.poisson.ppf(np.clip(u, 1e-9, 1 - 1e-9), lam).astype(float)


def _q_categorical(u, probs):
    """Inverse-CDF for an integer-coded categorical with level probs ``probs``."""
    edges = np.cumsum(np.asarray(probs, dtype=float))
    edges[-1] = 1.0 + 1e-9
    return np.searchsorted(edges, np.asarray(u), side="right").astype(float)


def _sigmoid(x):
    return 1.0 / (1.0 + np.exp(-x))


def _solve_intercept(logit_no_intercept: np.ndarray, target_rate: float) -> float:
    """Bisection for the intercept ``c`` s.t. ``mean(sigmoid(logit + c)) == target``."""
    lo, hi = -12.0, 12.0
    for _ in range(80):
        mid = 0.5 * (lo + hi)
        rate = float(np.mean(_sigmoid(logit_no_intercept + mid)))
        if rate < target_rate:
            lo = mid
        else:
            hi = mid
    return 0.5 * (lo + hi)


def _zfix(x, mean, std):
    """Standardize with FIXED (cohort-baseline) mean/std so the risk logit is a
    fixed structural function — interventions move the input, not the scaler."""
    std = std if (np.isfinite(std) and std > 0) else 1.0
    z = (np.asarray(x, dtype=float) - mean) / std
    return np.nan_to_num(z, nan=0.0)


# --------------------------------------------------------------------------- #
# SCM state returned to callers (counterfactual engine reads this).
# --------------------------------------------------------------------------- #


@dataclass
class SCMState:
    """Frozen per-cohort SCM state the counterfactual engine needs.

    ``noise`` holds the per-unit exogenous uniform draws for every node; ``latent``
    holds the realized latent Gaussians; ``values`` holds the realized feature
    arrays (pre-gating, i.e. bank-feed block populated for all units). ``has_feed``
    is the structural switch. ``risk_scaler`` are the FIXED standardization
    params for the default logit so it is a stable structural function.
    """

    n: int
    seed: int
    noise: dict = field(default_factory=dict)        # node -> per-unit U(0,1) ndarray
    latent: dict = field(default_factory=dict)       # node -> per-unit latent Gaussian
    values: dict = field(default_factory=dict)       # node -> per-unit realized value (ungated)
    has_feed: np.ndarray = field(default=None)       # bool ndarray
    risk_scaler: dict = field(default_factory=dict)  # term name -> (mean, std)
    risk_intercept: float = 0.0
    confounder_u: np.ndarray = field(default=None)   # unobserved confounder (frozen)
    generator: "StructuralBorrowerGenerator" = None  # back-reference for do_intervention


@dataclass
class InterventionResult:
    """Return of :meth:`StructuralBorrowerGenerator.do_intervention`."""

    feature: str
    value: float
    true_pd: np.ndarray            # post-intervention true PD, shape (n,)
    baseline_pd: np.ndarray        # pre-intervention true PD, shape (n,)
    effect: np.ndarray             # true_pd - baseline_pd, shape (n,)
    intervenable: bool             # False => engine refuses (non-intervenable feature)
    in_support: bool               # value within train [min, max]
    is_noop: bool                  # value ~= observed (per-unit baseline preserved)
    structural: bool = False       # True => structural (information) switch, e.g.
    #                                has_linked_bank_feed: manipulable but NOT one
    #                                of the 16 policy-intervenable features.
    note: str = ""


class StructuralBorrowerGenerator:
    """Layered, fitted SCM for SMB borrowers with computable counterfactuals.

    Drop-in for :class:`cldd.synthetic.SyntheticBorrowerGenerator` (same cohort
    contract) plus ``true_pd`` / ``do_intervention`` for known-truth interventions.
    """

    def __init__(
        self,
        n_applicants: int = config.DEFAULT_N_APPLICANTS,
        selection_severity: float = 1.0,
        approval_rate: float = config.DEFAULT_APPROVAL_RATE,
        target_base_rate: float = config.TARGET_BASE_DEFAULT_RATE,
        bank_feed_rate: float = 0.643157,
        unobserved_strength: float = 0.55,
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
    # Presets (mirror synthetic.py)
    # ------------------------------------------------------------------ #

    @classmethod
    def unit(cls, seed: int = config.RANDOM_SEED, **kwargs) -> "StructuralBorrowerGenerator":
        return cls(n_applicants=1500, seed=seed, **kwargs)

    @classmethod
    def benchmark(cls, seed: int = config.RANDOM_SEED, **kwargs) -> "StructuralBorrowerGenerator":
        return cls(n_applicants=8000, seed=seed, **kwargs)

    # ------------------------------------------------------------------ #
    # DAG topology accessors (public; for downstream g-computation)
    # ------------------------------------------------------------------ #

    @classmethod
    def dag_children(cls) -> dict[str, list[str]]:
        """Public DAG topology: ``node -> list of its direct child nodes``.

        Derived from the modeled structural edges (``_CHILDREN``). A downstream
        g-computation / standardization estimator can fit each child mechanism
        ``child ~ parents`` without touching private internals. Returns a fresh
        copy with sorted, de-duplicated child lists.
        """
        return {node: sorted(set(children))
                for node, children in cls._CHILDREN.items()}

    @classmethod
    def dag_parents(cls) -> dict[str, list[str]]:
        """Public DAG topology: ``node -> list of its direct parent nodes``.

        Exact inverse of :meth:`dag_children` over the same modeled feature nodes,
        so every child lists the node as a parent (and vice-versa). Nodes with no
        parents map to an empty list.
        """
        parents: dict[str, list[str]] = {node: [] for node in cls._CHILDREN}
        for node, children in cls._CHILDREN.items():
            for child in children:
                parents.setdefault(child, [])
                if node not in parents[child]:
                    parents[child].append(node)
        return {node: sorted(set(ps)) for node, ps in parents.items()}

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #

    def generate_cohort(self) -> dict:
        """Return a cohort dict (SUPERSET of the synthetic contract).

        Keys
        ----
        features : pd.DataFrame[FEATURE_COLUMNS]  (bank-feed cols NaN when no feed)
        true_default : np.ndarray[int]            planted default for ALL units
        approved : np.ndarray[bool]               prior-policy funding mask
        prior_score : np.ndarray[float]           selection score (lower = safer)
        true_pd : np.ndarray[float]               baseline SCM true default prob
        days_to_default : np.ndarray[float]       in [1,90] for defaulters, NaN else
        observation_status : np.ndarray[object]   'matured' if approved else None
        scm_state : SCMState                      frozen SCM state for counterfactuals
        ground_truth : dict                       severity/base_rate/approval_rate/...
        """
        state = self._build_state()
        df = self._assemble_features(state)

        true_pd = self._logit_to_pd(self._risk_logit(state.values, state))
        # Planted realized default uses a frozen per-unit uniform draw.
        default_u = state.noise["__default__"]
        true_default = (default_u < true_pd).astype(int)

        approved, prior_score = self._apply_selection(state, true_pd)
        days_to_default = self._draw_survival(state, true_default)
        observation_status = np.where(approved, "matured", None).astype(object)

        return {
            "features": df,
            "true_default": true_default,
            "approved": approved,
            "prior_score": prior_score,
            "true_pd": true_pd,
            "days_to_default": days_to_default,
            "observation_status": observation_status,
            "scm_state": state,
            "ground_truth": {
                "selection_severity": self.selection_severity,
                "base_rate": float(true_default.mean()),
                "true_pd_mean": float(true_pd.mean()),
                "approval_rate": float(approved.mean()),
                "bank_feed_rate": float(state.has_feed.mean()),
                "seed": self.seed,
                "n_applicants": self.n_applicants,
            },
        }

    def true_pd(self, state: SCMState | None = None) -> np.ndarray:
        """Baseline per-applicant TRUE default probability from the SCM.

        With no ``state`` a fresh cohort is built. Shape ``(n,)`` float in [0,1].
        """
        if state is None:
            state = self._build_state()
        return self._logit_to_pd(self._risk_logit(state.values, state))

    def do_intervention(self, state: SCMState, feature: str, value) -> InterventionResult:
        """TRUE post-intervention default probability of ``do(feature = value)``.

        Propagates ``value`` through the SCM: descendants of ``feature`` are
        regenerated with the SAME frozen noise; ancestors and the unobserved
        confounder are untouched. ``do(feature = observed_value)`` reproduces the
        baseline exactly (per-unit no-op invariance). The bank-feed block is a
        structural switch (toggling ``has_linked_bank_feed`` regenerates/deletes
        the whole block). Returns an :class:`InterventionResult`.

        ``value`` is broadcast to all units (scalar) or used per-unit (length-n
        array). Non-intervenable identity features (``sector``, ``vintage_years``,
        ...) are refused (``intervenable=False``, baseline returned unchanged).
        ``has_linked_bank_feed`` is a *structural* (information) switch: it is NOT
        one of the 16 policy-intervenable features, but it IS manipulable — flipping
        it reveals/hides the 6-node bank-feed block and recomputes the risk logit
        through the existing structural equations (incl. the no-feed risk term).
        Such results carry ``intervenable=False`` and ``structural=True``.
        """
        baseline_pd = self._logit_to_pd(self._risk_logit(state.values, state))

        in_support = self._check_support(feature, value)

        # ---- structural (information) switch: has_linked_bank_feed -------------
        if feature == "has_linked_bank_feed":
            new_has_feed = self._coerce_feed(value, state.n)
            post_pd = self._logit_to_pd(
                self._risk_logit(state.values, state, has_feed=new_has_feed)
            )
            is_noop = bool(np.array_equal(new_has_feed, state.has_feed))
            return InterventionResult(
                feature=feature, value=_scalar(value), true_pd=post_pd,
                baseline_pd=baseline_pd, effect=post_pd - baseline_pd,
                intervenable=False, in_support=in_support, is_noop=is_noop,
                structural=True,
                note="structural bank-feed switch: information node toggled "
                     "(no-feed risk term re-applied; block revealed/hidden)",
            )

        intervenable = feature in INTERVENABLE_FEATURES
        if not intervenable:
            return InterventionResult(
                feature=feature, value=_scalar(value), true_pd=baseline_pd.copy(),
                baseline_pd=baseline_pd, effect=np.zeros_like(baseline_pd),
                intervenable=False, in_support=in_support, is_noop=False,
                note="non-intervenable feature: intervention refused (baseline returned)",
            )

        new_values = self._propagate(state, feature, value)
        post_pd = self._logit_to_pd(self._risk_logit(new_values, state))
        is_noop = bool(np.allclose(post_pd, baseline_pd, atol=1e-12))
        return InterventionResult(
            feature=feature, value=_scalar(value), true_pd=post_pd,
            baseline_pd=baseline_pd, effect=post_pd - baseline_pd,
            intervenable=True, in_support=in_support, is_noop=is_noop,
            note="" if in_support else "value outside train [min,max] (extrapolation)",
        )

    @staticmethod
    def _coerce_feed(value, n: int) -> np.ndarray:
        """Coerce a feed-switch ``value`` (scalar bool/0-1 or length-n array) to a
        boolean ndarray of length ``n`` (truthy => feed linked)."""
        v = np.asarray(value)
        flags = np.broadcast_to(v, (n,)).astype(float)
        return flags > 0.5

    # ------------------------------------------------------------------ #
    # SCM construction: layered latents -> fitted marginals
    # ------------------------------------------------------------------ #

    def _build_state(self) -> SCMState:
        """Sample the full SCM once; freeze noise + realized values on an SCMState."""
        rng = self.rng
        n = self.n_applicants
        st = SCMState(n=n, seed=self.seed, generator=self)
        st.has_feed = rng.random(n) < self.bank_feed_rate

        # ---- exogenous standard-normal noise per node (frozen) ----
        nodes = [
            "sector", "geography_region", "vintage_years", "employee_count_bucket",
            "stated_annual_revenue", "stated_time_in_business", "requested_amount",
            "observed_monthly_revenue_avg_3mo", "observed_revenue_trend_3mo",
            "observed_revenue_volatility", "observed_cash_balance_p10",
            "observed_overdraft_count_3mo", "payroll_regularity_score",
            "aggregate_credit_utilization", "recent_inquiries_count_6mo",
            "existing_debt_obligations", "owner_personal_credit_band",
            "invoice_payment_delinquency_rate", "prior_loans_count",
            "application_channel", "multi_lender_inquiry_count_30d",
            "prior_underwriter_score",
        ]
        for node in nodes:
            st.noise[node] = rng.standard_normal(n)
        # Extra frozen draws (realized-default uniform, survival, prior-loan defaults).
        st.noise["__default__"] = rng.random(n)
        st.noise["__survival_body__"] = rng.random(n)
        st.noise["__survival_mass__"] = rng.random(n)
        st.noise["__prior_default__"] = rng.random(n)
        st.confounder_u = rng.standard_normal(n)

        self._populate_values(st)
        self._fit_risk_scaler(st)
        return st

    # latent helper: latent z = sum(beta_i * parent_latent_i) + sqrt(resid)*noise
    @staticmethod
    def _latent(noise, parents=(), resid_sd=None):
        z = np.zeros_like(noise)
        explained = 0.0
        for beta, pz in parents:
            z = z + beta * pz
            explained += beta * beta  # parents are ~unit-variance latents
        if resid_sd is None:
            resid_sd = np.sqrt(max(1.0 - explained, 1e-6))
        return z + resid_sd * noise

    def _populate_values(self, st: SCMState) -> None:
        """Fill ``st.latent`` and ``st.values`` for every node (ungated block)."""
        L, V, N = st.latent, st.values, st.noise

        # ---------------- business_identity roots (exogenous) ----------------
        L["sector"] = N["sector"]
        V["sector"] = _q_categorical(stats.norm.cdf(L["sector"]),
                                     [.30095, .24858, .20151, .14938, .09958])
        L["geography_region"] = N["geography_region"]
        V["geography_region"] = _q_categorical(stats.norm.cdf(L["geography_region"]),
                                               [.24701, .25337, .25096, .24865])
        L["employee_count_bucket"] = N["employee_count_bucket"]
        V["employee_count_bucket"] = _q_categorical(stats.norm.cdf(L["employee_count_bucket"]),
                                                    [.40014, .29820, .20177, .09989])
        L["vintage_years"] = N["vintage_years"]
        V["vintage_years"] = _q_gamma(stats.norm.cdf(L["vintage_years"]), 2.0033, 2.9799)

        emp = L["employee_count_bucket"]
        vin = L["vintage_years"]
        sec = L["sector"]

        # ---------------- self_reported ----------------
        # stated_annual_revenue <- employee_count_bucket (eta .332)
        L["stated_annual_revenue"] = self._latent(N["stated_annual_revenue"],
                                                  parents=[(0.55, emp)])
        V["stated_annual_revenue"] = _q_lognormal(stats.norm.cdf(L["stated_annual_revenue"]),
                                                  14.444, 0.6137)
        # stated_time_in_business == vintage echoed (r .996)
        L["stated_time_in_business"] = self._latent(N["stated_time_in_business"],
                                                    parents=[(0.996, vin)], resid_sd=0.0894)
        V["stated_time_in_business"] = _q_gamma(stats.norm.cdf(L["stated_time_in_business"]),
                                                2.4615, 2.6006)
        # requested_amount <- sector (eta .183), stated_revenue (confounder r +.635)
        L["requested_amount"] = self._latent(N["requested_amount"],
                                             parents=[(0.30, sec), (0.55, L["stated_annual_revenue"])])
        V["requested_amount"] = _q_normal(stats.norm.cdf(L["requested_amount"]),
                                          24923.5, 6153.0, lo=7590.0)

        # ---------------- bank_feed GATED block ----------------
        # observed_monthly_revenue_avg_3mo <- employee_count_bucket (eta .368),
        #   stated_revenue (r +.917 near-identity)
        L["observed_monthly_revenue_avg_3mo"] = self._latent(
            N["observed_monthly_revenue_avg_3mo"],
            parents=[(0.30, emp), (0.62, L["stated_annual_revenue"])])
        V["observed_monthly_revenue_avg_3mo"] = _q_lognormal(
            stats.norm.cdf(L["observed_monthly_revenue_avg_3mo"]), 11.9729, 0.6063)
        # intra-block covariance: payroll<->cash +.552, cash<->overdraft -.318,
        #   trend<->volatility -.361, payroll<->revenue +.454
        L["payroll_regularity_score"] = self._latent(
            N["payroll_regularity_score"],
            parents=[(0.45, L["observed_monthly_revenue_avg_3mo"])])
        V["payroll_regularity_score"] = _q_beta(
            stats.norm.cdf(L["payroll_regularity_score"]), 2.6766, 2.4943)
        L["observed_cash_balance_p10"] = self._latent(
            N["observed_cash_balance_p10"],
            parents=[(0.55, L["payroll_regularity_score"])])
        V["observed_cash_balance_p10"] = _q_normal(
            stats.norm.cdf(L["observed_cash_balance_p10"]), 459.92, 3038.44)
        L["observed_overdraft_count_3mo"] = self._latent(
            N["observed_overdraft_count_3mo"],
            parents=[(-0.32, L["observed_cash_balance_p10"])])
        V["observed_overdraft_count_3mo"] = _q_poisson(
            stats.norm.cdf(L["observed_overdraft_count_3mo"]), 0.458)
        L["observed_revenue_trend_3mo"] = self._latent(N["observed_revenue_trend_3mo"])
        V["observed_revenue_trend_3mo"] = _q_normal(
            stats.norm.cdf(L["observed_revenue_trend_3mo"]), 0.1508, 0.8218)
        L["observed_revenue_volatility"] = self._latent(
            N["observed_revenue_volatility"],
            parents=[(-0.36, L["observed_revenue_trend_3mo"])])
        V["observed_revenue_volatility"] = _q_lognormal(
            stats.norm.cdf(L["observed_revenue_volatility"]), -0.0178, 0.5407)

        # ---------------- bureau_credit ----------------
        # aggregate_credit_utilization <- employee (eta .210), sector (eta .111),
        #   vintage (r -.291)
        L["aggregate_credit_utilization"] = self._latent(
            N["aggregate_credit_utilization"],
            parents=[(0.21, emp), (0.11, sec), (-0.29, vin)])
        V["aggregate_credit_utilization"] = _q_beta(
            stats.norm.cdf(L["aggregate_credit_utilization"]), 1.7944, 1.7908)
        L["recent_inquiries_count_6mo"] = self._latent(N["recent_inquiries_count_6mo"])
        V["recent_inquiries_count_6mo"] = _q_poisson(
            stats.norm.cdf(L["recent_inquiries_count_6mo"]), 0.6001)
        # existing_debt_obligations <- employee (eta .183)
        L["existing_debt_obligations"] = self._latent(
            N["existing_debt_obligations"], parents=[(0.30, emp)])
        V["existing_debt_obligations"] = _q_lognormal(
            stats.norm.cdf(L["existing_debt_obligations"]), 9.026, 0.51)
        # owner_personal_credit_band <- employee (eta .188); strongest categorical
        L["owner_personal_credit_band"] = self._latent(
            N["owner_personal_credit_band"], parents=[(0.30, emp)])
        V["owner_personal_credit_band"] = _q_categorical(
            stats.norm.cdf(L["owner_personal_credit_band"]),
            [.20207, .20006, .20060, .19943, .19784])

        # ---------------- platform_engagement ----------------
        # invoice_payment_delinquency_rate <- vintage (r -.281), utilization (mediator r +.706)
        L["invoice_payment_delinquency_rate"] = self._latent(
            N["invoice_payment_delinquency_rate"],
            parents=[(-0.28, vin), (0.55, L["aggregate_credit_utilization"])])
        V["invoice_payment_delinquency_rate"] = _q_beta(
            stats.norm.cdf(L["invoice_payment_delinquency_rate"]), 1.6859, 6.0527)
        L["prior_loans_count"] = self._latent(N["prior_loans_count"])
        V["prior_loans_count"] = _q_poisson(stats.norm.cdf(L["prior_loans_count"]), 0.3956)
        # prior_loans_default_count ~ Binomial(count, 0.135); frozen via uniform.
        cnt = V["prior_loans_count"].astype(int)
        V["prior_loans_default_count"] = stats.binom.ppf(
            N["__prior_default__"], np.maximum(cnt, 0), 0.135).astype(float)

        # ---------------- application_context ----------------
        L["application_channel"] = N["application_channel"]
        V["application_channel"] = _q_categorical(
            stats.norm.cdf(L["application_channel"]), [.49764, .35128, .15108])
        L["multi_lender_inquiry_count_30d"] = self._latent(N["multi_lender_inquiry_count_30d"])
        V["multi_lender_inquiry_count_30d"] = _q_poisson(
            stats.norm.cdf(L["multi_lender_inquiry_count_30d"]), 0.4500)

        # ---------------- derived ratios (deterministic) ----------------
        self._recompute_derived(V)

        # ---------------- prior_underwriter (selection) ----------------
        # prior_underwriter_score: U-shaped beta, tilted by risk drivers (propensity).
        L["prior_underwriter_score"] = self._latent(
            N["prior_underwriter_score"],
            parents=[(-0.10, L["aggregate_credit_utilization"]),
                     (-0.10, L["invoice_payment_delinquency_rate"]),
                     (0.10, L["requested_amount"])])
        V["prior_underwriter_score"] = _q_beta(
            stats.norm.cdf(L["prior_underwriter_score"]), 0.3852, 0.3818)
        # prior_decision: hard threshold ~0.273 reproduces 0.606 approve rate.
        V["prior_decision"] = (V["prior_underwriter_score"] >= 0.273).astype(float)
        appr = V["prior_decision"] > 0.5
        prior_approved_amount = _q_gamma(
            stats.norm.cdf(N["requested_amount"]), 15.3714, 1523.73, lo=7590.0)
        prior_approved_amount = np.where(appr, prior_approved_amount, np.nan)
        V["prior_approved_amount"] = prior_approved_amount

    @staticmethod
    def _recompute_derived(V: dict) -> None:
        """Deterministic derived nodes (never independent): ratio + debt-to-revenue."""
        rev_monthly = np.where(np.isfinite(V["observed_monthly_revenue_avg_3mo"]),
                               V["observed_monthly_revenue_avg_3mo"],
                               V["stated_annual_revenue"] / 12.0)
        V["requested_amount_to_observed_revenue"] = V["requested_amount"] / np.maximum(rev_monthly, 1.0)
        V["debt_to_revenue"] = V["existing_debt_obligations"] / np.maximum(V["stated_annual_revenue"], 1.0)

    # ------------------------------------------------------------------ #
    # Default risk logit (the structural outcome equation)
    # ------------------------------------------------------------------ #

    #: Structural coefficients for the latent default logit. Signs + relative
    #: magnitudes match the grounded corr-to-default ranking in the DAG spec.
    _RISK_TERMS = {
        "invoice_payment_delinquency_rate": +1.05,
        "aggregate_credit_utilization": +0.95,
        "observed_cash_balance_p10": -0.95,
        "requested_amount_to_observed_revenue": +0.70,
        "observed_revenue_volatility": +0.60,
        "requested_amount": +0.55,
        "payroll_regularity_score": -0.55,
        "observed_overdraft_count_3mo": +0.50,
        "existing_debt_obligations": +0.40,
        "debt_to_revenue": +0.30,
        "owner_personal_credit_band": -0.30,
        "recent_inquiries_count_6mo": +0.25,
        "vintage_years": -0.25,
        "stated_annual_revenue": -0.13,
    }

    def _fit_risk_scaler(self, st: SCMState) -> None:
        """Freeze per-term (mean,std) on the baseline cohort so the risk logit is a
        stable structural function, then solve the intercept for the base rate."""
        for term in self._RISK_TERMS:
            x = np.asarray(st.values[term], dtype=float)
            x = np.where(np.isfinite(x), x, np.nan)
            st.risk_scaler[term] = (float(np.nanmean(x)), float(np.nanstd(x)))
        logit_no_int = self._risk_logit_raw(st.values, st)
        # Confounder folded in (unobserved): drives true risk; not exposed to model.
        logit_no_int = logit_no_int + self.unobserved_strength * st.confounder_u
        st.risk_intercept = _solve_intercept(logit_no_int, self.target_base_rate)

    def _risk_logit_raw(self, values: dict, st: SCMState, has_feed=None) -> np.ndarray:
        logit = np.zeros(st.n)
        for term, coef in self._RISK_TERMS.items():
            mean, std = st.risk_scaler[term]
            logit = logit + coef * _zfix(values[term], mean, std)
        # No-feed rows are slightly riskier (structural-missingness signal). The
        # feed flag is a structural switch: do(has_linked_bank_feed=...) overrides
        # it so linking/unlinking a feed flips this no-feed term (modest direct,
        # information-only effect) — everything else is unchanged.
        feed = st.has_feed if has_feed is None else has_feed
        logit = logit + 0.20 * (~feed).astype(float)
        return logit

    def _risk_logit(self, values: dict, st: SCMState, has_feed=None) -> np.ndarray:
        return (self._risk_logit_raw(values, st, has_feed=has_feed)
                + self.unobserved_strength * st.confounder_u + st.risk_intercept)

    def _logit_to_pd(self, logit: np.ndarray) -> np.ndarray:
        return np.clip(_sigmoid(logit), 0.0, 1.0)

    # ------------------------------------------------------------------ #
    # Intervention propagation (descendants only; frozen noise)
    # ------------------------------------------------------------------ #

    #: Direct children per node (the DAG edges we propagate along).
    _CHILDREN = {
        "stated_annual_revenue": ["requested_amount", "observed_monthly_revenue_avg_3mo",
                                  "debt_to_revenue", "requested_amount_to_observed_revenue"],
        "requested_amount": ["requested_amount_to_observed_revenue"],
        "observed_monthly_revenue_avg_3mo": ["payroll_regularity_score",
                                             "requested_amount_to_observed_revenue"],
        "payroll_regularity_score": ["observed_cash_balance_p10"],
        "observed_cash_balance_p10": ["observed_overdraft_count_3mo"],
        "observed_revenue_trend_3mo": ["observed_revenue_volatility"],
        "aggregate_credit_utilization": ["invoice_payment_delinquency_rate"],
        "existing_debt_obligations": ["debt_to_revenue"],
        # leaf intervenables (no structural children beyond the risk logit):
        "observed_overdraft_count_3mo": [],
        "observed_revenue_volatility": [],
        "recent_inquiries_count_6mo": [],
        "owner_personal_credit_band": [],
        "invoice_payment_delinquency_rate": [],
        "application_channel": [],
        "multi_lender_inquiry_count_30d": [],
        "stated_time_in_business": [],
    }

    #: Latent-equation parents (beta, parent_node) used to recompute a child's
    #: latent from updated parents — mirrors _populate_values exactly.
    _LATENT_PARENTS = {
        "requested_amount": [(0.30, "sector"), (0.55, "stated_annual_revenue")],
        "observed_monthly_revenue_avg_3mo": [(0.30, "employee_count_bucket"),
                                             (0.62, "stated_annual_revenue")],
        "payroll_regularity_score": [(0.45, "observed_monthly_revenue_avg_3mo")],
        "observed_cash_balance_p10": [(0.55, "payroll_regularity_score")],
        "observed_overdraft_count_3mo": [(-0.32, "observed_cash_balance_p10")],
        "observed_revenue_volatility": [(-0.36, "observed_revenue_trend_3mo")],
        "invoice_payment_delinquency_rate": [(-0.28, "vintage_years"),
                                             (0.55, "aggregate_credit_utilization")],
    }

    #: Marginal quantile transform per node (latent -> value).
    _MARGINAL = {
        "stated_annual_revenue": lambda z: _q_lognormal(stats.norm.cdf(z), 14.444, 0.6137),
        "requested_amount": lambda z: _q_normal(stats.norm.cdf(z), 24923.5, 6153.0, lo=7590.0),
        "observed_monthly_revenue_avg_3mo": lambda z: _q_lognormal(stats.norm.cdf(z), 11.9729, 0.6063),
        "payroll_regularity_score": lambda z: _q_beta(stats.norm.cdf(z), 2.6766, 2.4943),
        "observed_cash_balance_p10": lambda z: _q_normal(stats.norm.cdf(z), 459.92, 3038.44),
        "observed_overdraft_count_3mo": lambda z: _q_poisson(stats.norm.cdf(z), 0.458),
        "observed_revenue_trend_3mo": lambda z: _q_normal(stats.norm.cdf(z), 0.1508, 0.8218),
        "observed_revenue_volatility": lambda z: _q_lognormal(stats.norm.cdf(z), -0.0178, 0.5407),
        "aggregate_credit_utilization": lambda z: _q_beta(stats.norm.cdf(z), 1.7944, 1.7908),
        "recent_inquiries_count_6mo": lambda z: _q_poisson(stats.norm.cdf(z), 0.6001),
        "existing_debt_obligations": lambda z: _q_lognormal(stats.norm.cdf(z), 9.026, 0.51),
        "owner_personal_credit_band": lambda z: _q_categorical(
            stats.norm.cdf(z), [.20207, .20006, .20060, .19943, .19784]),
        "invoice_payment_delinquency_rate": lambda z: _q_beta(stats.norm.cdf(z), 1.6859, 6.0527),
        "application_channel": lambda z: _q_categorical(stats.norm.cdf(z), [.49764, .35128, .15108]),
        "multi_lender_inquiry_count_30d": lambda z: _q_poisson(stats.norm.cdf(z), 0.4500),
        "stated_time_in_business": lambda z: _q_gamma(stats.norm.cdf(z), 2.4615, 2.6006),
    }

    #: Resid SD for child latent recompute (matches _populate_values explained var).
    _RESID_SD = {
        "stated_time_in_business": 0.0894,
    }

    def _child_latent(self, node: str, st: SCMState, L: dict) -> np.ndarray:
        """Recompute node's latent from (possibly updated) parent latents + frozen noise."""
        parents = [(b, L[p]) for b, p in self._LATENT_PARENTS.get(node, [])]
        return self._latent(st.noise[node], parents=parents, resid_sd=self._RESID_SD.get(node))

    def _propagate(self, st: SCMState, feature: str, value) -> dict:
        """Return a NEW values dict for do(feature = value); descendants updated."""
        # The bank-feed structural switch is handled directly in do_intervention
        # (it toggles has_feed and re-applies the no-feed risk term rather than
        # altering any node value), so it never reaches descendant propagation.
        if feature == "has_linked_bank_feed":  # pragma: no cover - guarded upstream
            return dict(st.values)

        L = dict(st.latent)
        V = dict(st.values)

        # Clamp the target value; invert to a clamped latent so descendants react.
        v = np.asarray(value, dtype=float)
        V[feature] = np.broadcast_to(v, (st.n,)).astype(float).copy()
        L[feature] = self._invert_to_latent(feature, V[feature])

        # Breadth-first propagation through descendants in DAG order.
        order = self._descendant_order(feature)
        for node in order:
            if node in ("requested_amount_to_observed_revenue", "debt_to_revenue"):
                continue  # derived, recomputed below
            L[node] = self._child_latent(node, st, L)
            if node in self._MARGINAL:
                V[node] = self._MARGINAL[node](L[node])

        # Derived ratios recomputed from current V (handles both derived children).
        self._recompute_derived(V)
        # Re-apply bank-feed gating for the risk logit: gated nulls don't change
        # because the risk logit uses raw values; gating only affects the emitted
        # DataFrame, not the latent risk (no-feed handled by has_feed flag).
        return V

    def _descendant_order(self, feature: str) -> list[str]:
        """Topologically ordered descendants of ``feature`` (excluding itself)."""
        order: list[str] = []
        seen = set()
        # repeated relaxation along _CHILDREN until closure (DAG, small)
        frontier = list(self._CHILDREN.get(feature, []))
        # Process in a stable layered manner.
        topo = ["stated_annual_revenue", "requested_amount",
                "observed_monthly_revenue_avg_3mo", "payroll_regularity_score",
                "observed_cash_balance_p10", "observed_overdraft_count_3mo",
                "observed_revenue_trend_3mo", "observed_revenue_volatility",
                "aggregate_credit_utilization", "invoice_payment_delinquency_rate",
                "existing_debt_obligations",
                "requested_amount_to_observed_revenue", "debt_to_revenue"]
        # Collect full descendant set.
        desc = set()
        stack = list(self._CHILDREN.get(feature, []))
        while stack:
            c = stack.pop()
            if c in desc:
                continue
            desc.add(c)
            stack.extend(self._CHILDREN.get(c, []))
        for node in topo:
            if node in desc and node not in seen:
                order.append(node)
                seen.add(node)
        return order

    def _invert_to_latent(self, feature: str, value: np.ndarray) -> np.ndarray:
        """Invert a clamped value back to its latent Gaussian (for descendant flow).

        Uses the fitted marginal CDF -> norm.ppf. For discrete/categorical nodes
        the latent is approximate (mid-rank) but only feeds descendant *latents*;
        the clamped value itself is exact in the risk logit.
        """
        u = self._marginal_cdf(feature, value)
        u = np.clip(u, 1e-9, 1 - 1e-9)
        return stats.norm.ppf(u)

    @staticmethod
    def _marginal_cdf(feature: str, value: np.ndarray) -> np.ndarray:
        v = np.asarray(value, dtype=float)
        if feature == "stated_annual_revenue":
            return stats.lognorm.cdf(v, 0.6137, scale=np.exp(14.444))
        if feature == "requested_amount":
            return stats.norm.cdf(v, 24923.5, 6153.0)
        if feature == "observed_monthly_revenue_avg_3mo":
            return stats.lognorm.cdf(v, 0.6063, scale=np.exp(11.9729))
        if feature == "payroll_regularity_score":
            return stats.beta.cdf(v, 2.6766, 2.4943)
        if feature == "observed_cash_balance_p10":
            return stats.norm.cdf(v, 459.92, 3038.44)
        if feature == "observed_overdraft_count_3mo":
            return stats.poisson.cdf(v, 0.458)
        if feature == "observed_revenue_trend_3mo":
            return stats.norm.cdf(v, 0.1508, 0.8218)
        if feature == "observed_revenue_volatility":
            return stats.lognorm.cdf(v, 0.5407, scale=np.exp(-0.0178))
        if feature == "aggregate_credit_utilization":
            return stats.beta.cdf(v, 1.7944, 1.7908)
        if feature == "recent_inquiries_count_6mo":
            return stats.poisson.cdf(v, 0.6001)
        if feature == "existing_debt_obligations":
            return stats.lognorm.cdf(v, 0.51, scale=np.exp(9.026))
        if feature == "owner_personal_credit_band":
            return np.clip((v + 0.5) / 5.0, 1e-6, 1 - 1e-6)
        if feature == "invoice_payment_delinquency_rate":
            return stats.beta.cdf(v, 1.6859, 6.0527)
        if feature == "application_channel":
            return np.clip((v + 0.5) / 3.0, 1e-6, 1 - 1e-6)
        if feature == "multi_lender_inquiry_count_30d":
            return stats.poisson.cdf(v, 0.4500)
        if feature == "stated_time_in_business":
            return stats.gamma.cdf(v, 2.4615, scale=2.6006)
        return np.full_like(v, 0.5)

    def _check_support(self, feature: str, value) -> bool:
        if feature not in FEATURE_SUPPORT:
            return True
        lo, hi = FEATURE_SUPPORT[feature]
        v = np.asarray(value, dtype=float)
        return bool(np.all((v >= lo) & (v <= hi)))

    # ------------------------------------------------------------------ #
    # Feature DataFrame assembly (apply bank-feed gating)
    # ------------------------------------------------------------------ #

    def _assemble_features(self, st: SCMState) -> pd.DataFrame:
        data = {}
        for col in FEATURE_COLUMNS:
            if col == "has_linked_bank_feed":
                data[col] = st.has_feed.astype(float)
            else:
                data[col] = np.asarray(st.values[col], dtype=float)
        df = pd.DataFrame(data, columns=FEATURE_COLUMNS)
        # Structural missingness: bank-feed block null where no feed linked.
        df.loc[~st.has_feed, list(BANK_FEED_COLUMNS)] = np.nan
        return df

    # ------------------------------------------------------------------ #
    # Selection (prior underwriter) + survival
    # ------------------------------------------------------------------ #

    def _apply_selection(self, st: SCMState, true_pd: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        """Fund the lowest-risk ``approval_rate`` fraction.

        ``prior_score`` blends standardized true risk (incl. the unobserved
        confounder) with independent noise per ``selection_severity`` — so the
        loop's frontier escalation still makes sense (sev 0 == random selection,
        sev 1 == approval tracks full latent risk including the unobservable).
        """
        sev = self.selection_severity
        logit = self._risk_logit(st.values, st)  # includes confounder
        z = _zfix(logit, float(np.mean(logit)), float(np.std(logit)))
        noise = st.noise["prior_underwriter_score"]  # frozen independent noise
        prior_score = sev * z + (1.0 - sev) * noise
        cutoff = np.quantile(prior_score, self.approval_rate)
        approved = prior_score <= cutoff
        return approved, prior_score

    def _draw_survival(self, st: SCMState, true_default: np.ndarray) -> np.ndarray:
        """days_to_default in [1,90]: smooth body over [3,60] + point mass at 90.

        Per the survival spec: ~22.5% of defaults land exactly at day 90 (trigger
        3); (60,90) is empty; defaulters only. Non-defaulters -> NaN.
        """
        n = st.n
        days = np.full(n, np.nan)
        is_def = true_default == 1
        body_u = st.noise["__survival_body__"]
        mass_u = st.noise["__survival_mass__"]
        # body: gamma-ish shape over [3,60], median ~37
        body = 3.0 + 57.0 * stats.beta.ppf(np.clip(body_u, 1e-6, 1 - 1e-6), 2.2, 2.3)
        body = np.clip(np.round(body), 3, 60)
        at_90 = mass_u < 0.225
        dd = np.where(at_90, 90.0, body)
        days[is_def] = dd[is_def]
        return days


def dag_children() -> dict[str, list[str]]:
    """Module-level accessor for the SCM DAG topology (``node -> children``).

    Thin wrapper over :meth:`StructuralBorrowerGenerator.dag_children` so a
    downstream estimator can import the topology without instantiating or touching
    private internals: ``from cldd import dag_children``.
    """
    return StructuralBorrowerGenerator.dag_children()


def dag_parents() -> dict[str, list[str]]:
    """Module-level accessor for the SCM DAG topology (``node -> parents``).

    Thin wrapper over :meth:`StructuralBorrowerGenerator.dag_parents`. Consistent
    with :func:`dag_children`: every child lists the node as a parent.
    """
    return StructuralBorrowerGenerator.dag_parents()


def _scalar(value):
    v = np.asarray(value, dtype=float)
    return float(v.reshape(-1)[0]) if v.size else float("nan")
