---
ts: 2026-07-20T19:00:32Z
commit: 7f03f52
session: c71f1953-cab6-4134-b96b-ff17dc8098f3
status: verified
---

**fact:** `docs/` is the Sphinx source root and the docs gate runs `-W`
(warnings-as-errors), so **any new `docs/` subdirectory that is not a site page
must be added to `exclude_patterns` in `docs/conf.py`** — otherwise every file
in it raises `toc.not_included` and the docs job fails. Creating the
`docs/handoff/` and `docs/learnings/` ledgers in this session would have turned
CI red again, one commit after fixing it, if left unexcluded.

**basis:** with the two new directories removed from `exclude_patterns`, the
gate fails:

```
$ .venv/Scripts/python.exe -m sphinx -b html -W --keep-going docs docs/_build/html
WARNING: docs/handoff/2026-07-20-ci-portability-and-state-discrepancies.md: document isn't included in any toctree [toc.not_included]
WARNING: docs/handoff/HANDOFF.md: document isn't included in any toctree [toc.not_included]
WARNING: docs/learnings/2026-07-20-adding-a-test-invalidates-every-quoted-suite-count.md: document isn't included in any toctree [toc.not_included]
```

and with them restored it passes (`build succeeded`, 0 warnings). The repo
already carried the precedent — `superpowers` was excluded with the comment
*"design specs, not site pages"*; ledgers are the same category:

```
exclude_patterns = ["_build", ..., "RECON_FINDINGS.md", "assessment.md",
                    "superpowers", "handoff", "learnings"]
```

**Generalization:** the same trap applies to any future `docs/adr/`,
`docs/notes/`, etc. Prose that is *about* the project rather than *of* the
documentation site belongs behind an exclude.

**re-verify:** `.venv/Scripts/python.exe -m sphinx -b html -W --keep-going docs docs/_build/html` → `build succeeded`
