"""The spaced driver must never write over the committed environment manifest.

``artifacts/surface_env.json`` is a committed, hash-pinned record of the build
the I-1 baselines were produced under. ``--out-suffix NAME`` used to rewrite it
in place while its help text promised the originals were never touched. These
tests pin the repaired behavior: a suffixed run writes a suffixed manifest.

No sweep is executed (the run functions are stubbed), so NOT ``pinned``.
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

_spec = importlib.util.spec_from_file_location(
    "run_spaced_sweeps",
    Path(__file__).resolve().parents[1] / "scripts" / "run_spaced_sweeps.py",
)
rsp = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(rsp)


def test_suffixed_manifest_gets_its_own_file():
    target = rsp._suffixed(rsp.ENV_MANIFEST, "mine")
    assert target.name == "surface_env_mine.json"
    assert target != rsp.ENV_MANIFEST


def test_write_env_manifest_has_no_default_target():
    """No implicit target: a caller cannot overwrite the committed manifest by
    forgetting an argument."""
    with pytest.raises(TypeError):
        rsp.write_env_manifest()


def test_suffixed_run_leaves_the_committed_manifest_untouched(tmp_path, monkeypatch):
    committed = tmp_path / "surface_env.json"
    committed.write_text('{"sentinel": "committed record"}\n', encoding="utf-8")
    before = committed.read_bytes()

    monkeypatch.setattr(rsp, "ENV_MANIFEST", committed)
    monkeypatch.setattr(rsp, "CF_OUT", tmp_path / "seed_sweep_spaced.csv")
    monkeypatch.setattr(rsp, "FR_OUT", tmp_path / "frontier_sweep_spaced.csv")
    written = []
    monkeypatch.setattr(rsp, "run_counterfactual", lambda out: written.append(out.name))
    monkeypatch.setattr(rsp, "run_frontier", lambda out: written.append(out.name))
    monkeypatch.setattr(sys, "argv", ["run_spaced_sweeps.py", "--out-suffix", "mine"])

    rsp.main()

    assert committed.read_bytes() == before
    mine = json.loads((tmp_path / "surface_env_mine.json").read_text(encoding="utf-8"))
    assert {"python_version", "python_build", "numpy", "scikit_learn"} <= set(mine)
    assert written == ["seed_sweep_spaced_mine.csv", "frontier_sweep_spaced_mine.csv"]
