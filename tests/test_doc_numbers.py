"""Tests for scripts/check_doc_numbers.py -- the doc-number gate (assessment III.3).

This is also the gate's CI wiring: the suite runs in every CI job, so
``test_all_registered_claims_pass`` failing IS the gate firing. The remaining
tests prove the gate is not vacuous (it fires on a planted mismatch) and that
it fails closed (a missing artifact is a failure, never a silent pass).

Not ``pinned``: every recompute is closed-form over committed CSVs (means,
medians, counts, exact sign/Wilcoxon tests) -- no model training, so the
results are identical across the version matrix.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"

_spec = importlib.util.spec_from_file_location(
    "check_doc_numbers", SCRIPTS_DIR / "check_doc_numbers.py"
)
cdn = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(cdn)


def _readme_text() -> str:
    return (cdn.ROOT / "README.md").read_text(encoding="utf-8")


def test_all_registered_claims_pass():
    """The gate itself: every README figure recomputes from its artifact."""
    results = cdn.check_claims()
    failures = [r for r in results if not r["ok"]]
    assert not failures, f"doc-number gate failed: {failures}"
    # The registry must actually cover the claims it says it covers.
    assert len(results) == len(cdn.CLAIMS)


def test_gate_fires_on_planted_value_mismatch():
    """Vacuity check: corrupt one quoted figure and the matching claim must fail."""
    doctored = _readme_text().replace("positive on 24/25 seeds", "positive on 23/25 seeds")
    assert doctored != _readme_text(), "planted mismatch did not apply"
    results = {r["id"]: r for r in cdn.check_claims(doc_texts={"README.md": doctored})}
    assert not results["counterfactual-headline"]["ok"]
    assert results["counterfactual-headline"]["missing"], "should report the missing literal"
    # Unrelated claims are untouched by the plant.
    assert results["frontier-distribution"]["ok"]


def test_gate_fires_on_dropped_literal():
    """A doc rewrite that deletes a registered claim entirely must also fail."""
    doctored = _readme_text().replace("Wilcoxon p = 1.5e-7", "Wilcoxon p = small")
    results = {r["id"]: r for r in cdn.check_claims(doc_texts={"README.md": doctored})}
    assert not results["counterfactual-headline"]["ok"]


def test_gate_fails_closed_on_missing_artifact(monkeypatch, tmp_path):
    """Unevaluable != pass: with artifacts unreadable, every claim FAILS."""
    monkeypatch.setattr(cdn, "ARTIFACTS", tmp_path)  # empty dir, no CSVs
    monkeypatch.setattr(cdn, "_FSS", None)
    results = cdn.check_claims()
    # Only the claims that read artifacts/*.csv through cdn.ARTIFACTS; the
    # feedback claim resolves its CSV through feedback_sweep_stats' own path,
    # and package-version / test-count read pyproject / live collection.
    reads_artifacts_dir = {
        "frontier-table-seed42", "counterfactual-headline",
        "frontier-distribution", "emp-disagreement", "exploration-price",
    }
    artifact_backed = [r for r in results if r["id"] in reads_artifacts_dir]
    assert artifact_backed and all(not r["ok"] for r in artifact_backed)
    assert all(r["error"] for r in artifact_backed), "failure must carry the reason"


def test_gate_artifacts_are_git_tracked():
    """Every artifact the gate reads must be TRACKED, not merely present.

    artifacts/* is gitignore-default-deny; an unexcepted file exists locally
    (where the sweep ran) but not on CI/clones, where the fail-closed gate then
    fails. This catches the mismatch locally, before a push.
    """
    import subprocess
    tracked = subprocess.run(
        ["git", "ls-files", "artifacts/"],
        capture_output=True, text=True, cwd=cdn.ROOT,
    ).stdout.splitlines()
    tracked_names = {Path(p).name for p in tracked}
    missing = [n for n in cdn.ARTIFACTS_READ if n not in tracked_names]
    assert not missing, (
        f"gate reads untracked artifacts (add !artifacts/ exceptions + git add): {missing}"
    )


def test_formatting_matches_doc_conventions():
    assert cdn.sci_short(1.4901161193847656e-07) == "1.5e-7"
    assert cdn.sci_padded(2.3253e-06) == "2.3e-06"
    assert cdn.signed(-0.00276, 4) == "−0.0028"
    assert cdn.signed(0.00174, 4) == "+0.0017"
