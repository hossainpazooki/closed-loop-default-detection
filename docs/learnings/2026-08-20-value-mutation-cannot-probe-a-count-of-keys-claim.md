# value mutation cannot probe a count-of-keys claim

ts: 2026-08-20T17:43:58Z
commit: 9ff50a9
session: cldd-article-and design-update (Claude Code, 2026-08-20; gate-hardening execution, Tasks 4 and 6)
status: verified
fact: The per-claim mutation self-test (perturb non-key artifact values; the claim must raise or change its literals) failed for surface-run-counts - and the failure was correct: that claim counts DISTINCT RUN KEYS and quotes no measured value, so it is value-insensitive by construction, because the mutation harness deliberately preserves key columns in order to test value sensitivity rather than lookup structure. A non-vacuity probe must match what the claim protects: for a count-of-keys claim the probe is row DROP (remove one run; the quoted count must change), not value drift. The discipline is exempt-with-documented-reason plus the matching probe - never weakening the harness so the misfit case passes.
basis: full-suite run reported "FAILED tests/test_doc_numbers.py::test_claim_fires_on_artifact_value_drift[surface-run-counts]" (captured at 3082d9b + uncommitted Task-4 tree, pre-dates this entry's anchor); at 9ff50a9 the replacement probe passes: pytest tests/test_doc_numbers.py::test_surface_run_counts_fires_on_dropped_run -q -> "1 passed" (captured 17:43:58Z); the exemption reason sits in the _ARTIFACT_BACKED comment block.
re-verify: .venv/Scripts/python.exe -m pytest tests/test_doc_numbers.py::test_surface_run_counts_fires_on_dropped_run -q
