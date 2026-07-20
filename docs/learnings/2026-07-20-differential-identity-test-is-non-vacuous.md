---
ts: 2026-07-20T18:54:41Z
commit: 7f03f52
session: c71f1953-cab6-4134-b96b-ff17dc8098f3
status: verified
---

**fact:** The differential default-path identity test catches a real regression
— it is not a comparison that passes by construction. Verified by mutation
*after* the module-scoped-fixture refactor, because sharing the baseline across
tests via a fixture is exactly the kind of change that can silently make a
comparison compare a value against itself.

**basis:** injecting a subtle default-path mutant (exploration rate scaled
1.02x in `src/cldd/feedback.py`) fails the gate at HEAD `7f03f52`:

```
$ # inject: rng.random(...) < self.exploration_rate   ->   ... * 1.02
$ .venv/Scripts/python.exe -m pytest -q tests/test_feedback_flags.py
tests\test_feedback_flags.py:300: AssertionError
FAILED tests/test_feedback_flags.py::test_default_path_byte_identity_regression
$ # restored; git diff --quiet src/cldd/feedback.py -> RESTORED clean
```

Two further guards, both in `tests/test_feedback_flags.py`:
`test_pre_v3_baseline_really_is_pre_v3` asserts the reconstructed module *lacks*
`retrain`/`policy_mode` while the current one has them (so a loader that
silently returned today's code fails instead of passing tautologically); and an
unreachable blob **skips loudly** rather than passing — see
[[2026-07-20-green-ci-must-be-checked-for-vacuity]].

**re-verify:** inject the 1.02x mutant into `src/cldd/feedback.py`'s exploration mask, run `.venv/Scripts/python.exe -m pytest -q tests/test_feedback_flags.py`, confirm FAILED, then restore and confirm `git diff --quiet src/cldd/feedback.py`
