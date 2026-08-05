"""Tests for scripts/surface_stats.py -- verdict math, floors, I-1, fail-closed.

Synthetic in-memory frames only (3 seeds); the module's SEEDS list is
monkeypatched so completeness checks target the toy matrix. Not ``pinned``:
closed-form statistics over constructed rows.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"

_spec = importlib.util.spec_from_file_location("surface_stats", SCRIPTS / "surface_stats.py")
ss = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ss)

SEEDS3 = [1000, 1016, 1032]


def _fr_rows(strength, world, frontiers):
    """One terminal row per (seed, cell) -- enough for frontier extraction."""
    rows = []
    for seed, frontier in zip(SEEDS3, frontiers):
        rows.append({
            "unobserved_strength": str(strength), "seed": str(seed), "generator": world,
            "iteration": "0", "selection_severity": "0.0",
            "frontier_severity": "" if frontier is None else str(frontier),
            "passed": "True",
        })
    return rows


def test_frontier_extraction_and_never_passed_encoding(monkeypatch):
    monkeypatch.setattr(ss, "SEEDS", SEEDS3)
    rows = _fr_rows(0.7, "flat", [0.4, None, 0.2])
    f = ss.frontier_by_seed(rows, 0.7, "flat")
    assert f == {1000: 0.4, 1016: -0.2, 1032: 0.2}


def test_hs1_verdict_confirmed_on_clean_recession(monkeypatch):
    monkeypatch.setattr(ss, "SEEDS", SEEDS3)
    # strength 0: every seed tops out at 1.0; default 0.7: frontier 0.2 -> diff 0.8
    zero = ss.frontier_by_seed(_fr_rows(0.0, "flat", [1.0, 1.0, 1.0]), 0.0, "flat")
    dflt = ss.frontier_by_seed(_fr_rows(0.7, "flat", [0.2, 0.2, 0.2]), 0.7, "flat")
    row = ss.hs1_row("H-S1f", zero, dflt)
    assert row["median_stat"] == 0.8
    assert row["clears_floor"] is True          # floor = one grid step, 0.2
    assert row["sign_k"] == 3 and row["sign_n"] == 3


def test_hs1_floor_blocks_sub_grid_move(monkeypatch):
    monkeypatch.setattr(ss, "SEEDS", SEEDS3)
    zero = ss.frontier_by_seed(_fr_rows(0.0, "flat", [0.4, 0.4, 0.4]), 0.0, "flat")
    dflt = ss.frontier_by_seed(_fr_rows(0.7, "flat", [0.4, 0.4, 0.4]), 0.7, "flat")
    row = ss.hs1_row("H-S1f", zero, dflt)
    assert row["median_stat"] == 0.0
    assert row["clears_floor"] is False


def test_hs2_floor_is_strength_zero_scale():
    g0 = {1000: 0.001, 1016: -0.002, 1032: 0.003}     # median |g(0,.4)| = 0.002
    gd = {1000: 0.020, 1016: 0.015, 1032: 0.030}
    row = ss.hs2_row("H-S2a", gd, g0)
    assert row["floor"] == pytest.approx(0.002)
    assert row["clears_floor"] is True


def test_i1_fires_on_planted_mismatch(tmp_path):
    ref = tmp_path / "ref.csv"
    got = tmp_path / "got.csv"
    header = "unobserved_strength,seed,generator,iteration,x\n"
    ref.write_text("seed,generator,iteration,x\n1000,flat,0,0.123456\n")
    got.write_text(header + "0.7,1000,flat,0,0.123457\n")
    problems = ss.i1_check_frontier(got, ref, fields=["seed", "generator", "iteration", "x"],
                                    default_strength={"flat": 0.7, "scm": 0.55},
                                    seeds=[1000], worlds=("flat",))
    assert problems and "x" in problems[0]


def test_completeness_fails_closed(monkeypatch):
    monkeypatch.setattr(ss, "SEEDS", SEEDS3)
    rows = _fr_rows(0.0, "flat", [0.4, 0.4, 0.4])      # only 1 of 12 cells present
    missing = ss.missing_frontier_cells(rows)
    assert missing                                     # every other cell reported
