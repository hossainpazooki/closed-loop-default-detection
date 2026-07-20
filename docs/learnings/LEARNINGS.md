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
