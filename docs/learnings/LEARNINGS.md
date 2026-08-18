# Learnings ledger — `cldd`

Pointers only. Each row links a dated, immutable entry; evidence lives in the
entry, never here. A wrong entry is superseded by a new dated entry carrying a
`kills:` reference — entries are never edited in place.

Written solely by `/rigor:handoff` at session close.

| Date | Entry | Status | One-line |
|---|---|---|---|
| 2026-07-20 | [machine-derived hash is not a determinism baseline](2026-07-20-machine-derived-hash-is-not-a-determinism-baseline.md) | verified | A sha256 pinned on one machine encodes that machine's floats; it failed 14/15 CI jobs while passing locally. |
| 2026-07-20 | [OpenMP thread count does not explain HistGBT drift](2026-07-20-openmp-thread-count-does-not-explain-histgbt-drift.md) | refuted-assumption | The obvious thread-count hypothesis is wrong here — hash is stable 1x–8x. Don't re-spend time on it. |
| 2026-07-20 | [green CI must be checked for vacuity](2026-07-20-green-ci-must-be-checked-for-vacuity.md) | verified | The identity gate skips when the git blob is unreachable; read the skip count, not just the tick. |
| 2026-07-20 | [differential identity test is non-vacuous](2026-07-20-differential-identity-test-is-non-vacuous.md) | verified | Mutation-tested after the fixture refactor: a 1.02x default-path mutant still fails the gate. |
| 2026-07-20 | [session state records drifted from the repo](2026-07-20-session-state-records-drifted-from-the-repo.md) | verified | Carried state, `HANDOFF.md`, and the CHANGELOG were each wrong differently; nothing recorded CI was red. |
| 2026-07-20 | [adding a test invalidates every quoted suite count](2026-07-20-adding-a-test-invalidates-every-quoted-suite-count.md) | verified | 202→203 stale-ed several docs; `CLAUDE.md` was 80 tests behind. Dated snapshots stay frozen. |
| 2026-07-20 | [editable-install metadata is stale](2026-07-20-editable-install-metadata-is-stale.md) | verified | Local editable install reports 0.1.0 against `pyproject.toml` 0.3.0; reinstall at release. |
| 2026-07-20 | [no local Linux reproduction on this machine](2026-07-20-no-local-linux-reproduction-on-this-machine.md) | verified | Docker daemon down and WSL lacks `python3.12-venv`, so platform-specific CI failures cost a push cycle. |
| 2026-07-20 | [new `docs/` subdirs must be Sphinx-excluded](2026-07-20-new-docs-subdirs-must-be-sphinx-excluded.md) | verified | `docs/` is the Sphinx root under `-W`; these very ledgers would have re-broken CI unexcluded. |
| 2026-07-22 | [PyPI project JSON lags the simple index](2026-07-22-pypi-project-json-lags-the-simple-index.md) | verified | CDN cache served `latest: 0.2.0` minutes after 0.3.0 was pip-installable; verify releases via the simple index or a clean install. |
| 2026-07-22 | [PyPI metadata scrub is forward-only](2026-07-22-pypi-metadata-scrub-is-forward-only.md) | verified | Author email removed at 0.3.0; 0.1.0/0.2.0 carry it immutably and mirrored — deletion/restart assessed and rejected. |
| 2026-07-22 | [superpowers plans are locally excluded by policy](2026-07-22-superpowers-plans-are-locally-excluded-by-policy.md) | verified | `plans/` gitignored via `.git/info/exclude` (operator policy); `specs/` stay committed as provenance — don't re-flag, don't un-commit. |
| 2026-07-22 | [unanchored exclude swallowed the handoff index](2026-07-22-unanchored-exclude-swallowed-the-handoff-index.md) | verified | Root-note pattern `HANDOFF.md` matched `docs/handoff/HANDOFF.md` too — the ledger index was never committed and status never warned; anchor root-only patterns with `/`. |
| 2026-07-29 | [the seed-overlap caveat applied to only one sweep](2026-07-29-seed-overlap-caveat-applied-to-only-one-sweep.md) | verified | Part III's "consumes `s..s+7`" premise was the loop's, not the counterfactual eval's (`{s, s+1000}`) — the spaced rerun repaired the frontier but merely replicated the counterfactual; audit consumption per pipeline before claiming contamination. |
| 2026-07-29 | [the v3 raw sweep CSV was never committed](2026-07-29-v3-raw-sweep-was-never-committed.md) | verified | Gate's first CI run found `feedback_profit_sweep.csv` gitignore-denied since v3 — the "recomputes from a committed CSV" claim was clone-broken for ten days; third unexcepted-artifact incident, now mechanized by a tracked-status guard test. |
| 2026-08-18 | [a fail-closed gate with one leg that isn't](2026-08-18-fail-closed-gate-with-one-leg-that-isnt.md) | verified | I-1's frontier leg silently passes a cell absent from BOTH sides (`0 == 0`, `zip` iterates zero times); the cf leg is correctly fail-closed. Latent — reachability is blocked only incidentally by a separate completeness check. Ask every comparator what it returns on empty input. |
