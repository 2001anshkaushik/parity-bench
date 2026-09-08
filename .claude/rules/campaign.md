---
description: How this repository is operated — read before any work here, whatever the task
globs: ['**/*']
---

# parity-bench — operating rules (one copy; `.github/copilot-instructions.md` is identical)

This is a PUBLIC repository and every number in it is evidence. Before doing anything, read, in order:

1. `working/docs/AUTOMATION_CONTRACT.md` — how we operate: GREEN / AMBER / RED tiers, the gates, the self-audit block every task ends with.
2. `working/docs/DOCS_HANDOFF.md` — the document-workload re-run: what is settled, what is open, what may never be quoted.
3. `working/video/METHODOLOGY_REGISTER.md` — 35 entries, the ways this campaign has already been wrong. Consult it before designing anything.

Non-negotiable, whichever agent you are:

- **Pushes go through `working/harness/autoland.sh`** — explicit paths, seven fail-closed gates, `ls-remote` read-back. Never `git push` by hand, never `--force`, never rewrite history.
- **Box commands go through `working/harness/box.sh`** (`run` / `launch`, single-line, `--start` opt-in). Never paste a command into an SSM session by hand. On the box the interpreter is `~/.venv/bin/python`; on the laptop it is `../.venv/bin/python` — prove it by importing psutil, never by a path existing.
- **`working/results/` is append-only.** Never modify, rename or delete an existing artifact. New artifacts are fine.
- **Never quote a withdrawn figure uncaveated** — `figure_guard.py` enforces the list in `DOCS_HANDOFF.md` §3.6; a figure labelled `[UNVERIFIED — no artifact; do not quote]` is not quotable.
- **Nothing reaches a person from an autonomous run** — no issues, PRs, messages, or published copy. Draft; do not send.
- **A green run is a claim about the paths it ran.** Every checker carries a null control that must fail. Anything not explicitly reported as done is PENDING.

The RocketRide SDK writes its own generated doc pointer into `.claude/rules/rocketride.md` (a `ROCKETRIDE:BEGIN … END` block pointing at the untracked `.rocketride/docs/`). That file is local tool output, gitignored, and not a campaign rule.
