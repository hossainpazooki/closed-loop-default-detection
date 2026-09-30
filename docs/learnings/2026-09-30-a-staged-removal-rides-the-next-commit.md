# a staged removal rides the next commit

ts: 2026-09-30T00:35:56Z
commit: 1c81d3e
session: cldd-v4-world-testing (Claude Code, 2026-09-29; transcript b9c37d75-090e-4b18-af1f-7d20606f9548)
status: verified
fact: The four committed design specifications were removed with `git rm`, which stages the deletion. The operator then ran a command block that added three artifact paths and committed. A commit takes the whole index, so the four deletions landed inside the artifacts commit and there is no removal commit of their own. When someone else writes the history, an assistant leaves the index empty: remove files in the working tree only, and put the `git rm` inside the command block under its own commit. Before handing over any block, run `git diff --cached --name-only` and expect it empty.
basis: `git show --name-status 90708e5` lists "M artifacts/SHA256SUMS.json", two added replication artifacts, and four "D docs/superpowers/specs/..." lines; the count of "^D" lines is 4 under the subject "feat: strength-1.0 replication artifacts and stats". The staging command ran at 2026-09-30T00:02:04Z on `43926ce`, three minutes before that commit. At capture `git diff --cached --name-only` printed 0 lines.
re-verify: git show --name-status --format="%h %s" 90708e5
