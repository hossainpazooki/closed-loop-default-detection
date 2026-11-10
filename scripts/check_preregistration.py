"""Pre-registration gate: every specification registered by digest in
PREREGISTRATION.md is released under preregistration/ and its LF-normalised
SHA-256 equals the registered one.

A digest committed before an experiment ran proves a document existed at that
date. Releasing the text and recomputing the digest on every CI run lets any
reader check that the released text is that document. Fail-closed: a registered
name with no digest row, a missing file, or a mismatch is a failure.

Usage:
    python scripts/check_preregistration.py    # exit 0 iff every digest matches

Wired into CI via tests/test_preregistration.py.
"""
from __future__ import annotations

import importlib.util
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

_pin_spec = importlib.util.spec_from_file_location(
    "pin_artifacts", Path(__file__).resolve().parent / "pin_artifacts.py"
)
_pin = importlib.util.module_from_spec(_pin_spec)
_pin_spec.loader.exec_module(_pin)
lf_sha256 = _pin.lf_sha256

_SPEC_ROW = re.compile(r"^\| Specification \| `([^`]+)` \|\s*$", re.MULTILINE)
_SHA_ROW = re.compile(r"^\| SHA-256 \| `([0-9a-f]{64})` \|\s*$", re.MULTILINE)


def registered_specifications(root: Path) -> list[tuple[str, str]]:
    """(name, sha256) for every Specification row, each paired with the SHA-256
    row that follows it. Fail-closed on a Specification row with no digest."""
    text = (root / "PREREGISTRATION.md").read_text(encoding="utf-8")
    out: list[tuple[str, str]] = []
    for m in _SPEC_ROW.finditer(text):
        nxt = _SPEC_ROW.search(text, m.end())
        window = text[m.end(): nxt.start() if nxt else len(text)]
        sha = _SHA_ROW.search(window)
        assert sha, f"PREREGISTRATION.md: specification {m.group(1)!r} has no SHA-256 row"
        out.append((m.group(1), sha.group(1)))
    assert out, "PREREGISTRATION.md registers no specification"
    return out


def check(root: Path) -> list[str]:
    lines = []
    for name, registered in registered_specifications(root):
        path = root / "preregistration" / name
        assert path.exists(), f"preregistration/{name}: registered but not released"
        actual = lf_sha256(path)
        assert actual == registered, (
            f"preregistration/{name}: digest mismatch\n"
            f"  registered {registered}\n  recomputed {actual}"
        )
        lines.append(f"{name}: digest matches")
    return lines


def main() -> int:
    try:
        lines = check(ROOT)
    except AssertionError as exc:
        print("PREREGISTRATION GATE: FAIL")
        print(str(exc).encode("ascii", "backslashreplace").decode("ascii"))
        return 1
    for ln in lines:
        print("PASS  " + ln)
    print(f"PREREGISTRATION GATE: PASS ({len(lines)} specifications, every digest matches)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
