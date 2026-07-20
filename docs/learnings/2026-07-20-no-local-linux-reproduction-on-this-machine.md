---
ts: 2026-07-20T18:55:32Z
commit: 7f03f52
session: c71f1953-cab6-4134-b96b-ff17dc8098f3
status: verified
---

**fact:** This Windows machine currently has **no working local Linux
reproduction** for CI failures. Both obvious routes are broken, so a
platform-specific CI failure cannot be debugged locally — it costs a
push-and-watch cycle. This matters because the whole session's root cause was a
platform difference invisible to local runs.

**basis:**

```
$ docker info      -> daemon DOWN
   failed to connect to the docker API at npipe:////./pipe/dockerDesktopLinuxEngine
$ wsl -d Ubuntu -- python3 -c "import ensurepip"
   ModuleNotFoundError: No module named 'ensurepip'      # python3.12-venv not installed
$ wsl -d Ubuntu -- python3 --version
   Python 3.12.3
```

WSL Ubuntu *does* have git and reached the pre-v3 blob successfully
(`git show da81c98:src/cldd/feedback.py` printed), so only the venv/pip half is
missing. **Cheapest fix if this bites again:** start Docker Desktop, or
`sudo apt install python3.12-venv` inside WSL Ubuntu — either gives a real Linux
loop for the `pinned-repro` platform (`ubuntu-latest`).

**re-verify:** `docker info >/dev/null 2>&1 && echo UP || echo DOWN; wsl -d Ubuntu -- python3 -c "import ensurepip" 2>&1 | tail -1`
