"""Content-integrity pins for tracked artifacts.

The doc-number gate checks doc<->artifact consistency; this layer checks
artifact<->manifest integrity, so a coordinated artifact+doc edit cannot pass
silently: the manifest line must change too, visibly, in review. Frozen
baselines are immutable by repo rule -- an entry change is a supersession
event and needs its own reviewed commit.

Hashes are computed over LF-normalized bytes (CRLF -> LF): git stores the
artifacts with LF in the index but Windows worktrees check them out CRLF, so
raw-byte hashes would be platform-dependent.
"""
from __future__ import annotations

import importlib.util
import json
import subprocess
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"

_spec = importlib.util.spec_from_file_location(
    "pin_artifacts", SCRIPTS_DIR / "pin_artifacts.py"
)
pin = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(pin)


def test_every_tracked_artifact_hash_matches_manifest():
    manifest = json.loads(pin.MANIFEST.read_text(encoding="utf-8"))
    current = pin.build()
    assert current == manifest, {
        "changed_or_new_on_disk": sorted(
            k for k in current if manifest.get(k) != current[k]),
        "stale_manifest_entries": sorted(k for k in manifest if k not in current),
        "hint": "legitimate additions/supersessions: rerun scripts/pin_artifacts.py "
                "and commit the manifest change with its reason",
    }


def test_manifest_is_git_tracked():
    out = subprocess.run(
        ["git", "ls-files", "artifacts/SHA256SUMS.json"],
        capture_output=True, text=True, cwd=pin.ROOT,
    ).stdout.strip()
    assert out, ("SHA256SUMS.json must be git-tracked "
                 "(needs the !artifacts/SHA256SUMS.json gitignore exception)")


def test_hash_is_line_ending_invariant(tmp_path):
    a = tmp_path / "a.csv"
    b = tmp_path / "b.csv"
    a.write_bytes(b"x,y\n1,2\n")
    b.write_bytes(b"x,y\r\n1,2\r\n")
    assert pin.lf_sha256(a) == pin.lf_sha256(b)


def test_integrity_fires_on_planted_tamper(monkeypatch, tmp_path):
    (tmp_path / "artifacts").mkdir()
    planted = tmp_path / "artifacts" / "planted.csv"
    planted.write_bytes(b"col\n1\n")
    monkeypatch.setattr(pin, "ROOT", tmp_path)
    monkeypatch.setattr(pin, "tracked_artifact_files",
                        lambda: ["artifacts/planted.csv"])
    manifest = pin.build()
    planted.write_bytes(b"col\n2\n")
    assert pin.build() != manifest, "tampered bytes must change the manifest"
