"""Tests for the strength-1.0 replication driver and its analysis.

The driver is exercised by its --pilot gate; these tests pin the matrix
DEFINITION, the seed-disjointness that makes the run a replication, and the
verdict math. Synthetic rows only, so NOT ``pinned``.
"""
from __future__ import annotations

import importlib.util
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
    assert (rsr.STRENGTH_LOW, rsr.STRENGTH_HIGH) == (0.0, 1.0)
    assert rsr.strengths_for("flat") == [0.0, 0.7, 1.0]
    assert rsr.strengths_for("scm") == [0.0, 0.55, 1.0]


def test_matrix_is_150_runs_with_no_duplicate_cells():
    cells = rsr.cells()
    assert len(cells) == 6 and len(set(cells)) == 6
    assert len(cells) * len(rsr.SEEDS) == 150


def test_schema_is_the_surface_schema():
    assert rsr.FIELDS == rsr._rss.SURF_FR_FIELDS


def test_driver_reuses_the_surface_child_verbatim():
    """A replication judged by a re-implemented child would not be a replication."""
    source = (SCRIPTS / "run_strength_replication.py").read_text(encoding="utf-8")
    assert "_rss._FR_CHILD.format(" in source
    assert "SelectiveLabelsLoop(" not in source


# --------------------------------------------------------------------------- #
# Seed disjointness -- what makes this a replication and not a re-read
# --------------------------------------------------------------------------- #

def test_fresh_seeds_share_nothing_with_the_spent_set():
    fresh = set().union(*(rsr.consumed(s) for s in rsr.SEEDS))
    spent = set().union(*(rsr.consumed(s) for s in rsr.SPENT_SEEDS))
    assert not fresh & spent


def test_fresh_seeds_clear_every_committed_artifact_seed():
    """Every committed artifact's seeds are <= 2026; a loop run consumes at most
    seed + 1007. Nothing below 4000 may be reused."""
    assert min(min(rsr.consumed(s)) for s in rsr.SEEDS) >= 4000


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
# Analysis
# --------------------------------------------------------------------------- #

def _rows(strength, world, frontiers, seeds=SEEDS8):
    return [{
        "unobserved_strength": str(strength), "seed": str(seed), "generator": world,
        "iteration": "0", "selection_severity": "0.0",
        "frontier_severity": "" if f is None else str(f), "passed": "True",
    } for seed, f in zip(seeds, frontiers)]


def _matrix(high_flat, high_scm, seeds=SEEDS8):
    rows = []
    for strength, world in rsr.cells():
        frontier = 0.4
        if strength == rsr.STRENGTH_HIGH:
            frontier = high_flat if world == "flat" else high_scm
        rows += _rows(strength, world, [frontier] * len(seeds), seeds)
    return rows


def test_family_is_exactly_two_and_confirms_a_clean_recession(monkeypatch):
    monkeypatch.setattr(rst, "SEEDS", SEEDS8)
    rows = rst.build_rows(_matrix(0.2, 0.2))
    conf = [r for r in rows if r["metric"] == "hypothesis"]
    assert [(r["hypothesis"], r["world"]) for r in conf] == [("H-R1f", "flat"), ("H-R1s", "scm")]
    # 8/8 positive: raw sign p = 0.5**8; Holm over m=2 doubles the smallest
    assert conf[0]["sign_p_raw"] == pytest.approx(0.5 ** 8)
    assert conf[0]["sign_p_holm"] == pytest.approx(2 * 0.5 ** 8)
    assert all(r["confirmed"] for r in conf)
    assert all(r["median_stat"] == pytest.approx(0.2) for r in conf)


def test_worlds_are_judged_separately(monkeypatch):
    monkeypatch.setattr(rst, "SEEDS", SEEDS8)
    conf = [r for r in rst.build_rows(_matrix(0.2, 0.4)) if r["metric"] == "hypothesis"]
    assert [r["confirmed"] for r in conf] == [True, False]


def test_floor_blocks_a_minority_move(monkeypatch):
    """3 of 8 seeds recede one step: the median difference is 0, below the floor."""
    monkeypatch.setattr(rst, "SEEDS", SEEDS8)
    rows = _matrix(0.4, 0.4)
    moved = 0
    for r in rows:
        if (r["generator"] == "flat" and float(r["unobserved_strength"]) == 1.0
                and moved < 3):
            r["frontier_severity"] = "0.2"
            moved += 1
    flat = next(r for r in rst.build_rows(rows) if r["hypothesis"] == "H-R1f")
    assert flat["sign_k"] == 3 and flat["sign_n"] == 3
    assert flat["clears_floor"] is False and flat["confirmed"] is False


def test_descriptive_rows_carry_the_distribution(monkeypatch):
    import json
    monkeypatch.setattr(rst, "SEEDS", SEEDS8)
    rows = rst.build_rows(_matrix(0.2, 0.2))
    cell = [r for r in rows if r["metric"] == "cell_frontier"]
    assert len(cell) == 6
    high_flat = next(r for r in cell if r["world"] == "flat" and r["strength"] == 1.0)
    assert json.loads(high_flat["detail_json"]) == {"0.2": 8}


def test_missing_cells_and_spent_seeds_are_reported(monkeypatch):
    monkeypatch.setattr(rst, "SEEDS", SEEDS8)
    rows = _matrix(0.2, 0.2)
    assert rst.missing_cells(rows) == []
    assert rst.missing_cells(rows[1:]) == [(0.0, "flat", SEEDS8[0])]
    assert rst.spent_seed_rows(rows) == []
    tainted = rows + _rows(1.0, "flat", [0.2], seeds=[1000])
    assert rst.spent_seed_rows(tainted) == [1000]


def _write_csv(path, rows):
    header = list(rows[0])
    path.write_text(",".join(header) + "\n"
                    + "\n".join(",".join(r[h] for h in header) for r in rows) + "\n")


@pytest.mark.parametrize("defect", ["incomplete", "spent"])
def test_main_fails_closed(defect, monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(rst, "SEEDS", SEEDS8)
    rows = _matrix(0.2, 0.2)
    rows = rows[:-1] if defect == "incomplete" else rows + _rows(1.0, "flat", [0.2], [1000])
    src = tmp_path / "in.csv"
    _write_csv(src, rows)
    monkeypatch.setattr(rst, "IN_CSV", src)
    monkeypatch.setattr(rst, "OUT_CSV", tmp_path / "out.csv")
    assert rst.main() == 1
    assert "FAIL-CLOSED" in capsys.readouterr().out
    assert not (tmp_path / "out.csv").exists()


def test_main_writes_stats_on_a_complete_matrix(monkeypatch, tmp_path):
    monkeypatch.setattr(rst, "SEEDS", SEEDS8)
    src = tmp_path / "in.csv"
    _write_csv(src, _matrix(0.2, 0.2))
    monkeypatch.setattr(rst, "IN_CSV", src)
    monkeypatch.setattr(rst, "OUT_CSV", tmp_path / "out.csv")
    assert rst.main() == 0
    assert (tmp_path / "out.csv").exists()
