"""v4 Option A knob tests: generator_kwargs (loop) + unobserved_strength (eval).

All identity tests are IN-PROCESS DIFFERENTIALS (run default and explicit-default
in the same process and compare) — no stored float constants, so they are NOT
``pinned``: they hold on every sklearn/numpy version by construction.
"""
from __future__ import annotations

import numpy as np
import pytest

from cldd.counterfactual import run_counterfactual_eval
from cldd.loop import SelectiveLabelsLoop, make_generator
from cldd.scm import StructuralBorrowerGenerator


def _round_tuple(r):
    return (
        r.iteration, r.selection_severity, r.base_rate, r.approval_rate,
        r.naive.declined_ece,
        r.reweight.declined_ece if r.reweight is not None else None,
        r.retrain.declined_ece if r.retrain is not None else None,
        r.control_metric,
    )


def _run(generator, seed, generator_kwargs=None, n=800):
    return SelectiveLabelsLoop(
        improve_mode="both", max_rounds=1, n_applicants=n, seed=seed,
        generator=generator, generator_kwargs=generator_kwargs,
    ).run()


def test_generator_kwargs_explicit_default_identical_flat():
    """{"unobserved_strength": 0.7} == flat default, byte-for-byte."""
    base = _run("flat", seed=42)
    knob = _run("flat", seed=42, generator_kwargs={"unobserved_strength": 0.7})
    assert [_round_tuple(r) for r in base.rounds] == [_round_tuple(r) for r in knob.rounds]
    assert base.frontier_severity == knob.frontier_severity


def test_generator_kwargs_explicit_default_identical_scm():
    """{"unobserved_strength": 0.55} == scm default, byte-for-byte."""
    base = _run("scm", seed=42, n=600)
    knob = _run("scm", seed=42, generator_kwargs={"unobserved_strength": 0.55}, n=600)
    assert [_round_tuple(r) for r in base.rounds] == [_round_tuple(r) for r in knob.rounds]
    assert base.frontier_severity == knob.frontier_severity


def test_generator_kwargs_reaches_the_world():
    """Strength 0 must change the cohort's planted outcomes (non-vacuity)."""
    base = _run("flat", seed=42)
    zero = _run("flat", seed=42, generator_kwargs={"unobserved_strength": 0.0})
    assert _round_tuple(base.rounds[0]) != _round_tuple(zero.rounds[0])


def test_make_generator_forwards_extra_kwargs():
    gen = make_generator(
        "scm", severity=0.4, seed=7, n_applicants=100, approval_rate=0.6,
        unobserved_strength=0.0,
    )
    assert gen.unobserved_strength == 0.0
    assert gen.independent_selection_noise is True  # scm loop path untouched


def test_make_generator_rejects_selection_noise_override():
    """The scm path pins independent_selection_noise=True; a caller trying to
    override it must fail loudly (duplicate keyword), not silently win."""
    with pytest.raises(TypeError):
        make_generator(
            "scm", severity=0.4, seed=7, n_applicants=100, approval_rate=0.6,
            independent_selection_noise=False,
        )


# --------------------------------------------------------------------------- #
# run_counterfactual_eval knob (Task 2)
# --------------------------------------------------------------------------- #

_CF_KW = dict(n_applicants=800, selection_severity=0.4, n_query_applicants=60, seed=42)


def test_cf_explicit_default_identical():
    """unobserved_strength=0.55 == the SCM default, byte-for-byte headline floats."""
    base = run_counterfactual_eval(**_CF_KW)
    knob = run_counterfactual_eval(**_CF_KW, unobserved_strength=0.55)
    for attr in ("naive_mae", "gcomp_mae", "naive_bias", "gcomp_bias",
                 "naive_mae_strong_propagation", "gcomp_mae_strong_propagation",
                 "mae_gap_overall", "mae_gap_strong_propagation"):
        assert getattr(base, attr) == getattr(knob, attr), attr


def test_cf_strength_recorded_in_meta():
    r = run_counterfactual_eval(**_CF_KW, unobserved_strength=0.0)
    assert r.meta["unobserved_strength"] == 0.0
    base = run_counterfactual_eval(**_CF_KW)
    assert base.meta["unobserved_strength"] == 0.55  # scm ctor default


def test_cf_rejects_strength_with_external_generator():
    gen = StructuralBorrowerGenerator(n_applicants=200, selection_severity=0.4, seed=7)
    with pytest.raises(ValueError):
        run_counterfactual_eval(generator=gen, unobserved_strength=0.0)


def test_strength_zero_confounder_out_of_risk_and_selection():
    """At strength 0, u must not enter risk (and therefore not selection, which
    blends true risk) — asserted via the generator's own state, not downstream
    floats: perturbing confounder_u leaves the risk logit bit-identical."""
    gen = StructuralBorrowerGenerator(
        n_applicants=600, selection_severity=0.4, seed=7, unobserved_strength=0.0
    )
    cohort = gen.generate_cohort()
    st = cohort["scm_state"]
    logit_before = gen._risk_logit(st.values, st)
    st.confounder_u = st.confounder_u + 10.0
    logit_after = gen._risk_logit(st.values, st)
    assert np.array_equal(logit_before, logit_after)
