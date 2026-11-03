"""Cell-enumeration tests for scripts/run_segment_sweep.py (Option C).

The driver itself is exercised by its --pilot gate (subprocess orchestration is
not unit-tested, same as run_surface_sweep.py); these tests pin the matrix
DEFINITION and the child-code contract.
"""
from __future__ import annotations

import ast
import importlib.util
import subprocess
from pathlib import Path

_spec = importlib.util.spec_from_file_location(
    "run_segment_sweep",
    Path(__file__).resolve().parents[1] / "scripts" / "run_segment_sweep.py",
)
rgs = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(rgs)


def test_locked_grid():
    assert rgs.SEEDS == [1000 + 16 * i for i in range(25)]
    assert rgs.STRENGTH == 0.0                      # ruling F8: confounder off
    assert rgs.N_SEGMENTS == 5
    assert rgs.DEPTHS == [0.0, 0.5, 1.0]
    assert rgs.ATTACK_FEATURES == [("aggregate_credit_utilization", "high"),
                                   ("vintage_years", "low")]
    assert rgs.PLACEBO_FEATURE == ("requested_amount", "high")
    assert rgs.PLACEBO_WORLDS == ("flat",)


def test_matrix_is_400_runs_with_no_duplicate_cells():
    cells = rgs.policy_cells()
    keys = [(c["policy_id"], c["world"]) for c in cells]
    assert len(keys) == 16 and len(set(keys)) == 16
    assert len(cells) * len(rgs.SEEDS) == 400
    assert sum(1 for c in cells if c["world"] == "flat") == 9
    assert sum(1 for c in cells if c["world"] == "scm") == 7


def test_legacy_cell_exists_in_both_worlds_and_carries_no_policy():
    legacy = [c for c in rgs.policy_cells() if c["policy_id"] == rgs.LEGACY]
    assert {c["world"] for c in legacy} == {"flat", "scm"}
    assert all(c["depth"] is None and c["feature"] == "" for c in legacy)


def test_placebo_is_flat_only():
    feature, _ = rgs.PLACEBO_FEATURE
    worlds = {c["world"] for c in rgs.policy_cells() if c["feature"] == feature}
    assert worlds == {"flat"}


def test_schema_extends_the_spaced_schema():
    assert rgs.SEG_FIELDS == (rgs.POLICY_FIELDS + rgs.STRENGTH_FIELDS + rgs.FR_FIELDS
                              + rgs.EXTRA_FIELDS)
    assert len(set(rgs.SEG_FIELDS)) == len(rgs.SEG_FIELDS)
    assert rgs.MATCH_FIELDS == ["unobserved_strength"] + rgs.FR_FIELDS


def test_child_code_is_valid_python_for_every_cell():
    for cell in rgs.policy_cells():
        ast.parse(rgs.child_code(cell, seed=1000))


def test_legacy_child_passes_only_the_strength():
    """The embed cell must take the v4 surface's strength-0 path exactly: the
    strength knob and nothing else (no policy), so its rows can string-match
    the surface's strength-0 rows."""
    legacy = next(c for c in rgs.policy_cells() if c["policy_id"] == rgs.LEGACY)
    code = rgs.child_code(legacy, seed=1000)
    assert "feature, end, depth = '', '', None" in code
    assert 'kwargs = {"unobserved_strength": 0.0}' in code


def test_every_child_runs_at_strength_zero():
    for cell in rgs.policy_cells():
        assert '"unobserved_strength": 0.0' in rgs.child_code(cell, seed=1000)


def test_reference_rows_keep_only_the_strength_zero_surface(tmp_path):
    """The v4 surface carries six strengths; only the strength-0 rows are the
    I-C1 reference, and they come back in iteration order."""
    ref = tmp_path / "surface.csv"
    ref.write_text(
        "unobserved_strength,seed,generator,iteration,x\n"
        "0.0,1000,flat,1,b\n"
        "0.7,1000,flat,0,z\n"
        "0.0,1000,flat,0,a\n"
        "0.0,1016,scm,0,c\n"
    )
    rows = rgs.reference_rows(ref)
    assert set(rows) == {("flat", 1000), ("scm", 1016)}
    assert [r["x"] for r in rows[("flat", 1000)]] == ["a", "b"]


def test_every_policy_preserves_the_approval_rate():
    import numpy as np
    from cldd.selection import knockout_rates
    for depth in set(rgs.DEPTHS) | set(rgs.PLACEBO_DEPTHS):
        rates = knockout_rates(depth, rgs.APPROVAL_RATE, rgs.N_SEGMENTS)
        assert abs(float(np.mean(rates)) - rgs.APPROVAL_RATE) < 1e-12


def test_embed_reference_artifacts_are_git_tracked():
    """artifacts/* is gitignore-default-deny: an untracked reference exists only
    on the machine that made it, so the gate would fail closed on every clone."""
    tracked = subprocess.run(
        ["git", "ls-files", "artifacts/"],
        capture_output=True, text=True, cwd=rgs.ROOT,
    ).stdout.splitlines()
    names = {Path(p).name for p in tracked}
    missing = [n for n in (rgs.SURFACE_FR.name, rgs.ENV_MANIFEST.name) if n not in names]
    assert not missing, f"sweep reads untracked artifacts: {missing}"
