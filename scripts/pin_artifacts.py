"""Write artifacts/SHA256SUMS.json: sha256 of every git-TRACKED file under
artifacts/ (manifest itself excluded), hashed over LF-normalized bytes.

Why LF-normalized: the index stores the artifacts with LF but Windows
worktrees check them out CRLF (`git ls-files --eol` shows `i/lf w/crlf`), so
raw-disk-byte hashes would differ across platforms. The hash pins content.

Discipline: frozen baselines are immutable (repo rule). Rerun this script
ONLY when adding a new artifact or executing a documented supersession; the
resulting manifest diff is the review surface. tests/test_artifact_integrity.py
fails CI whenever disk content and manifest disagree.

Usage:
    python scripts/pin_artifacts.py     # rewrites the manifest, prints count
"""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "artifacts" / "SHA256SUMS.json"


def tracked_artifact_files() -> list[str]:
    out = subprocess.run(
        ["git", "ls-files", "artifacts/"],
        capture_output=True, text=True, cwd=ROOT, check=True,
    ).stdout
    return sorted(
        p for p in out.splitlines() if p and Path(p).name != MANIFEST.name
    )


def lf_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def build() -> dict:
    return {p: lf_sha256(ROOT / p) for p in tracked_artifact_files()}


def main() -> int:
    manifest = build()
    MANIFEST.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print("wrote %s (%d entries)" % (MANIFEST.name, len(manifest)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
