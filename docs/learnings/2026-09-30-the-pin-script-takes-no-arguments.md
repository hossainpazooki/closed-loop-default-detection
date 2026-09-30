# the pin script takes no arguments

ts: 2026-09-30T00:36:04Z
commit: 1c81d3e
session: cldd-v4-world-testing (Claude Code, 2026-09-29; transcript b9c37d75-090e-4b18-af1f-7d20606f9548)
status: verified
fact: `scripts/pin_artifacts.py` has no argument parser. Any invocation rewrites `artifacts/SHA256SUMS.json`, including one that passes `--help`. It was called with `--help` to read its usage and it rewrote the manifest. The content came out identical because no artifact had changed. Had one drifted, the call would have re-pinned the drift and turned the integrity test green over it. To check the pins, run the integrity test, which only reads. Read a script's source before passing it a flag it may not have.
basis: at 2026-09-30T00:16:56Z on `fe37e8a`, `scripts/pin_artifacts.py --help` printed "wrote SHA256SUMS.json (24 entries)", and `git diff --quiet HEAD -- artifacts/SHA256SUMS.json` then exited 0. Re-captured at `1c81d3e` without running the script: `grep -n "argparse\|sys.argv\|write_text" scripts/pin_artifacts.py` printed only "48:    MANIFEST.write_text(", and `pytest tests/test_artifact_integrity.py` printed "4 passed in 0.55s".
re-verify: grep -n "argparse\|sys.argv\|write_text" scripts/pin_artifacts.py
