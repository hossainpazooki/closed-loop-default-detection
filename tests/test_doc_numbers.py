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

import pytest

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
        "spaced-replication", "surface-verdicts", "surface-run-counts",
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


# --------------------------------------------------------------------------- #
# Per-claim artifact-mutation self-test: every artifact-backed claim must be a
# function of the data it reads. Perturb the values -> the claim must raise
# (internal asserts fire) or emit different literals. Identical literals under
# perturbed data = data-blind claim = FAIL.
# --------------------------------------------------------------------------- #

_ARTIFACT_BACKED = [
    "frontier-table-seed42",
    "counterfactual-headline",
    "frontier-distribution",
    "emp-disagreement",
    "exploration-price",
    "spaced-replication",
    "surface-verdicts",
]
# Exempt from _rows mutation, with reasons:
#   feedback-hypotheses: reads via scripts/feedback_sweep_stats.py -- covered by
#                        test_feedback_claim_fires_on_artifact_value_drift below.
#   package-version:     reads pyproject/CITATION directly; internally
#                        cross-checked (CITATION != pyproject already fails it).
#   test-count:          live pytest collection; non-vacuity demonstrated in the
#                        field (228->229 catch, 2026-08-17).
#   surface-run-counts:  counts distinct RUN KEYS, quoting no measured value, so
#                        it is value-insensitive by construction (_perturbed_rows
#                        preserves key columns on purpose). Its matching
#                        non-vacuity check is row-DROP, not value drift --
#                        test_surface_run_counts_fires_on_dropped_run below.

# Columns that identify a row rather than carry a measured value. Preserved so
# the mutation exercises VALUE sensitivity, not just lookup structure.
_KEY_COLS = {
    "seed", "generator", "iteration", "severity", "selection_severity",
    "unobserved_strength", "exploration_rate",
}


def _perturbed_rows(orig):
    def wrapper(name):
        doctored = []
        for r in orig(name):
            d = dict(r)
            for k, v in d.items():
                if k in _KEY_COLS:
                    continue
                try:
                    f = float(v)
                except (TypeError, ValueError):
                    continue
                d[k] = repr(f * 1.5 + 0.25)
            doctored.append(d)
        return doctored
    return wrapper


def _claim_fn(claim_id):
    return {cid: fn for cid, _doc, fn in cdn.CLAIMS}[claim_id]


def _fires_under_mutation(fn, monkeypatch) -> bool:
    """True iff the claim raises or changes its literals under perturbed rows."""
    baseline = fn()
    monkeypatch.setattr(cdn, "_rows", _perturbed_rows(cdn._rows))
    try:
        mutated = fn()
    except Exception:
        return True
    return mutated != baseline


@pytest.mark.parametrize("claim_id", _ARTIFACT_BACKED)
def test_claim_fires_on_artifact_value_drift(claim_id, monkeypatch):
    assert _fires_under_mutation(_claim_fn(claim_id), monkeypatch), (
        f"{claim_id}: literals identical under perturbed artifact values -- "
        "the claim is blind to the data it reads"
    )


def test_feedback_claim_fires_on_artifact_value_drift(monkeypatch):
    fss = cdn._feedback_stats_module()
    orig_load = fss.load_full_csv

    def doctored():
        df = orig_load().copy()
        num = [c for c in df.select_dtypes("number").columns if c not in _KEY_COLS]
        df[num] = df[num] * 1.5 + 0.25
        return df

    fn = _claim_fn("feedback-hypotheses")
    baseline = fn()
    monkeypatch.setattr(fss, "load_full_csv", doctored)
    try:
        mutated = fn()
    except Exception:
        return  # verdict/identity asserts fired: data-sensitive
    assert mutated != baseline, "feedback-hypotheses is blind to its CSV values"


def test_surface_run_counts_fires_on_dropped_run(monkeypatch):
    """Non-vacuity for a count-of-runs claim: drop one run key -> the quoted
    count must change (the matrix-completeness property it exists to protect)."""
    orig = cdn._rows
    fn = _claim_fn("surface-run-counts")
    baseline = fn()

    def one_run_short(name):
        rows = orig(name)
        if name != "surface_frontier.csv":
            return rows
        drop = (rows[0]["generator"], rows[0]["unobserved_strength"], rows[0]["seed"])
        return [
            r for r in rows
            if (r["generator"], r["unobserved_strength"], r["seed"]) != drop
        ]

    monkeypatch.setattr(cdn, "_rows", one_run_short)
    assert fn() != baseline, "claim did not notice a missing surface run"


def test_mutation_harness_detects_a_data_blind_claim(monkeypatch):
    """Vacuity check on the harness itself: a constant claim must NOT fire."""
    assert not _fires_under_mutation(lambda: ["static literal"], monkeypatch)


# --------------------------------------------------------------------------- #
# Verb-conditional claims: the README's qualitative language ("survives",
# "collapses to a negligible", "does not replicate") must be refused by the
# claim when the recomputed data no longer supports the verb.
# --------------------------------------------------------------------------- #

def _sign_flipped_rows(orig, col="strong_gap"):
    def wrapper(name):
        rows = [dict(r) for r in orig(name)]
        for r in rows:
            if r.get(col) not in ("", None):
                r[col] = repr(-float(r[col]))
        return rows
    return wrapper


def test_spaced_replication_refuses_survives_verb_when_effect_flips(monkeypatch):
    monkeypatch.setattr(cdn, "_rows", _sign_flipped_rows(cdn._rows))
    with pytest.raises(AssertionError, match="survives"):
        cdn.claim_spaced_replication()


def test_counterfactual_headline_refuses_verbs_when_effect_flips(monkeypatch):
    monkeypatch.setattr(cdn, "_rows", _sign_flipped_rows(cdn._rows))
    with pytest.raises(AssertionError):
        cdn.claim_counterfactual_headline()
