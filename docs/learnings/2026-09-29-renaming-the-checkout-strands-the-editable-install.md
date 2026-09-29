# renaming the checkout strands the editable install

ts: 2026-09-29T17:22:46Z
commit: 36752b0
session: cldd-v4-world-testing (Claude Code, 2026-09-29; transcript b9c37d75-090e-4b18-af1f-7d20606f9548)
status: verified
fact: An editable install records the absolute path of `src/` in a `.pth` file inside the venv. Renaming the checkout folder leaves that path pointing at a directory that no longer exists, so `import cldd` fails and the whole suite dies at collection. CI stays green, because CI installs fresh. The doc-number gate fails with it, and misleadingly: `test-count` reports the number of tests that still collect (73 that day) as the expected literal, which reads like doc drift and is not. After moving or renaming the checkout, run `pip install -e . --no-deps` before trusting any local gate. `--no-deps` keeps the pins where they are.
basis: at 36752b0 in the renamed folder, `cat .venv/Lib/site-packages/*.pth` showed "C:\Users\hossa\dev\closed-loop-default-detection\src"; `pytest --collect-only -q` ended "Interrupted: 18 errors during collection", every one "ModuleNotFoundError: No module named 'cldd'"; `scripts/check_doc_numbers.py` printed "FAIL test-count ... expected: `pytest` — 73 tests, all synthetic" and "DOC-NUMBER GATE: FAIL (2 of 13 claims)". After the reinstall the same tree gave 237 passed, 9 skipped, and the gate passed 13 of 13. Re-captured at 5f01105: the import resolves inside the current checkout.
re-verify: .venv/Scripts/python.exe -c "import cldd, pathlib; print(pathlib.Path(cldd.__file__).resolve())"
