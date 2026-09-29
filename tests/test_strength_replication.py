"""Tests for the strength-1.0 replication driver and its analysis.

The driver is exercised by its --pilot gate; these tests pin the matrix
DEFINITION, the seed-disjointness that makes the run a replication, and the
verdict math. Synthetic rows only, so NOT ``pinned``.
"""
from __future__ import annotations

import ast
import importlib.util
import json
import subprocess
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"


def _load(name):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


rsr = _load("run_strength_replication")
rst = _load("strength_replication_stats")

SEEDS8 = rsr.SEEDS[:8]


# --------------------------------------------------------------------------- #
# Matrix definition
# --------------------------------------------------------------------------- #

def test_locked_grid():
    assert rsr.SEEDS == [5000 + 16 * i for i in range(25)]
    assert rsr.STRENGTHS == [0.0, 0.2, 0.4, 0.55, 0.7, 1.0]
    assert (rsr.STRENGTH_LOW, rsr.STRENGTH_HIGH) == (0.0, 1.0)


def test_matrix_is_300_runs_with_no_duplicate_cells():
    cells = rsr.cells()
    assert len(cells) == 12 and len(set(cells)) == 12
    assert len(cells) * len(rsr.SEEDS) == 300
    assert {w for _v, w in cells} == {"flat", "scm"}


def test_schema_extends_the_surface_schema_by_the_four_diagnostics():
    assert rsr.SHARED_FIELDS == rsr._rss.SURF_FR_FIELDS
    assert rsr.DIAG_FIELDS == ["propensity_auc", "ess_ratio",
                               "unfunded_below_floor", "diag_flagged"]
    assert rsr.FIELDS == rsr.SHARED_FIELDS + rsr.DIAG_FIELDS
    assert len(set(rsr.FIELDS)) == len(rsr.FIELDS)


def test_child_is_the_surface_child_plus_the_diagnostic_block_and_nothing_else():
    """A replication judged by a re-implemented child would not be a replication:
    removing the inserted block must give back the v4 child byte for byte."""
    child = rsr.child_template()
    assert child.count(rsr.DIAG_BLOCK) == 1
    assert child.replace(rsr.DIAG_BLOCK, "") == rsr._rss._FR_CHILD
    source = (SCRIPTS / "run_strength_replication.py").read_text(encoding="utf-8")
    assert "SelectiveLabelsLoop(" not in source


def test_child_code_is_valid_python_and_writes_every_field():
    code = rsr.child_template().format(strength=1.0, generator="scm", seed=5000)
    ast.parse(code)
    for field in rsr.FIELDS:
        assert f'"{field}"' in code, field


# --------------------------------------------------------------------------- #
# Seed disjointness -- what makes this a replication and not a re-read
# --------------------------------------------------------------------------- #

def test_fresh_seeds_share_nothing_with_the_spent_set():
    fresh = set().union(*(rsr.consumed(s) for s in rsr.SEEDS))
    spent = set().union(*(rsr.consumed(s) for s in rsr.SPENT_SEEDS))
    assert not fresh & spent


def test_fresh_seeds_clear_the_spent_ceiling():
    """Every committed artifact's seeds are <= 2026; a loop run consumes at most
    seed + 1007. Nothing below the ceiling may be reused."""
    assert rsr.SPENT_CEILING == 4000
    assert min(min(rsr.consumed(s)) for s in rsr.SEEDS) >= rsr.SPENT_CEILING
    assert max(max(rsr.consumed(s)) for s in rsr.SPENT_SEEDS) < rsr.SPENT_CEILING


def test_runs_within_a_cell_are_seed_disjoint():
    seen: set = set()
    for s in rsr.SEEDS:
        used = rsr.consumed(s)
        assert not seen & used, f"seed {s} overlaps an earlier run in the cell"
        seen |= used


def test_consumption_model_matches_the_loop_config():
    from cldd import config
    assert rsr.MAX_ROUNDS == config.MAX_ROUNDS
    assert rsr.TRAIN_SEED_OFFSET == config.TRAIN_SEED_OFFSET
    assert rst.TARGET == config.TARGET_DECLINED_ECE


def test_pilot_never_touches_a_fresh_seed():
    assert rsr.PILOT_SEED in rsr.SPENT_SEEDS
    assert rsr.PILOT_SEED not in rsr.SEEDS


def test_pilot_reference_artifact_is_git_tracked():
    tracked = subprocess.run(
        ["git", "ls-files", "artifacts/"],
        capture_output=True, text=True, cwd=rsr.ROOT,
    ).stdout.splitlines()
    assert rsr.SURFACE_FR.name in {Path(p).name for p in tracked}


# --------------------------------------------------------------------------- #
# Synthetic matrices
# --------------------------------------------------------------------------- #

def _run_rows(strength, world, seed, eces, frontier, flags=None):
    """One loop run: a row per walked severity 0.0, 0.2, ... with its ECE."""
    rows = []
    for i, ece in enumerate(eces):
        sev = round(0.2 * i, 1)
        flag = bool(flags[i]) if flags else False
        rows.append({
            "unobserved_strength": str(strength), "seed": str(seed), "generator": world,
            "iteration": str(i), "selection_severity": str(sev),
            "frontier_severity": "" if frontier is None else str(frontier),
            "passed": str(ece <= 0.10), "reweight_declined_ece": repr(ece),
            "propensity_auc": repr(0.80 + 0.05 * i), "ess_ratio": repr(0.99 - 0.05 * i),
            "unfunded_below_floor": repr(0.01 * i), "diag_flagged": str(flag),
        })
    return rows


def _matrix(high_04=0.090, high_frontier=0.2, base_04=0.060, seeds=SEEDS8):
    """Every cell of the real matrix. Strength 1.0 gets ``high_04`` at severity
    0.4 and ``high_frontier``; every other strength gets ``base_04`` and 0.4."""
    rows = []
    for strength, world in rsr.cells():
        for k, seed in enumerate(seeds):
            jitter = 0.0001 * k
            if strength == rsr.STRENGTH_HIGH:
                e04, frontier = high_04 + jitter, high_frontier
            else:
                e04, frontier = base_04 + jitter, 0.4
            # severity 0: the noise scale. +/-0.002 around 0.02, alternating by seed
            e0 = 0.020 + (0.002 if (k % 2) == (strength == rsr.STRENGTH_HIGH) else 0.0)
            eces = [e0, 0.040 + jitter, e04, 0.150]
            rows += _run_rows(strength, world, seed, eces, frontier,
                              flags=[False, False, False, True])
    return rows


def _conf(rows, role):
    return [r for r in rows if r["metric"] == "hypothesis" and r["role"] == role]


# --------------------------------------------------------------------------- #
# Extraction and the floor
# --------------------------------------------------------------------------- #

def test_ece_extraction_reads_one_severity():
    rows = _run_rows(0.0, "flat", 5000, [0.02, 0.04, 0.06], 0.4)
    assert rst.ece_by_seed(rows, 0.0, "flat", 0.4) == {5000: 0.06}
    assert rst.ece_by_seed(rows, 0.0, "flat", 0.6) == {}
    assert rst.ece_by_seed(rows, 0.0, "scm", 0.4) == {}


def test_floor_is_the_larger_of_target_distance_and_noise():
    e_low = {s: 0.060 for s in SEEDS8}                  # distance to 0.10 = 0.040
    quiet = ({s: 0.020 for s in SEEDS8}, {s: 0.021 for s in SEEDS8})    # noise 0.001
    loud = ({s: 0.020 for s in SEEDS8}, {s: 0.075 for s in SEEDS8})     # noise 0.055
    floor, parts = rst.primary_floor(e_low, *quiet)
    assert floor == pytest.approx(0.040) and parts["binding"] == "target_distance"
    floor, parts = rst.primary_floor(e_low, *loud)
    assert floor == pytest.approx(0.055) and parts["binding"] == "noise_scale"
    assert parts["target_distance"] == pytest.approx(0.040)


def test_floor_is_unevaluable_when_the_baseline_is_already_at_the_target():
    e_low = {s: 0.100 for s in SEEDS8}
    with pytest.raises(rst.Unevaluable, match="already at or over"):
        rst.primary_floor(e_low, {s: 0.02 for s in SEEDS8}, {s: 0.02 for s in SEEDS8})


# --------------------------------------------------------------------------- #
# Families
# --------------------------------------------------------------------------- #

def test_primary_family_is_calibration_error_and_confirms_a_clean_rise(monkeypatch):
    monkeypatch.setattr(rst, "SEEDS", SEEDS8)
    monkeypatch.setattr(rst, "MIN_PAIRS", 8)
    rows = rst.build_rows(_matrix(high_04=0.110, base_04=0.060))
    primary = _conf(rows, "confirmatory")
    assert [(r["hypothesis"], r["world"]) for r in primary] == [("H-R1f", "flat"), ("H-R1s", "scm")]
    for r in primary:
        assert r["severity"] == rst.PRIMARY_SEVERITY
        assert r["median_stat"] == pytest.approx(0.050)
        assert r["floor"] == pytest.approx(0.040, abs=1e-3)   # target distance binds
        assert r["sign_p_raw"] == pytest.approx(0.5 ** 8)
        assert r["sign_p_holm"] == pytest.approx(2 * 0.5 ** 8)     # Holm over m=2
        assert r["confirmed"] is True


def test_primary_floor_blocks_a_rise_that_does_not_reach_the_target(monkeypatch):
    monkeypatch.setattr(rst, "SEEDS", SEEDS8)
    monkeypatch.setattr(rst, "MIN_PAIRS", 8)
    # rises on every seed (+0.020) but the baseline sits 0.040 below the target
    primary = _conf(rst.build_rows(_matrix(high_04=0.080, base_04=0.060)), "confirmatory")
    for r in primary:
        assert r["sign_k"] == 8 and r["sign_n"] == 8
        assert r["clears_floor"] is False and r["confirmed"] is False


def test_secondary_family_is_the_frontier_with_its_own_holm(monkeypatch):
    monkeypatch.setattr(rst, "SEEDS", SEEDS8)
    monkeypatch.setattr(rst, "MIN_PAIRS", 8)
    rows = rst.build_rows(_matrix(high_04=0.110, high_frontier=0.2))
    secondary = _conf(rows, "secondary")
    assert [(r["hypothesis"], r["world"]) for r in secondary] == [("H-R2f", "flat"), ("H-R2s", "scm")]
    for r in secondary:
        assert r["floor"] == pytest.approx(0.2)
        assert r["median_stat"] == pytest.approx(0.2)
        assert r["sign_p_holm"] == pytest.approx(2 * 0.5 ** 8)     # m=2, not m=4
        assert r["confirmed"] is True


def test_families_are_judged_independently(monkeypatch):
    monkeypatch.setattr(rst, "SEEDS", SEEDS8)
    monkeypatch.setattr(rst, "MIN_PAIRS", 8)
    rows = rst.build_rows(_matrix(high_04=0.110, high_frontier=0.4))
    assert all(r["confirmed"] for r in _conf(rows, "confirmatory"))
    assert not any(r["confirmed"] for r in _conf(rows, "secondary"))


def test_a_run_without_the_primary_row_is_excluded_and_counted(monkeypatch):
    monkeypatch.setattr(rst, "SEEDS", SEEDS8)
    monkeypatch.setattr(rst, "MIN_PAIRS", 7)
    rows = _matrix(high_04=0.110)
    drop = str(SEEDS8[0])
    rows = [r for r in rows if not (r["generator"] == "flat" and r["seed"] == drop
                                    and float(r["unobserved_strength"]) == 1.0
                                    and float(r["selection_severity"]) >= 0.4)]
    flat = next(r for r in rst.build_rows(rows) if r["hypothesis"] == "H-R1f")
    assert flat["n_seeds"] == 7
    assert json.loads(flat["detail_json"])["n_missing_pairs"] == 1


def test_too_few_pairs_is_unevaluable(monkeypatch):
    monkeypatch.setattr(rst, "SEEDS", SEEDS8)
    monkeypatch.setattr(rst, "MIN_PAIRS", 8)
    rows = _matrix(high_04=0.110)
    drop = str(SEEDS8[0])
    rows = [r for r in rows if not (r["generator"] == "flat" and r["seed"] == drop
                                    and float(r["unobserved_strength"]) == 1.0
                                    and float(r["selection_severity"]) >= 0.4)]
    with pytest.raises(rst.Unevaluable, match="pairs"):
        rst.build_rows(rows)


# --------------------------------------------------------------------------- #
# Descriptive rows
# --------------------------------------------------------------------------- #

def test_dose_rows_cover_every_strength_above_zero(monkeypatch):
    monkeypatch.setattr(rst, "SEEDS", SEEDS8)
    monkeypatch.setattr(rst, "MIN_PAIRS", 8)
    dose = [r for r in rst.build_rows(_matrix(high_04=0.110)) if r["metric"] == "dose_ece"]
    assert len(dose) == 10          # 5 strengths above zero x 2 worlds
    top = next(r for r in dose if r["world"] == "flat" and r["strength"] == 1.0)
    assert top["median_stat"] == pytest.approx(0.050) and top["sign_k"] == 8
    mid = next(r for r in dose if r["world"] == "flat" and r["strength"] == 0.4)
    assert mid["median_stat"] == pytest.approx(0.0) and mid["sign_k"] == 0


def test_flag_reads_are_descriptive_and_both_are_present(monkeypatch):
    monkeypatch.setattr(rst, "SEEDS", SEEDS8)
    monkeypatch.setattr(rst, "MIN_PAIRS", 8)
    rows = rst.build_rows(_matrix(high_04=0.110))
    across = [r for r in rows if r["metric"] == "flag_at_failing_severity"]
    within = [r for r in rows if r["metric"] == "diag_within_severity"]
    assert len(across) == 2 and len(within) == 2
    assert all(r["role"] == "descriptive" and r["strength"] == 0.0 for r in across + within)
    flat = next(r for r in across if r["world"] == "flat")
    assert (flat["sign_k"], flat["sign_n"]) == (8, 8)      # flagged at each failing round
    table = json.loads(flat["detail_json"])
    assert table["flagged_passed"] == 0 and table["clear_passed"] == 24
    assert table["overlap_explanation_withdrawn"] is False
    w = json.loads(next(r for r in within if r["world"] == "flat")["detail_json"])
    assert w["n_failing"] == 0 and w["n_passing"] == 8
    assert set(w["spearman_vs_ece"]) == {"propensity_auc", "ess_ratio", "unfunded_below_floor"}


def test_reading_rule_withdraws_when_the_flag_is_clear_at_most_failing_rounds(monkeypatch):
    monkeypatch.setattr(rst, "SEEDS", SEEDS8)
    monkeypatch.setattr(rst, "MIN_PAIRS", 8)
    monkeypatch.setattr(rst, "WITHDRAW_AT", 5)          # "most" of 8 seeds
    rows = _matrix(high_04=0.110)
    cleared = 0
    for r in rows:
        if (r["generator"] == "flat" and float(r["unobserved_strength"]) == 0.0
                and r["passed"] == "False" and cleared < 5):
            r["diag_flagged"] = "False"
            cleared += 1
    across = {r["world"]: json.loads(r["detail_json"])
              for r in rst.build_rows(rows) if r["metric"] == "flag_at_failing_severity"}
    assert across["flat"]["clear_failed"] == 5
    assert across["flat"]["overlap_explanation_withdrawn"] is True
    assert across["scm"]["overlap_explanation_withdrawn"] is False


def test_reading_rule_threshold_is_a_majority_of_the_seed_set():
    assert rst.WITHDRAW_AT == 13 and len(rst.SEEDS) == 25


def test_cell_rows_carry_the_frontier_distribution(monkeypatch):
    monkeypatch.setattr(rst, "SEEDS", SEEDS8)
    monkeypatch.setattr(rst, "MIN_PAIRS", 8)
    cell = [r for r in rst.build_rows(_matrix(high_04=0.110)) if r["metric"] == "cell_frontier"]
    assert len(cell) == 12
    high = next(r for r in cell if r["world"] == "flat" and r["strength"] == 1.0)
    assert json.loads(high["detail_json"]) == {"0.2": 8}


# --------------------------------------------------------------------------- #
# Fail-closed
# --------------------------------------------------------------------------- #

def test_seed_guard_checks_consumed_spans_not_base_seeds():
    rows = _matrix(high_04=0.110)
    assert rst.spent_seed_rows(rows) == []
    # 1005 is not a spent BASE seed, but the run at 1000 consumed it
    assert 1005 not in rsr.SPENT_SEEDS
    assert rst.spent_seed_rows(rows + _run_rows(1.0, "flat", 1005, [0.02], 0.4)) == [1005]
    # 2003 sits in the train span of the run at 1000 (1000 + 1000 + 3)
    assert rst.spent_seed_rows(rows + _run_rows(1.0, "flat", 2003, [0.02], 0.4)) == [2003]
    # 3995 consumes 3995..4002: it starts below the ceiling
    assert rst.spent_seed_rows(rows + _run_rows(1.0, "flat", 3995, [0.02], 0.4)) == [3995]


def test_missing_cells_are_reported(monkeypatch):
    monkeypatch.setattr(rst, "SEEDS", SEEDS8)
    rows = _matrix(high_04=0.110)
    assert rst.missing_cells(rows) == []
    first = rows[0]
    dropped = [r for r in rows if not (r["generator"] == first["generator"]
                                       and r["seed"] == first["seed"]
                                       and r["unobserved_strength"] == first["unobserved_strength"])]
    assert rst.missing_cells(dropped) == [(0.0, "flat", SEEDS8[0])]


def _write_csv(path, rows):
    header = list(rows[0])
    path.write_text(",".join(header) + "\n"
                    + "\n".join(",".join(r[h] for h in header) for r in rows) + "\n")


def _drop_run(rows):
    first = rows[0]
    return [r for r in rows if not (r["generator"] == first["generator"]
                                    and r["seed"] == first["seed"]
                                    and r["unobserved_strength"] == first["unobserved_strength"])]


@pytest.mark.parametrize("defect", ["incomplete", "spent", "baseline_at_target"])
def test_main_fails_closed(defect, monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(rst, "SEEDS", SEEDS8)
    monkeypatch.setattr(rst, "MIN_PAIRS", 8)
    rows = _matrix(high_04=0.110)
    if defect == "incomplete":
        rows = _drop_run(rows)
    elif defect == "spent":
        rows = rows + _run_rows(1.0, "flat", 1005, [0.02, 0.04, 0.06], 0.4)
    else:
        rows = _matrix(high_04=0.150, base_04=0.105)
    src = tmp_path / "in.csv"
    _write_csv(src, rows)
    monkeypatch.setattr(rst, "IN_CSV", src)
    monkeypatch.setattr(rst, "OUT_CSV", tmp_path / "out.csv")
    assert rst.main() == 1
    assert "FAIL-CLOSED" in capsys.readouterr().out
    assert not (tmp_path / "out.csv").exists()


def test_main_writes_stats_to_the_configured_path(monkeypatch, tmp_path):
    monkeypatch.setattr(rst, "SEEDS", SEEDS8)
    monkeypatch.setattr(rst, "MIN_PAIRS", 8)
    src = tmp_path / "in.csv"
    _write_csv(src, _matrix(high_04=0.110))
    monkeypatch.setattr(rst, "IN_CSV", src)
    monkeypatch.setattr(rst, "OUT_CSV", tmp_path / "out.csv")
    assert rst.main() == 0
    assert (tmp_path / "out.csv").exists()
