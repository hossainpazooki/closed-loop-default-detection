# The rebuilt venv silently dropped the docs extra

ts: 2026-08-18T23:33:00Z
commit: 90cf40d
session: cldd-article-and design-update (Claude Code, 2026-08-18; captured with the Task-7 changes uncommitted in the tree; successful rebuild logged 23:38:07Z)
status: verified
fact: The venv rebuild behind the 2026-08-04 interpreter-build incident (spec Rev 1.1) reinstalled the pins but not the `[docs]` extra, so `python -m sphinx` had been locally unrunnable ever since — the sphinx `-W` gate was silently CI-only for two weeks and nobody noticed because CI stayed green. A venv rebuild narrows local gate coverage to exactly the extras you remember to reinstall; after any rebuild, re-run every local gate command in CLAUDE.md once, not just the suite. Also: `cmd | tail; echo $?` reports tail's exit, which masked the failure as SPHINX_EXIT=0 on first look — capture `${PIPESTATUS[0]}` or redirect to a file.
basis: ".venv/Scripts/python.exe -m sphinx ..." printed "No module named sphinx" while the trailing echo showed "SPHINX_EXIT=0" (the pipe's exit); `pip install -q -e ".[docs]"` then `import sphinx, sklearn, numpy` printed "sphinx 9.1.0 | pins: 1.9.0 2.4.6" (pins unchanged), and the real build wrote "build succeeded." with a directly captured exit 0 (scratch-sphinx-2026-08-18.log, mtime 23:38:07Z).
re-verify: .venv/Scripts/python.exe -c "import sphinx, sklearn, numpy; print(sphinx.__version__, sklearn.__version__, numpy.__version__)"
