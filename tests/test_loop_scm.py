"""Loop-on-SCM unification: pluggable generator smoke/determinism/contract tests,
plus a frozen-baseline guard that the default flat path is byte-identical to the
pre-change behavior."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from cldd import SelectiveLabelsLoop, config
from cldd.loop import GENERATORS, RoundResult
from cldd.scm import StructuralBorrowerGenerator


def test_invalid_generator_rejected():
    with pytest.raises(ValueError, match="generator"):
        SelectiveLabelsLoop(generator="nope")


def test_default_generator_is_flat():
    assert SelectiveLabelsLoop().generator == "flat"
    assert GENERATORS == ("flat", "scm")


def test_scm_loop_smoke_one_round():
    """generator="scm" runs end-to-end and returns a coherent RoundResult."""
    loop = SelectiveLabelsLoop(
        generator="scm", improve_mode="both", max_rounds=1, n_applicants=800, seed=42
    )
    result = loop.run()
    assert len(result.rounds) == 1
    r = result.rounds[0]
    assert isinstance(r, RoundResult)
    assert r.selection_severity == config.START_SEVERITY
    # Quantile-cutoff selection funds exactly the configured fraction.
    assert r.approval_rate == pytest.approx(config.DEFAULT_APPROVAL_RATE, abs=0.005)
    # Around the SCM's 0.17 intercept target (small-n tolerance).
    assert 0.10 <= r.base_rate <= 0.25
    for lever in (r.naive, r.reweight, r.retrain):
        assert lever is not None
        assert 0.0 <= lever.declined_ece <= 1.0
        assert 0.0 <= lever.declined_mean_pd <= 1.0
        assert np.isfinite(lever.declined_brier)
    # Control keys on the primary (reweight) lever under improve_mode="both".
    assert r.control_metric == r.reweight.declined_ece


def test_scm_loop_deterministic():
    """Same seed -> identical metrics (all randomness via one PCG64 per cohort)."""

    def run():
        return SelectiveLabelsLoop(
            generator="scm", improve_mode="both", max_rounds=2, n_applicants=800, seed=7
        ).run()

    a, b = run(), run()
    assert a.frontier_severity == b.frontier_severity
    assert len(a.rounds) == len(b.rounds)
    assert [r.control_metric for r in a.rounds] == [r.control_metric for r in b.rounds]
    assert [r.naive.declined_ece for r in a.rounds] == [r.naive.declined_ece for r in b.rounds]
    assert [r.retrain.declined_ece for r in a.rounds] == [r.retrain.declined_ece for r in b.rounds]


def test_scm_retrain_seed_disjoint():
    """The no-leakage TRAIN_SEED_OFFSET discipline carries over to the SCM path."""
    loop = SelectiveLabelsLoop(
        generator="scm", improve_mode="retrain", max_rounds=1, n_applicants=600, seed=42
    )
    result = loop.run()
    r = result.rounds[0]
    assert r.retrain_train_seed == loop.seed + config.TRAIN_SEED_OFFSET + r.iteration
    assert r.retrain_train_seed != loop.seed + r.iteration


def test_scm_cohort_satisfies_loop_contract():
    """Every key/dtype the loop, eval_default, and model_pd consume from a cohort."""
    n = 600
    cohort = StructuralBorrowerGenerator(
        n_applicants=n,
        selection_severity=0.4,
        approval_rate=0.6,
        seed=3,
        independent_selection_noise=True,
    ).generate_cohort()

    # loop._measure_reweight / eval_default: all-float-coercible feature frame.
    X = cohort["features"].to_numpy(dtype=float)
    assert X.shape[0] == n and X.ndim == 2

    # eval_default: boolean ndarray (negation ~approved must be logical, and
    # true_default[approved] is a numpy fancy-index).
    approved = cohort["approved"]
    assert isinstance(approved, np.ndarray) and approved.dtype == np.bool_
    declined = ~approved
    assert int(approved.sum() + declined.sum()) == n

    # model_pd.train_pd_model: non-negative int labels for np.bincount.
    y = cohort["true_default"]
    assert isinstance(y, np.ndarray) and y.dtype.kind == "i"
    assert set(np.unique(y)) <= {0, 1}
    assert y[approved].shape == (int(approved.sum()),)

    # loop.run: ground_truth must expose base_rate and approval_rate.
    gt = cohort["ground_truth"]
    assert gt["approval_rate"] == pytest.approx(0.6, abs=0.005)
    assert 0.0 <= gt["base_rate"] <= 1.0


def test_independent_selection_noise_gated_off_default_path():
    """The dedicated selection draw must not perturb the fidelity-gated default
    path: features/labels stay byte-identical, only the selection itself moves."""
    kw = dict(n_applicants=500, selection_severity=0.0, approval_rate=0.6, seed=11)
    base = StructuralBorrowerGenerator(**kw).generate_cohort()
    indep = StructuralBorrowerGenerator(**kw, independent_selection_noise=True).generate_cohort()

    pd.testing.assert_frame_equal(base["features"], indep["features"])
    assert np.array_equal(base["true_default"], indep["true_default"])
    assert not np.array_equal(base["prior_score"], indep["prior_score"])

    # Severity-0 selection must be unexplainable from the observed prior-policy
    # column once independent noise is used (default path: corr ~0.92).
    feat = indep["features"]["prior_underwriter_score"].to_numpy()
    assert abs(np.corrcoef(feat, indep["prior_score"])[0, 1]) < 0.2
    assert abs(np.corrcoef(feat, base["prior_score"])[0, 1]) > 0.5


# Frozen on the pre-change working tree (before the pluggable-generator edit) by
# running exactly:
#   SelectiveLabelsLoop(improve_mode="both", max_rounds=2, n_applicants=1500, seed=42).run()
# Tuples: (iteration, severity, base_rate, approval_rate,
#          naive_declined_ece, reweight_declined_ece, retrain_declined_ece, control_metric)
_FLAT_FROZEN_ROUNDS = [
    (0, 0.0, 0.162, 0.6,
     0.06577659884915682, 0.05195818598023266, 0.05372145874585532, 0.05195818598023266),
    (1, 0.2, 0.18266666666666667, 0.6,
     0.034960713827482434, 0.05189947896006501, 0.05705044657012228, 0.05189947896006501),
]
_FLAT_FROZEN_FRONTIER = 0.2


# The _FLAT_FROZEN_ROUNDS floats below were captured under scikit-learn 1.9.0
# (pinned in pyproject.toml). This test is therefore version-sensitive: under
# scikit-learn 1.8.0 the last decimals differ because HistGradientBoosting float
# output shifts across releases, so the exact-equality assertion would fail.
def test_flat_generator_byte_identical_to_pre_change_baseline():
    """generator="flat" (the default) reproduces the pre-change metrics exactly."""
    result = SelectiveLabelsLoop(
        improve_mode="both", max_rounds=2, n_applicants=1500, seed=42
    ).run()
    got = [
        (r.iteration, r.selection_severity, r.base_rate, r.approval_rate,
         r.naive.declined_ece, r.reweight.declined_ece, r.retrain.declined_ece,
         r.control_metric)
        for r in result.rounds
    ]
    assert got == _FLAT_FROZEN_ROUNDS  # exact float equality == byte-identical
    assert result.frontier_severity == _FLAT_FROZEN_FRONTIER
