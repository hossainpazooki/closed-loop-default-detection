"""Cell-enumeration tests for scripts/run_surface_sweep.py (v4 spec 4).

The driver itself is exercised by its --pilot gate (subprocess orchestration is
not unit-tested, same as run_spaced_sweeps.py); these tests pin the matrix
DEFINITION: 300 loop runs, 450 evals, the locked grids, no duplicate cells.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

_spec = importlib.util.spec_from_file_location(
    "run_surface_sweep",
    Path(__file__).resolve().parents[1] / "scripts" / "run_surface_sweep.py",
)
rss = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(rss)


def test_locked_grids():
    assert rss.STRENGTHS == [0.0, 0.2, 0.4, 0.55, 0.7, 1.0]
    assert rss.SEEDS == [1000 + 16 * i for i in range(25)]


def test_frontier_matrix_is_300_runs():
    cells = rss.frontier_cells()
    assert len(cells) == 12                      # 6 strengths x 2 worlds
    assert len(set(cells)) == 12
    assert len(cells) * len(rss.SEEDS) == 300


def test_cf_matrix_is_450_evals():
    cells = rss.cf_cells()
    assert len(cells) == 18                      # 3x4 anchors + 3x2 endpoints
    assert len(set(cells)) == 18
    assert len(cells) * len(rss.SEEDS) == 450
    for v, sev in cells:
        assert v in rss.STRENGTHS
        assert sev in (0.4, 0.6, 0.8, 1.0)
    # anchors carry the full severity curve; endpoints only {0.4, 1.0}
    assert {s for v, s in cells if v in (0.0, 0.55, 1.0)} == {0.4, 0.6, 0.8, 1.0}
    assert {s for v, s in cells if v in (0.2, 0.4, 0.7)} == {0.4, 1.0}


def test_surface_schemas_extend_spaced_schemas():
    assert rss.SURF_FR_FIELDS == ["unobserved_strength"] + rss.FR_FIELDS
    assert rss.SURF_CF_FIELDS == ["unobserved_strength"] + rss.CF_FIELDS


def test_i1_reference_artifacts_are_git_tracked():
    """The I-1 embed references (and their environment manifest) must be TRACKED.

    artifacts/* is gitignore-default-deny: an unexcepted reference exists on the
    machine that generated it and nowhere else, so the gate would fail closed on
    every clone. Same guard as tests/test_doc_numbers.py's, applied to the files
    the surface driver reads (spec Amendment Rev 1.1).
    """
    import subprocess
    tracked = subprocess.run(
        ["git", "ls-files", "artifacts/"],
        capture_output=True, text=True, cwd=rss.ROOT,
    ).stdout.splitlines()
    tracked_names = {Path(p).name for p in tracked}
    needed = [rss.SPACED_FR.name, rss.SPACED_CF.name, rss.ENV_MANIFEST.name]
    missing = [n for n in needed if n not in tracked_names]
    assert not missing, (
        f"I-1 reads untracked artifacts (add !artifacts/ exceptions + git add): {missing}"
    )
