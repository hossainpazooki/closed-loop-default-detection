"""FeedbackLoop: the model's own approvals create its training data.

Directional assertions were measured before being frozen (scm, n=2000, 4
generations, seed 42 — values inline). Note the diagnostics' in-sample AUC
inflates at n=2000, so generation 0's flag state is not asserted here; the
calibrated-scale behavior is covered in test_diagnostics.
"""

from __future__ import annotations

import numpy as np
import pytest

from cldd import FeedbackLoop


def _run(eps: float, n_generations: int = 4, seed: int = 42):
    return FeedbackLoop(
        selection_severity=0.4,
        n_generations=n_generations,
        exploration_rate=eps,
        generator="scm",
        n_applicants=2000,
        seed=seed,
    ).run()


def test_invalid_params_rejected():
    with pytest.raises(ValueError, match="exploration_rate"):
        FeedbackLoop(exploration_rate=1.0)
    with pytest.raises(ValueError, match="n_generations"):
        FeedbackLoop(n_generations=0)


def test_feedback_deterministic():
    a, b = _run(0.05), _run(0.05)
    assert a.declined_ece_trajectory == b.declined_ece_trajectory
    assert [g.n_explored for g in a.generations] == [g.n_explored for g in b.generations]
    assert [g.funded_default_rate for g in a.generations] == [
        g.funded_default_rate for g in b.generations
    ]


def test_generation_zero_is_prior_policy_then_model():
    res = _run(0.0)
    assert [g.policy for g in res.generations] == ["prior", "model", "model", "model"]
    # Rank-based top-k: the model policy funds EXACTLY the approval-rate volume
    # (the quantile-cutoff formulation overfunded through isotonic ties).
    for g in res.generations:
        assert g.funded_rate == pytest.approx(0.6, abs=0.005)


def test_model_policy_destroys_positivity_observably():
    """From generation 1 the funding rule is a function of the features, so the
    observable diagnostics must flag every model generation (measured min
    propensity AUC 0.957 across both exploration settings; threshold 0.85)."""
    for eps in (0.0, 0.05):
        res = _run(eps)
        for g in res.generations:
            if g.policy == "model":
                assert g.diagnostics.flagged, (eps, g.generation)
                assert g.diagnostics.propensity_auc > 0.9


def test_funded_book_looks_fine_while_blind_spot_underpredicts():
    """The deceptive dynamic: the observable funded book improves on generation 1
    (0.0483 vs 0.0883 measured) while the planted-truth under-prediction on the
    model's own declines GROWS (+0.1924 vs +0.1130). Real monitoring sees only
    the first number."""
    res = _run(0.0)
    gen0, gen1 = res.generations[0], res.generations[1]
    assert gen1.funded_default_rate < gen0.funded_default_rate
    gap0 = gen0.metrics.declined_base_rate - gen0.metrics.declined_mean_pd
    gap1 = gen1.metrics.declined_base_rate - gen1.metrics.declined_mean_pd
    assert gap1 > gap0 > 0
    # And the blind spot persists across all model generations on average
    # (measured mean gap +0.0996 over generations 1-3).
    gaps = [
        g.metrics.declined_base_rate - g.metrics.declined_mean_pd
        for g in res.generations
        if g.policy == "model"
    ]
    assert float(np.mean(gaps)) > 0.03


def test_exploration_stabilizes_blind_spot_bias():
    """A 5% random-approval budget cuts the mean blind-spot under-prediction
    across model generations (measured +0.0996 -> +0.0210). It does NOT reliably
    improve declined-ECE at this scale — that is exploration sampling variance,
    and the docs state it — so only the bias reduction is asserted."""

    def mean_gap(res):
        return float(
            np.mean(
                [
                    g.metrics.declined_base_rate - g.metrics.declined_mean_pd
                    for g in res.generations
                    if g.policy == "model"
                ]
            )
        )

    assert mean_gap(_run(0.05)) < mean_gap(_run(0.0)) / 2


def test_explored_labels_are_bought_every_generation():
    res = _run(0.05)
    for g in res.generations:
        assert g.n_explored > 0
        assert 0 <= g.explored_defaults <= g.n_explored
