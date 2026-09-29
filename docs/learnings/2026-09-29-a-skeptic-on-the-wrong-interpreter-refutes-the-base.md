# a skeptic on the wrong interpreter refutes the base

ts: 2026-09-29T21:13:54Z
commit: 5f01105
session: cldd-v4-world-testing (Claude Code, 2026-09-29; transcript b9c37d75-090e-4b18-af1f-7d20606f9548)
status: verified
fact: A skeptic asked to refute "the existing identity and frozen-baseline tests pass untouched" returned REFUTED, with five failing tests named. It had re-run the suite with the machine's bare `python` (scikit-learn 1.8.0, numpy 2.4.2) and `PYTHONPATH=src`, not the repo venv (1.9.0, 2.4.6). The five are pinned float-exact tests, and they fail identically on the untouched base commit under that interpreter, which the skeptic itself reported. Its own differential, SHA-256 of both generators' cohorts and both loops at base against head, came back identical. So the verdict was about the skeptic's environment, not the change. A claim handed to a verifier must name the interpreter path, and a "refuted" that also fails on the base is a finding about the environment. The orchestrator's own rerun under the pins is what settles the clause.
basis: skeptic evidence, verbatim: "5 existing tests FAIL ... The same 5 fail with byte-identical obtained values on the pristine base tree - pre-existing library-version drift on this machine (sklearn 1.8.0 / scipy 1.17.0 / numpy 2.4.2) against frozen constants, NOT caused by the change." Orchestrator rerun on the same tree with `.venv/Scripts/python.exe -m pytest`: "307 passed, 9 skipped in 422.29s (0:07:02)". Interpreters at 5f01105: "venv 3.14.2 1.9.0 2.4.6" and "bare 3.14.2 1.8.0 2.4.2".
re-verify: .venv/Scripts/python.exe -c "import sklearn,numpy;print('venv',sklearn.__version__,numpy.__version__)"; python -c "import sklearn,numpy;print('bare',sklearn.__version__,numpy.__version__)"
