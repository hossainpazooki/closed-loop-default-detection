"""The README is essentials only: no dates, no run figures, no test counts.

Ruling of 2026-11-03 ("Essentials only, zero figures"): every measured result
lives in docs/results.md under the doc-number gate; the README is the tour.
These tests keep that convention mechanical.
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
README = ROOT / "README.md"

_FORBIDDEN = {
    "ISO date": re.compile(r"\b\d{4}-\d{2}-\d{2}\b"),
    "signed decimal": re.compile(r"[+\u2212-]0\.\d"),
    "test count": re.compile(r"\b\d+ tests\b"),
    "N/25 seeds": re.compile(r"\b\d+/25\b"),
    "N of 25": re.compile(r"\b\d+ of 25\b"),
}


def test_readme_carries_no_dates_or_figures():
    text = README.read_text(encoding="utf-8")
    hits = {
        label: sorted({m.group(0) for m in rx.finditer(text)})
        for label, rx in _FORBIDDEN.items()
    }
    hits = {k: v for k, v in hits.items() if v}
    assert not hits, f"README carries figures that belong in docs/results.md: {hits}"


def test_readme_relative_links_resolve():
    text = README.read_text(encoding="utf-8")
    targets = re.findall(r"\]\(([^)\s]+)\)", text)
    relative = [
        t for t in targets
        if not t.startswith(("http://", "https://", "#", "mailto:"))
    ]
    assert relative, "the README links to its docs; none found"
    missing = [t for t in relative if not (ROOT / t.split("#")[0]).exists()]
    assert not missing, f"README links to paths that do not exist: {missing}"
