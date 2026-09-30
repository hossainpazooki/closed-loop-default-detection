# Handoff — Strength-1.0 replication published; design specs moved out of the repo

*Written 2026-09-30 UTC (the evening of 2026-09-29 local) on `1c81d3e`, pushed,
level with `origin/master`, CI green. The working tree holds only this brief,
five learnings entries and the two index rows that point at them. Pick-up
measures drift from `1c81d3e`. Session: `cldd-v4-world-testing`. This brief
follows `2026-09-29-world-testing-build-landed-specs-proposed.md` and closes
its items 1 to 3.*

## Current state

- **[built, committed] The world-testing build.** Segmented-selection knob,
  two sweep drivers, two stats scripts, the manifest-overwrite fix. Landed in
  `5f01105`, `9ee84fe`, `78a6199`, `231e46f`, `22a8724`.
  re-verify: `git log --oneline 5f01105^..22a8724`
- **[built, committed] Replication judged on calibration error, six strengths.**
  The primary family is the rise in the control lever's declined calibration
  error at severity 0.4. The frontier is the secondary family. Landed in
  `f223b15`.
  re-verify: `.venv/Scripts/python.exe -m pytest tests/test_strength_replication.py -q -o addopts=""` → 31 pass
- **[built, committed] Pre-registration by digest.** `PREREGISTRATION.md`
  carries the specification's SHA-256. Landed in `43926ce`, committed
  2026-09-29T22:39:19Z.
  re-verify: `TZ=UTC git log -1 --date=format-local:%Y-%m-%dT%H:%M:%SZ --format="%h %cd" 43926ce`
- **[run, committed] The strength-1.0 replication matrix.** 300 loop runs: six
  strengths, two worlds, 25 fresh seeds `{5000 + 16i}`. 1099 rows, no
  duplicate run keys. Artifacts and the re-pinned hash manifest landed in
  `90708e5`.
  re-verify: `.venv/Scripts/python.exe -m pytest tests/test_artifact_integrity.py -q -o addopts=""` → 4 pass
- **[verified] The four verdicts.** Recomputed for this brief from the raw
  frontier file with code that does not import the repo's stats script, and
  before publication by an independent skeptic with its own code.

  | Hypothesis | World | Median | Floor | Seeds moving | Verdict |
  |---|---|---|---|---|---|
  | H-R1f, error rise at severity 0.4 | flat | +0.0515 | 0.0311 | 25 of 25 rose | confirmed |
  | H-R1s, error rise at severity 0.4 | SCM | +0.0201 | 0.0130 | 20 of 25 rose | confirmed |
  | H-R2f, frontier recession | flat | 0.2 | 0.2 | 19 receded, 6 tied, 0 advanced | confirmed on its floor |
  | H-R2s, frontier recession | SCM | 0.2 | 0.2 | 13 receded, 10 tied, 2 advanced | confirmed on its floor |

  re-verify: `.venv/Scripts/python.exe -c "import csv; [print(r['hypothesis'], r['median_stat'], r['floor'], r['sign_k'], r['sign_n'], r['confirmed']) for r in csv.DictReader(open('artifacts/strength_replication_stats.csv', newline='')) if r['metric']=='hypothesis']"`
- **[verified] What the result supports, and what it does not.** The
  confounder does not build the wall, and at full strength it moves it. The
  overlap explanation of the wall at strength 0 is untested by intervention:
  the registered reading rule does not withdraw it, and the diagnostics do not
  separate failing from passing runs within a severity. See the two 09-30
  learnings entries on the replication and on the overlap flag.
- **[built, committed] Results in the docs, claims registered.** README
  section "The strength-1.0 move, replicated on fresh seeds",
  `docs/how-it-works.md`, `docs/validation.md`, `CHANGELOG.md`. The doc-number
  gate holds 15 claims, two of them new, with a row-drop test. Landed in
  `fe37e8a`.
  re-verify: `.venv/Scripts/python.exe scripts/check_doc_numbers.py` → `DOC-NUMBER GATE: PASS (15 claims, all recomputed from artifacts)`
- **[done, committed] Every design specification and plan is out of the repo.**
  `docs/superpowers/` does not exist at the tip. The v2, v3 and v4
  specifications and the firing-evidence note stay in the history; the last
  commit that carries them is `43926ce`. Four docstrings that named the removed
  path were reworded in `1c81d3e`.
  re-verify: `git ls-tree -r HEAD --name-only | grep "^docs/superpowers"` → no output
- **[not released] The replication specification's text.** It was never
  committed. The public record is the digest alone. The digest proves a
  document existed at that date and nothing about what it says. The hypotheses,
  floors and reading rules are stated in the docstring of
  `scripts/strength_replication_stats.py`.
  re-verify: `grep -n "not released" PREREGISTRATION.md`
- **[verified] Gates on `1c81d3e`, run for this brief.** Output is in the
  Evidence section.
  re-verify: `.venv/Scripts/python.exe -m pytest -o addopts="" -q -rs` · `.venv/Scripts/python.exe -m sphinx -b html -W --keep-going docs docs/_build/html`
- **[built, not run, stale] The segmented-selection driver.**
  `scripts/run_segment_sweep.py` runs every cell at the generator's default
  confounder strength. The operator's ruling F8 sets strength 0. The driver
  has not been revised and no matrix has run.
  re-verify: `grep -n "strength" scripts/run_segment_sweep.py` → no output · `ls artifacts/segment_frontier.csv` → absent
- **[proposed] The segmented-selection specification.** A draft outside the
  repo with rulings F1 to F8 recorded at its top. Not ratified as a
  pre-registration, no digest published.
- **[planned, unchanged]** Reveal-`u` ablation; 0.4.0 release mechanics.
  `pyproject.toml` still says 0.3.0.

## Locked decisions

- **Publish the results; report both frontier verdicts as "confirmed on its
  floor", in those words.** Reason: the median recession equals the registered
  floor by exact equality on a grid of 0.2 steps, so the result carries no
  margin. The doc gate refuses the claim under any other verdict word.
- **The primary family is the calibration error at severity 0.4, the frontier
  is secondary.** Reason: the frontier is quantized to the severity grid and
  ties heavily; the error is continuous. Ruled before any fresh seed ran.
- **All superpowers documents live outside the repo, specifications included.**
  The operator's words: "leave the draft, thank you. move all superpoers to
  briefs". This overrides the ruling from earlier the same evening to keep the
  four committed specifications. Reason given by the operator: none beyond the
  instruction. Do not move them back.
- **The replication specification file is byte-frozen.** Reason: any edit
  breaks the match with the published digest.
- **The overlap explanation is worded as untested by intervention.** Reason:
  the flag and the failure both rise with severity, so their co-occurrence
  cannot show cause.
- **Segmented selection is held until after the essay, and runs at strength 0
  when it runs.** Reason for the hold: the operator's order of work. Reason for
  strength 0: ruling F8, which isolates the selection policy from the
  confounder.
- **The essay draft is left as it is.** The operator's word. It lives outside
  the repo. No session edits it without a new instruction.
- **History is not rewritten.** Two commits read differently from their
  content, listed under Invariants. Reason: the repo is public and the tree at
  the tip states the true position.
- **Carried from the previous brief and still in force:** fresh seeds are
  `{5000 + 16i}` and are now spent; `{1000 + 16i}` is spent; pilots run on a
  spent seed; functions that write take their target as a required argument; a
  suffixed manifest gets a suffixed file.

## Reuse map

- `scripts/run_strength_replication.py` — the v4 surface child plus one
  inserted block that records the overlap diagnostics per row. It refuses to
  build the child if the insertion anchor does not occur exactly once.
- `scripts/strength_replication_stats.py` — two Holm families of two, effect
  floors, an `Unevaluable` verdict when the baseline is already over target or
  fewer than 20 pairs exist, and a spent-seed guard that checks the span a run
  consumes and not only its base seed. This closes reviewer finding 1 of the
  previous brief.
- `scripts/check_doc_numbers.py` — `claim_strength_replication` shows how to
  register a verdict whose wording depends on the data.
  `claim_replication_run_counts` with its row-drop test shows the non-vacuity
  probe for a count-of-keys claim.
- `PREREGISTRATION.md` — the digest record format and the one-line command
  that reproduces a digest. Reuse it for the segmented-selection
  specification.
- `scripts/feedback_sweep_stats.py` — `sign_test`, `wilcoxon_test`,
  `holm_adjust`. One implementation for every analysis.
- `src/cldd/selection.py` — `knockout_rates` and `validate_policy`, unchanged
  since the previous brief.

## Invariants

- **No matrix without a published digest and an explicit go.** A fresh seed is
  spent when it runs. The segmented-selection seeds are not yet spent.
- **`artifacts/strength_replication_*.csv` are frozen.** They are hash-pinned.
  Rerunning the driver or the stats script over them is a supersession and
  needs a documented reason.
- **Never call `scripts/pin_artifacts.py` to inspect anything.** It has no
  argument parser and rewrites the manifest on every call. Check pins with
  `tests/test_artifact_integrity.py`.
- **Read the position from the tree, not the log.** The subject of `fe37e8a`
  says "released spec" and no specification was released. The four
  specification removals sit inside `90708e5`, whose subject names only
  artifacts.
- **Leave the index empty.** The operator writes the history here. A staged
  change rides into whatever they commit next.
- **The v4 specification is cited by a history permalink at `43926ce`.** Do
  not cite `docs/superpowers/` as a live path anywhere in the docs.
- **Dated ledger entries keep their old paths.** Earlier briefs and learnings
  entries name `docs/superpowers/...`. They were true when written.
- **Run everything with `.venv/Scripts/python.exe`.** The machine's bare
  `python` is off the pins and fails five pinned tests on any commit.
- **A new test file ends with a count re-sync.** The README and
  `docs/validation.md` say 331.
- Three older learnings entries fail `check-learnings` on format. They were
  failing before this session, they are immutable, and they were left alone.
  The five entries added here pass.

## Open / next

1. **Operator: commit this brief and the five learnings entries.** Command
   block in the session close-out.
2. **Essay, outside the repo.** The operator converges the draft. Two
   statements in the current draft are no longer true: that the specification
   text is released in the pinned commit, and that the v4 specification is in
   the repository. Its pin should move to the commit it is published against.
   No session touches the draft without an instruction.
3. **Operator ruling still open: release the replication specification or
   keep it private.** Until it is released, a reader can check the date of the
   pre-registration and not its content. The instruction to move everything
   out came after the ruling to release; the docs follow the later one.
4. **Segmented selection, after the essay.** Revise the driver for strength 0
   first. The legacy cell's byte-identity reference then moves to the
   strength-0 rows of `artifacts/surface_frontier.csv`. Then freeze the
   specification, publish its digest, run the pilot on a spent seed, and ask
   for the go. 16 cells by 25 seeds is 400 runs.
5. **Reveal-`u` ablation.** Its precondition is met: the strength-1.0 move
   replicated. Run it at strength 1.0. Not specified, not planned in detail.
6. **Reviewer findings carried, not fixed:** an inclusive cutoff can fund a
   segment slightly above its rate on tied scores; the SCM cohort's generator
   back-reference gains an attribute, so a pickle of the whole cohort object
   is not byte-identical although the generated data is.
7. **Local only:** the untracked `CLAUDE.md` still quotes 209 tests. The nine
   fidelity tests skip because the private dataset path is not set on this
   machine.

## Evidence

Order of registration and run. The digest commit `43926ce` is dated
2026-09-29T22:39:19Z. The matrix was launched at 22:40:40Z and the frontier
file was last written at 23:20:54Z. The launch time comes from the session's
own record and the write time from the file's modification time on the
operator's machine. No committed file carries either. The commit order shows
the digest was published before the artifacts were; it cannot by itself show
the run began after the digest.

Digest check, 2026-09-30T00:34Z, against the privately held specification:

```
e2929493b3ea6ba0d6563f34bcc847bb8d61d66d4745606f8e8ab4abd119459d
```

It matches the value in `PREREGISTRATION.md`.

Independent recompute from `artifacts/strength_replication_frontier.csv`,
2026-09-30T00:34:08Z on `1c81d3e`:

```
rows 1099
runs 300
seeds 25 min 5000 max 5384 registered True
flat baseline median E_w(0.0) at sev 0.4 = 0.0689 gap to 0.10 target = 0.0311
   flat strength 0.2 median diff 0.0042 rising 15 of 25
   flat strength 0.4 median diff 0.0131 rising 19 of 25
   flat strength 0.55 median diff 0.0273 rising 22 of 25
   flat strength 0.7 median diff 0.0265 rising 24 of 25
   flat strength 1.0 median diff 0.0515 rising 25 of 25
   flat frontier recession 0.0 -> 1.0: median 0.2 receded 19 tied 6 advanced 0
   flat strength 0: flagged at the failing severity 24 of 25
scm baseline median E_w(0.0) at sev 0.4 = 0.0870 gap to 0.10 target = 0.0130
   scm strength 0.2 median diff -0.0049 rising 10 of 25
   scm strength 0.4 median diff -0.0006 rising 12 of 25
   scm strength 0.55 median diff 0.0040 rising 17 of 25
   scm strength 0.7 median diff 0.0119 rising 17 of 25
   scm strength 1.0 median diff 0.0201 rising 20 of 25
   scm frontier recession 0.0 -> 1.0: median 0.2 receded 13 tied 10 advanced 2
   scm strength 0: flagged at the failing severity 17 of 25
```

Median frontier by strength, same run. Flat: 0.4 at every strength below 1.0,
then 0.2. SCM: 0.4 through strength 0.55, then 0.2 at 0.7 and 1.0. On the
spent seeds the SCM median moved only at 1.0, so that detail of the v4 reading
belongs to the spent draw.

Gates on `1c81d3e`:

```
full suite, started 2026-09-30T00:33:38Z: 322 passed, 9 skipped in 302.22s (0:05:02), exit 0
  all nine skips are tests/test_fidelity.py, "real dataset not found"
DOC-NUMBER GATE: PASS (15 claims, all recomputed from artifacts)
sphinx -W --keep-going: exit 0
tests/test_artifact_integrity.py: 4 passed
check-learnings: 21 failures, all in three entries dated 2026-07-29 and 2026-08-18; none in the 2026-09-30 entries
CI on 1c81d3e, fe37e8a, 43926ce: success
```
