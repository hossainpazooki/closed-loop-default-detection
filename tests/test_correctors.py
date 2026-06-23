"""Tests for the pluggable corrector interface (the NEW extensible path).

These prove that (1) a custom Corrector subclass can be injected via
``correctors=[...]`` and drive loop control when it has the highest
``control_priority``; (2) the default-built corrector list (``correctors=None``)
reproduces the same named ``RoundResult`` fields as the legacy ``improve_mode``
path; and (3) ``RoundResult.corrections`` exposes the expected name->metrics map.

Numeric constants below were captured by running the loop once and freezing the
observed floats.
"""

from __future__ import annotations

import pytest

from cldd import LeverMetrics as LeverMetrics_pkg
from cldd.correctors import (
    CorrectionOutcome,
    Corrector,
    CorrectorContext,
    DisjointRetrainCorrector,
    IPWReweightCorrector,
    LeverMetrics,
    NaiveCorrector,
)
from cldd.loop import LeverMetrics as LeverMetrics_loop
from cldd.loop import SelectiveLabelsLoop


def test_lever_metrics_reexported_from_both_modules():
    """LeverMetrics must remain importable from cldd, cldd.loop, cldd.correctors,
    and be the same object across them (the re-export, not a copy)."""
    assert LeverMetrics is LeverMetrics_loop
    assert LeverMetrics is LeverMetrics_pkg


# A custom lever: returns a constant, known metric so we can assert it drives
# control deterministically. Highest control_priority so it wins precedence.
_SENTINEL = 0.0123456789


def _constant_metrics(value: float) -> LeverMetrics:
    return LeverMetrics(
        declined_ece=value,
        declined_auc=0.5,
        declined_brier=0.25,
        declined_mean_pd=0.1,
        declined_base_rate=0.1,
        declined_f1=0.0,
        all_ece=value,
    )


class ConstantCorrector(Corrector):
    name = "constant"
    control_priority = 99  # higher than every shipped corrector

    def apply(self, cohort: dict, ctx: CorrectorContext) -> CorrectionOutcome:
        return CorrectionOutcome(metrics=_constant_metrics(_SENTINEL))


def test_custom_corrector_drives_control():
    """A custom Corrector passed via correctors=[...] with the highest
    control_priority sets control_metric, and appears in the corrections map."""
    loop = SelectiveLabelsLoop(
        correctors=[NaiveCorrector(), ConstantCorrector()],
        max_rounds=1,
        n_applicants=800,
        seed=42,
        # target high enough that the sentinel passes -> loop would advance, but
        # we only assert control wiring here.
        target_declined_ece=1.0,
    )
    result = loop.run()
    r = result.rounds[0]
    assert r.control_metric == _SENTINEL
    assert "constant" in r.corrections
    assert r.corrections["constant"].declined_ece == _SENTINEL
    # naive still computed and projected onto the named field.
    assert r.naive is r.corrections["naive"]


def test_corrector_list_without_naive_is_rejected():
    """A custom corrector list missing a 'naive' lever fails fast at construction
    with a clear ValueError, not a mid-run KeyError (regression guard for the
    footgun surfaced by adversarial verification)."""
    with pytest.raises(ValueError, match="naive"):
        SelectiveLabelsLoop(correctors=[IPWReweightCorrector()])


# Frozen by running:
#   SelectiveLabelsLoop(improve_mode="both", max_rounds=1, n_applicants=800,
#                       seed=42).run()  -> rounds[0]
_NAIVE_ECE = 0.043576267185961026
_REWEIGHT_ECE = 0.024653553147705676
_RETRAIN_ECE = 0.06476068138171526


def test_explicit_corrector_list_matches_improve_mode_path():
    """An explicit correctors=[...] list yields the SAME numbers as the legacy
    improve_mode build. Environment-INDEPENDENT (one sklearn, one run), so it runs
    on the cross-version compat matrix too — this is the real refactor-equivalence
    guard; the frozen-float values live in the pinned test below."""
    explicit = SelectiveLabelsLoop(
        correctors=[NaiveCorrector(), IPWReweightCorrector(), DisjointRetrainCorrector()],
        max_rounds=1, n_applicants=800, seed=42,
    ).run().rounds[0]
    legacy = SelectiveLabelsLoop(
        improve_mode="both", max_rounds=1, n_applicants=800, seed=42,
    ).run().rounds[0]

    assert explicit.naive.declined_ece == legacy.naive.declined_ece
    assert explicit.reweight.declined_ece == legacy.reweight.declined_ece
    assert explicit.retrain.declined_ece == legacy.retrain.declined_ece
    # Same control lever (reweight, priority 2 > retrain 1 > naive 0) under both.
    assert explicit.control_metric == legacy.control_metric == legacy.reweight.declined_ece


@pytest.mark.pinned
def test_default_built_list_frozen_values():
    """correctors=None reproduces the legacy improve_mode='both' named fields, at
    the frozen float values. Float-exact on HistGBT output -> pinned (reproducible
    only under the requirements-dev.txt pins); the cross-version compat matrix
    deselects it via -m "not pinned"."""
    default = SelectiveLabelsLoop(
        improve_mode="both", correctors=None, max_rounds=1, n_applicants=800, seed=42
    ).run().rounds[0]

    assert default.naive.declined_ece == _NAIVE_ECE
    assert default.reweight.declined_ece == _REWEIGHT_ECE
    assert default.retrain.declined_ece == _RETRAIN_ECE
    # Control keys on reweight (priority 2 > retrain 1 > naive 0) under "both".
    assert default.control_metric == _REWEIGHT_ECE


def test_corrections_map_has_expected_keys():
    """RoundResult.corrections is keyed by corrector.name with LeverMetrics values."""
    r = SelectiveLabelsLoop(
        improve_mode="both", max_rounds=1, n_applicants=800, seed=42
    ).run().rounds[0]
    assert set(r.corrections.keys()) == {"naive", "reweight", "retrain"}
    for metrics in r.corrections.values():
        assert isinstance(metrics, LeverMetrics)
    # The named projection is the very same object as the map entry.
    assert r.naive is r.corrections["naive"]
    assert r.reweight is r.corrections["reweight"]
    assert r.retrain is r.corrections["retrain"]


def test_explore_corrector_populates_info_fields():
    """With exploration_rate>0 the default build adds ExplorationCorrector, whose
    info populates n_explored / explored_defaults and drives control (priority 3)."""
    r = SelectiveLabelsLoop(
        improve_mode="both",
        exploration_rate=0.2,
        max_rounds=1,
        n_applicants=800,
        seed=42,
    ).run().rounds[0]
    assert "explore" in r.corrections
    assert r.explore is r.corrections["explore"]
    assert r.n_explored > 0
    assert r.explored_defaults >= 0
    assert r.control_metric == r.explore.declined_ece
