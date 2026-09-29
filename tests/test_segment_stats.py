"""Tests for scripts/segment_stats.py -- verdict math, floors, I-C1, fail-closed.

Synthetic in-memory rows only; the module's SEEDS list is monkeypatched so
completeness checks target the toy matrix. Not ``pinned``: closed-form
statistics over constructed rows.
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"

_spec = importlib.util.spec_from_file_location("segment_stats", SCRIPTS / "segment_stats.py")
gs = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(gs)

SEEDS8 = [1000 + 16 * i for i in range(8)]


def _rows(policy, world, eces, frontiers, flagged=False, seeds=SEEDS8):
    """Round-0 row per seed: enough for E, F and the diagnostics table."""
    out = []
    for seed, ece, frontier in zip(seeds, eces, frontiers):
        out.append({
            "policy_id": policy, "generator": world, "seed": str(seed),
            "iteration": "0", "selection_severity": "0.0",
            "frontier_severity": "" if frontier is None else str(frontier),
            "passed": "True", "control_metric": str(ece),
            "diag_flagged": str(flagged),
        })
    return out


def _full_matrix(d1_ece, d1_frontier, placebo_d1_ece=0.021):
    """Every cell of the real matrix on 8 seeds, with chosen depth-1 outcomes."""
    rows = []
    for cell in gs._rgs.policy_cells():
        policy, world = cell["policy_id"], cell["world"]
        ece, frontier = 0.020, 0.4
        if policy == gs.LEGACY:
            ece = 0.019
        if policy == gs.PRIMARY_D1:
            ece, frontier = d1_ece, d1_frontier
        if policy == gs.PLACEBO_D1:
            ece = placebo_d1_ece
        # a small per-seed ramp keeps paired differences non-degenerate
        rows += _rows(policy, world,
                      [ece + 0.0001 * i for i in range(8)], [frontier] * 8,
                      flagged=cell["depth"] == 1.0)
    return rows


def test_extraction_and_never_passed_encoding():
    rows = _rows("legacy", "flat", [0.02, 0.03, 0.04], [0.4, None, 0.2], seeds=SEEDS8[:3])
    assert gs.ece_by_seed(rows, "legacy", "flat") == {1000: 0.02, 1016: 0.03, 1032: 0.04}
    assert gs.frontier_by_seed(rows, "legacy", "flat") == {1000: 0.4, 1016: -0.2, 1032: 0.2}
    assert gs.ece_by_seed(rows, "legacy", "scm") == {}


def test_recut_floor_is_the_depth0_vs_legacy_scale():
    e_d0 = {1000: 0.021, 1016: 0.018, 1032: 0.025}
    e_legacy = {1000: 0.020, 1016: 0.020, 1032: 0.020}
    assert gs.recut_floor(e_d0, e_legacy) == pytest.approx(0.002)


def test_hc1_floor_blocks_a_shift_inside_the_recut_noise():
    e_legacy = {s: 0.020 for s in SEEDS8}
    e_d0 = {s: 0.025 for s in SEEDS8}            # re-cut noise scale 0.005
    e_d1 = {s: 0.027 for s in SEEDS8}            # shift 0.002 < 0.005
    row = gs.hc1_row("H-C1f", "flat", gs.PRIMARY_D1, e_d1, e_d0, e_legacy)
    assert row["median_stat"] == pytest.approx(0.002)
    assert row["clears_floor"] is False
    assert row["sign_k"] == 8 and row["sign_n"] == 8


def test_hc2_floor_blocks_a_sub_grid_move():
    f = {s: 0.4 for s in SEEDS8}
    row = gs.hc2_row("H-C2f", "flat", gs.PRIMARY_D1, f, dict(f))
    assert row["median_stat"] == 0.0
    assert row["clears_floor"] is False


def test_hc2_counts_never_passed_runs():
    f_d0 = {1000: 0.4, 1016: 0.4}
    f_d1 = {1000: gs.NEVER_PASSED, 1016: 0.2}
    row = gs.hc2_row("H-C2f", "flat", gs.PRIMARY_D1, f_d0, f_d1)
    assert row["n_never_passed"] == 1
    assert row["median_stat"] == pytest.approx(0.4)


def test_family_confirms_a_clean_effect_and_holm_covers_exactly_four(monkeypatch):
    monkeypatch.setattr(gs, "SEEDS", SEEDS8)
    rows = gs.build_rows(_full_matrix(d1_ece=0.060, d1_frontier=0.2))
    conf = [r for r in rows if r["role"] == "confirmatory"]
    assert [r["hypothesis"] for r in conf] == ["H-C1f", "H-C1s", "H-C2f", "H-C2s"]
    # 8/8 positive: raw sign p = 0.5**8; Holm over m=4 multiplies the smallest by 4
    assert conf[0]["sign_p_raw"] == pytest.approx(0.5 ** 8)
    assert conf[0]["sign_p_holm"] == pytest.approx(4 * 0.5 ** 8)
    assert all(r["confirmed"] for r in conf)


def test_family_reports_a_null_as_not_confirmed(monkeypatch):
    monkeypatch.setattr(gs, "SEEDS", SEEDS8)
    rows = gs.build_rows(_full_matrix(d1_ece=0.020, d1_frontier=0.4))
    conf = [r for r in rows if r["role"] == "confirmatory"]
    assert not any(r["confirmed"] for r in conf)


def test_placebo_is_outside_the_family_and_flags_a_move(monkeypatch):
    monkeypatch.setattr(gs, "SEEDS", SEEDS8)
    held = gs.build_rows(_full_matrix(0.060, 0.2, placebo_d1_ece=0.0201))
    moved = gs.build_rows(_full_matrix(0.060, 0.2, placebo_d1_ece=0.060))
    p_held = next(r for r in held if r["role"] == "control")
    p_moved = next(r for r in moved if r["role"] == "control")
    assert p_held["confirmed"] is False
    assert p_moved["confirmed"] is True
    assert p_held["world"] == "flat" and p_held["policy_id"] == gs.PLACEBO_D1


def test_diagnostics_table_counts_flag_by_outcome():
    rows = _rows("p", "flat", [0.02] * 3, [0.4] * 3, flagged=True, seeds=SEEDS8[:3])
    rows[0]["passed"] = "False"
    rows += _rows("p", "flat", [0.02], [0.4], flagged=False, seeds=[2000])
    assert gs.diag_confusion(rows, "p", "flat") == {
        "flagged_passed": 2, "flagged_failed": 1, "clear_passed": 1, "clear_failed": 0,
    }


def test_missing_cells_are_reported(monkeypatch):
    monkeypatch.setattr(gs, "SEEDS", SEEDS8)
    rows = _full_matrix(0.060, 0.2)
    assert gs.missing_cells(rows) == []
    dropped = [r for r in rows
               if not (r["policy_id"] == gs.LEGACY and r["generator"] == "scm"
                       and r["seed"] == "1000")]
    assert gs.missing_cells(dropped) == [(gs.LEGACY, "scm", 1000)]


def _write(path, header, lines):
    path.write_text(header + "\n" + "\n".join(lines) + "\n")


def test_ic1_passes_on_equal_rows_and_fires_on_a_planted_mismatch(tmp_path):
    ref, got = tmp_path / "ref.csv", tmp_path / "got.csv"
    _write(ref, "seed,generator,iteration,x", ["1000,flat,0,0.123456"])
    _write(got, "policy_id,seed,generator,iteration,x", ["legacy,1000,flat,0,0.123456"])
    kw = dict(fields=["seed", "generator", "iteration", "x"], seeds=[1000], worlds=("flat",))
    assert gs.ic1_check(got, ref, **kw) == []
    _write(got, "policy_id,seed,generator,iteration,x", ["legacy,1000,flat,0,0.123457"])
    problems = gs.ic1_check(got, ref, **kw)
    assert problems and "x" in problems[0]


def test_ic1_ignores_policy_rows_and_fails_closed_on_an_absent_reference(tmp_path):
    ref, got = tmp_path / "ref.csv", tmp_path / "got.csv"
    _write(ref, "seed,generator,iteration,x", ["1000,flat,0,0.5"])
    _write(got, "policy_id,seed,generator,iteration,x",
           ["legacy,1000,flat,0,0.5", "vintage_years:low:d1.0,1000,flat,0,0.9"])
    kw = dict(fields=["seed", "generator", "iteration", "x"], worlds=("flat",))
    assert gs.ic1_check(got, ref, seeds=[1000], **kw) == []
    problems = gs.ic1_check(got, ref, seeds=[1000, 1016], **kw)
    assert len(problems) == 1 and "reference cell absent" in problems[0]


def test_main_fails_closed_on_an_incomplete_matrix(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(gs, "SEEDS", SEEDS8)
    csv_path = tmp_path / "segment_frontier.csv"
    rows = _full_matrix(0.060, 0.2)[:-1]
    header = list(rows[0])
    _write(csv_path, ",".join(header),
           [",".join(r[h] for h in header) for r in rows])
    monkeypatch.setattr(gs, "SEG_CSV", csv_path)
    monkeypatch.setattr(gs, "OUT_CSV", tmp_path / "segment_stats.csv")
    assert gs.main() == 1
    assert "FAIL-CLOSED" in capsys.readouterr().out
    assert not (tmp_path / "segment_stats.csv").exists()


def test_main_writes_stats_to_the_configured_path(monkeypatch, tmp_path):
    """Success path, with every path redirected: nothing may land on the real
    artifact paths (a definition-time default target would)."""
    monkeypatch.setattr(gs, "SEEDS", SEEDS8)
    rows = _full_matrix(0.060, 0.2)
    for r in rows:
        r.update(seed=r["seed"], x="1")
    header = list(rows[0])
    seg = tmp_path / "segment_frontier.csv"
    _write(seg, ",".join(header), [",".join(r[h] for h in header) for r in rows])
    ref = tmp_path / "spaced.csv"
    legacy = [r for r in rows if r["policy_id"] == gs.LEGACY]
    _write(ref, ",".join(header), [",".join(r[h] for h in header) for r in legacy])
    out = tmp_path / "segment_stats.csv"
    monkeypatch.setattr(gs, "SEG_CSV", seg)
    monkeypatch.setattr(gs, "SPACED_FR", ref)
    monkeypatch.setattr(gs, "FR_FIELDS", ["seed", "generator", "iteration", "x"])
    monkeypatch.setattr(gs, "OUT_CSV", out)
    assert gs.main() == 0
    assert out.exists()


def test_stats_csv_round_trips_the_diagnostics_json(monkeypatch, tmp_path):
    monkeypatch.setattr(gs, "SEEDS", SEEDS8)
    out = tmp_path / "segment_stats.csv"
    frame = gs.write_stats_csv(gs.build_rows(_full_matrix(0.060, 0.2)), out)
    assert list(frame.columns) == gs.SEGMENT_STATS_FIELDS
    diag = frame[frame["metric"] == "cell_diagnostics"].iloc[0]
    assert set(json.loads(diag["detail_json"])) == {
        "flagged_passed", "flagged_failed", "clear_passed", "clear_failed"}
