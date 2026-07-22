# Handoff index — `cldd`

Pointers only. Each row links a dated, immutable brief; state and evidence live
in the brief, never here. A later session writes a **new** entry — entries are
never edited once written.

Written by `/rigor:handoff`; read by `/rigor:pickup`, which re-verifies a
brief's claims rather than trusting them.

> Note: the repo-root `HANDOFF.md` is a separate, local-only (untracked) working
> note kept via `.git/info/exclude`. This directory is the durable ledger.

| Date | Brief | Newest commit | One-line |
|---|---|---|---|
| 2026-06-26 | [hackathon-era session handoff (relocated 2026-07-22)](2026-06-26-session-handoff-hackathon-era.md) | — | Pre-ledger provenance note moved out of the repo root at public release; machine paths / dataset location / visibility redacted, all figures frozen. |
| 2026-07-20 | [CI portability fix and the day's state discrepancies](2026-07-20-ci-portability-and-state-discrepancies.md) | `7f03f52` | `master` was red for a day from a machine-derived hash baseline; replaced with a differential in-process identity test, CI green 15/15 and checked for vacuity. |
| 2026-07-22 | [v0.3.0 released; v3 closed out](2026-07-22-v0.3.0-released.md) | `1ab178b` | 0.3.0 live on PyPI and effect-verified from a clean venv (discriminating v3-flags probe); author email dropped forward-only; next work is spec §9 Option A/C. |
| 2026-07-22 | [v4 entry: Option A frontier surface](2026-07-22-v4-entry-option-a.md) | `3be6c06` | Starting ground for v4 — what Option A is (`unobserved_strength` × severity surface), inherited locks, reuse map; nothing built; first action is the adversarial spec. |
