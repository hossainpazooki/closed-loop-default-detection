"""Tests for scripts/check_preregistration.py -- the pre-registration gate.

The gate's CI wiring is test_every_registered_specification_is_released_and_matches;
the other tests prove the gate is not vacuous and fails closed.
"""
from __future__ import annotations

import importlib.util
import shutil
import subprocess
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
_spec = importlib.util.spec_from_file_location(
    "check_preregistration", SCRIPTS_DIR / "check_preregistration.py"
)
cpr = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(cpr)


def _copy_tree(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    root.mkdir()
    shutil.copy(cpr.ROOT / "PREREGISTRATION.md", root / "PREREGISTRATION.md")
    shutil.copytree(cpr.ROOT / "preregistration", root / "preregistration")
    return root


def test_every_registered_specification_is_released_and_matches():
    lines = cpr.check(cpr.ROOT)
    names = {ln.split(":")[0] for ln in lines}
    assert names == {
        "2026-09-29-cldd-strength-1.0-replication-design.md",
        "2026-11-03-cldd-option-c-segmented-selection-design.md",
    }
    assert all(ln.endswith("digest matches") for ln in lines)


def test_released_specifications_are_git_tracked():
    tracked = subprocess.run(
        ["git", "ls-files", "preregistration/"],
        capture_output=True, text=True, cwd=cpr.ROOT,
    ).stdout.splitlines()
    tracked_names = {Path(p).name for p in tracked}
    registered = {name for name, _ in cpr.registered_specifications(cpr.ROOT)}
    missing = sorted(registered - tracked_names)
    assert not missing, f"released texts are not git-tracked (git add them): {missing}"


def test_digest_check_fires_on_a_one_byte_mutation(tmp_path):
    root = _copy_tree(tmp_path)
    name, _ = cpr.registered_specifications(root)[0]
    path = root / "preregistration" / name
    data = bytearray(path.read_bytes())
    data[len(data) // 2] ^= 0x01
    path.write_bytes(bytes(data))
    with pytest.raises(AssertionError, match=name):
        cpr.check(root)


def test_digest_check_fires_on_a_missing_text(tmp_path):
    root = _copy_tree(tmp_path)
    name, _ = cpr.registered_specifications(root)[1]
    (root / "preregistration" / name).unlink()
    with pytest.raises(AssertionError, match=f"{name}: registered but not released"):
        cpr.check(root)


def test_registry_parser_fails_closed_on_a_row_without_a_digest(tmp_path):
    root = _copy_tree(tmp_path)
    reg = root / "PREREGISTRATION.md"
    text = reg.read_text(encoding="utf-8")
    first_sha = next(cpr._SHA_ROW.finditer(text))
    reg.write_text(text[: first_sha.start()] + text[first_sha.end():], encoding="utf-8")
    with pytest.raises(AssertionError, match="has no SHA-256 row"):
        cpr.registered_specifications(root)
