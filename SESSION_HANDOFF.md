# Session Handoff — closed-loop-default-detection

> Orientation note for the next session. It carries **only** what isn't already in
> the reference docs: current state, what's unverified, and the non-obvious design
> facts. For anything empirical, follow the link — **do not restate numbers here**
> (a second copy is what drifts).

| You want… | Read… |
|---|---|
| What the project is, install, API, CLI drivers, config, repo structure | `README.md` |
| The §3 causal result and **all** counterfactual / seed-sweep numbers | `FABLE.md` (the authority; has a seed-42 cross-check section) |
| Rendered API reference / quickstart | `docs/` (Sphinx) |
| How to contribute, dev setup | `CONTRIBUTING.md` |

Repo: `hossainpazooki/closed-loop-default-detection` (**private**, branch `master`).
Local: `C:\Users\hossa\dev\closed-loop-default-detection`. Python venv at
`.venv/Scripts/python.exe`.

---

## Current state (2026-06-26)

- **Tests green, determinism holds.** Run `pytest` for the authoritative count and
  module breakdown (pinned sklearn 1.9.0; the pin matters — three HistGBT tests are
  float-sensitive across sklearn releases). Last green run: **90 passed**.
- **The closed loop, SCM + fidelity gate, and counterfactual validator are built and
  working** — see README "How the closed loop works" and `FABLE.md` for the results.
- **Both §3 causal gaps are closed** (bank-feed propagation trap + a deployable
  g-computation estimator replacing the oracle comparison). Numbers and significance
  live in `FABLE.md`; the committed evidence is `artifacts/seed_sweep_25.csv` and
  `artifacts/paired_significance.csv`.
- **Post-hackathon "close the loop" work** (exploration lever, `FeedbackLoop`,
  observable positivity diagnostics) is built and measured in the two synthetic
  worlds only — see README + `FABLE.md`.

## What is NOT verified

- **The fidelity gate has not been re-run here** — it needs the real Intuit
  `train.csv`, which is absent from this checkout. The "fidelity PASSED" claims
  elsewhere are carried over from a prior session, not reconfirmed. Real Intuit data
  lives in the hackathon repo at `…/intuit-techweek-nyc-hackathon-2026/dataset/`
  (`train.csv`, `validation.csv`, `test.csv`, `data_dictionary.csv`,
  `intervention_queries.csv`); pass that directory explicitly to the fidelity
  functions on another machine.

---

## Non-obvious design facts (the reason this note exists)

- **Two generators coexist on purpose.** `synthetic.py` (`SyntheticBorrowerGenerator`)
  is the original flat single-layer generator the selective-labels **loop** runs on.
  `scm.py` (`StructuralBorrowerGenerator`) is the newer fitted, layered causal model
  used by the **fidelity gate** and the **counterfactual** validator. `scm.py` was
  added **additively**: its `generate_cohort()` returns a *superset* of the loop's
  cohort contract, so `SelectiveLabelsLoop` can be pointed at it later without
  breaking anything. Keep that contract stable.
- **Design stance for `do()` (Deliverable D §3):** propagate the *manipulable* gating
  node (`do(has_linked_bank_feed=…)` regenerates the whole bank-feed block); keep
  genuinely non-manipulable identity nodes (`sector`, `vintage_years`) as
  "do() refused / ill-defined."
- **Scope:** this repo is a **validation harness**. It does not produce or alter the
  challenge's A/B/C submission files. Wiring its conclusions (IPW correction,
  disclosed frontier, counterfactual method) into the real submission is a separate
  step.

## Invariants to preserve

- **Determinism:** byte-identical per seed; all randomness through one seeded
  `numpy.random.Generator` (exploration draws use dedicated seeded streams so the
  generator PCG64 streams stay untouched — the frozen-baseline test asserts exact
  float equality).
- **No-leakage:** the retrain lever fits on a disjoint cohort (`TRAIN_SEED_OFFSET`);
  the naive PD model is fit on approved rows only.
- **Cohort contract:** `scm.py` must keep returning the loop-compatible superset dict.
- **Fidelity gate is the guard:** any change to marginals must keep
  `check_fidelity.py` green, or the tolerances must be revisited deliberately.
