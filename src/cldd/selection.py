"""Segmented prior-approval policies (Option C).

The generators' default prior policy is ONE global rule: fund the lowest
``approval_rate`` fraction of a severity-blended score. Real underwriting is
structured -- minimum time in business, utilization caps, per-segment volume
targets -- so whole regions of the OBSERVED feature space can be funded at a
different rate, or not at all.

A :class:`SegmentedSelection` splits the cohort into equal-mass segments by the
rank of one observed feature and funds each segment at its own rate, using the
generator's existing score inside each segment. It consumes no randomness: for
a given seed the features, the planted defaults and the selection score are
byte-identical with or without a policy -- only the funding mask moves.

``rates[0]`` applies to the segment at ``knockout_end`` of the feature
(``"low"`` = smallest values, ``"high"`` = largest). A rate of 0.0 is a hard
knockout: that segment's declines have no funded counterpart at all, a pure
positivity violation in an observable, with nothing hidden.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

__all__ = [
    "KNOCKOUT_ENDS",
    "SegmentedSelection",
    "knockout_rates",
    "segment_index",
    "apply_segmented",
    "validate_policy",
]

#: Which end of the segment feature ``rates[0]`` applies to.
KNOCKOUT_ENDS = ("low", "high")

#: Tolerance on "the policy preserves the overall approval rate".
RATE_TOLERANCE = 1e-9


@dataclass(frozen=True)
class SegmentedSelection:
    """Per-segment funding rates over equal-mass bins of one observed feature."""

    feature: str
    rates: tuple[float, ...]
    knockout_end: str = "low"

    def __post_init__(self) -> None:
        rates = tuple(float(r) for r in self.rates)
        object.__setattr__(self, "rates", rates)
        if len(rates) < 2:
            raise ValueError(f"rates needs at least 2 segments; got {len(rates)}")
        if any(not 0.0 <= r <= 1.0 for r in rates):
            raise ValueError(f"every rate must be in [0, 1]; got {rates}")
        if self.knockout_end not in KNOCKOUT_ENDS:
            raise ValueError(
                f"knockout_end must be one of {KNOCKOUT_ENDS}; got {self.knockout_end!r}"
            )

    @property
    def n_segments(self) -> int:
        return len(self.rates)

    @property
    def mean_rate(self) -> float:
        return float(np.mean(self.rates))

    def as_dict(self) -> dict:
        return {
            "feature": self.feature,
            "rates": list(self.rates),
            "knockout_end": self.knockout_end,
        }


def knockout_rates(depth: float, approval_rate: float, n_segments: int = 5) -> tuple[float, ...]:
    """Rates for a knockout of ``depth`` on segment 0, overall rate preserved.

    Segment 0 is funded at ``approval_rate * (1 - depth)``; the volume it gives
    up is shared equally by the other segments. ``depth = 0`` is the uniform
    policy (every segment at ``approval_rate``); ``depth = 1`` declines segment
    0 outright.
    """
    if not 0.0 <= depth <= 1.0:
        raise ValueError(f"depth must be in [0, 1]; got {depth}")
    if n_segments < 2:
        raise ValueError(f"n_segments must be >= 2; got {n_segments}")
    first = approval_rate * (1.0 - depth)
    rest = approval_rate + approval_rate * depth / (n_segments - 1)
    if rest > 1.0 + RATE_TOLERANCE:
        raise ValueError(
            f"depth {depth} at approval_rate {approval_rate} needs the other "
            f"segments funded at {rest:.4f} > 1"
        )
    return (first,) + (min(rest, 1.0),) * (n_segments - 1)


def validate_policy(
    policy: SegmentedSelection,
    *,
    approval_rate: float,
    allowed_features,
    gated_features,
) -> None:
    """Constructor-time checks shared by both generators. Raises ValueError."""
    if policy.feature not in allowed_features:
        raise ValueError(
            f"selection_policy.feature {policy.feature!r} is not an observed "
            f"feature column of this generator"
        )
    if policy.feature in gated_features:
        raise ValueError(
            f"selection_policy.feature {policy.feature!r} is structurally "
            f"missing without a bank feed; segment on an always-observed column"
        )
    if abs(policy.mean_rate - approval_rate) > RATE_TOLERANCE:
        raise ValueError(
            f"selection_policy mean rate {policy.mean_rate:.6f} != approval_rate "
            f"{approval_rate:.6f}; a policy must preserve the overall funding "
            f"rate (see knockout_rates)"
        )


def segment_index(values, n_segments: int, knockout_end: str = "low") -> np.ndarray:
    """Equal-mass segment id per row, by rank of ``values``.

    Segment 0 holds the ``knockout_end`` of the feature. Ranking uses a stable
    sort, so ties resolve by row order and the result is deterministic.
    """
    vals = np.asarray(values, dtype=float)
    if np.isnan(vals).any():
        raise ValueError("segment feature has missing values; cannot rank")
    if knockout_end not in KNOCKOUT_ENDS:
        raise ValueError(f"knockout_end must be one of {KNOCKOUT_ENDS}; got {knockout_end!r}")
    keyed = vals if knockout_end == "low" else -vals
    order = np.argsort(keyed, kind="stable")
    n = len(vals)
    segment = np.empty(n, dtype=int)
    segment[order] = (np.arange(n) * n_segments) // n
    return segment


def apply_segmented(prior_score, segment, rates) -> np.ndarray:
    """Funding mask: within segment ``k`` fund the lowest ``rates[k]`` fraction."""
    score = np.asarray(prior_score, dtype=float)
    seg = np.asarray(segment)
    approved = np.zeros(len(score), dtype=bool)
    for k, rate in enumerate(rates):
        idx = np.flatnonzero(seg == k)
        if idx.size == 0 or rate <= 0.0:
            continue
        if rate >= 1.0:
            approved[idx] = True
            continue
        cutoff = np.quantile(score[idx], rate)
        approved[idx] = score[idx] <= cutoff
    return approved
