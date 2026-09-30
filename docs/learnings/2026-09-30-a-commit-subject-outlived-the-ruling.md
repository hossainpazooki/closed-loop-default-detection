# a commit subject outlived the ruling

ts: 2026-09-30T00:36:02Z
commit: 1c81d3e
session: cldd-v4-world-testing (Claude Code, 2026-09-29; transcript b9c37d75-090e-4b18-af1f-7d20606f9548)
status: verified
fact: The subject of `fe37e8a` says "released spec". No specification is in that commit or in its tree, and the files it carries say the text is held outside the repository and not released. The subject came from a command block written while the ruling was to release the text; the ruling changed, the files were reworded, and the block's subject line was not. The log is wrong and the tree is right. Read `PREREGISTRATION.md` for the position, not the log. When a ruling changes after a command block is handed over, reissue the whole block, subjects included.
basis: `git log -1 --format=%s fe37e8a` printed "docs: replication results, released spec, registered claims"; `git show fe37e8a:PREREGISTRATION.md | grep -n "not released"` printed "28:| Text | held outside this repository; not released |"; the commit's file list has 0 paths containing "superpowers" and its tree has 0 paths containing "replication-design".
re-verify: git log -1 --format=%s fe37e8a && git show fe37e8a:PREREGISTRATION.md | grep -n "not released"
