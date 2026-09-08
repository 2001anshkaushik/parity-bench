# AUTOMATION CONTRACT — how the docs re-run operates

**Repo path:** `working/docs/AUTOMATION_CONTRACT.md`
**Branch:** `video-bench` (travels to `docs-bench` unchanged)
**Companion to:** `working/docs/DOCS_HANDOFF.md` — read that first for the campaign; this file is how the campaign *runs*.
**Written:** 2026-09-07. Supersedes the manual-approval-on-every-push working mode.

---

## §1. The ruling

Manual approval on every push is **retired**. It is replaced by mechanical gates, not removed.

The reason the old rule existed is worth stating precisely, because the replacement is designed against it. It was never about merge conflicts — `2001anshkaushik/parity-bench` has one contributor. It is that the repo is **PUBLIC**, made so on 14 Aug precisely so Leela and Shashi could clone it without a token, and they do. The risk is a withdrawn figure becoming quotable by a colleague acting in good faith.

That risk is a **text search**. A text search is a better checker than a human reading a diff at 2am. So the gate moves from attention to code, and gets stricter in the process.

### Actions tier by reversibility, not visibility

**GREEN — fully autonomous, no gate, no announcement.**
Anything that stays on the laptop: builds, tests, analysis, writing and editing files, local commits, reading artifacts. Reads on the box (`ls`, `cat`, `docker inspect`, `git log`, log tails).

**AMBER — autonomous behind a mechanical gate.**
- Pushes to `origin` → gate is `working/harness/autoland.sh`.
- Box writes and runs → gate is `working/harness/box.sh` (refusal list, transcript, session hygiene) plus the campaign preflight (§4).

No human in the loop. The gate either passes or the action does not happen.

**RED — stops for Ansh. Exactly three. Do not extend this list without a ruling; do not shrink it either.**

1. **Deleting or modifying an existing measurement artifact or image.** Anything already committed under `working/results/`; the images `rr:patched` (`sha256:073b43d8…`), `rr:stock` (`sha256:5e83c803…`), `ws1-llamaindex:x86_64` (`sha256:3d2f1f43…`), `rr:patched-video`; any S3 object under `s3://rocketride-benchmark-data/ansh/`.
   *Why:* none are bit-reproducible and every published number rides them. **New artifacts are GREEN — the rule is append-only, not read-only.** `autoland.sh` gate 1 enforces this mechanically; `box.sh`'s refusal list covers the images.

2. **`git push --force`, branch deletion, history rewrite.**
   *Why:* one command loses the campaign, and no gate can un-lose it. `autoland.sh` never passes `--force` and will not construct one.

3. **Anything that reaches a person.** A Slack message, a GitHub issue or PR body, an email to Leela or Shashi, published copy.
   *Why:* the failure mode is not technical. A correction to a colleague is a social act with a social cost, and a script cannot judge tone or timing.
   *Live instance:* the provenance correction owed to Leela (`DOCS_HANDOFF.md` §2.4) is item 3. Draft it; do not send it.

**Everything not on the red list is automated.** If an action feels risky but is not on the list, the correct response is to propose adding it with a reason — not to quietly ask for permission, which reintroduces the bottleneck this contract removes.

---

## §2. The gates

### `working/harness/autoland.sh`

One command that commits, gates, pushes and **proves the landing**. Seven gates, all fail-closed, in order:

| # | Gate | Refuses when |
|---|---|---|
| 0 | branch shape | detached HEAD; origin unreachable; the index already dirty (never folded in, never discarded); no explicit paths; `origin/<branch>` not an ancestor of HEAD (a **claimed base**, entry 26) |
| 0b | **single-source files** | a file in the single-source list diverges between this branch and the other campaign branch in the wrong direction (§2a below) |
| 1 | **append-only** | anything but `A` staged under `working/results/` (`M`, `D`, `R`, `T`, `C`) |
| 2 | static names | `static_names.py` (imported, never run as a script) flags an undefined name in changed python; staged deletions are skipped, not crashed on |
| 3 | suite | a failure **not in** `suite_baseline.json`; a baselined failure that now **passes** (update the baseline deliberately); a runner that did not print its summary; **more skips than `max_skipped`** — a skipped test is a path the suite did not run (entry 27); or the runner/baseline **absent** (a missing gate is not a passing gate) |
| 4 | figure guard | its own null control does not fire, or a never-quote figure is uncaveated in any prose the push makes public (index vs. `origin/<branch>`, else the merge-base with `origin/video-bench`, else `origin/main`, else HEAD — printed) |
| 5 | **commit message**, then commit | the message carries an uncaveated never-quote figure — refused **before** the commit exists, because a message is public, permanent and never rewritten |
| 6 | push | never `--force`; the first push of a branch sets its upstream |
| 7 | **ls-remote read-back** | `origin` does not report the sha we just built |

Every gate has a null control in `working/harness/autoland_selftest.sh` (`autoland.sh --self-test`): a throwaway repo with a local bare origin, each gate driven to refuse its seeded case and to pass its clean twin. The interpreter is **proven** by importing psutil (`$PYBIN`, then `<repo>/../.venv/bin/python` — the laptop — then `~/.venv/bin/python` — the box); a path that exists is not evidence.

### §2a. Branches and single-source files

**Two campaign branches, one direction.** `video-bench` is the films/harness branch; `docs-bench` is the document re-run. **Merges go `video-bench` → `docs-bench` only, as an as-is merge after a mechanical path-overlap check — never the reverse.** Docs work must not reach the films branch. A harness change is made on `video-bench` and merged forward; a docs change stays on `docs-bench`. Neither branch is rebased.

**Single-source files** (the list is `SINGLE_SOURCE_*` in `autoland.sh`; gate 0b enforces it):

* `working/docs/AUTOMATION_CONTRACT.md` — **must be byte-identical** on both branches. On `video-bench` (the source) the other branch may only be *behind* (its copy is a version already in `video-bench`'s history — merge forward to converge); on `docs-bench` or any other branch the copy must equal `origin/video-bench`'s exactly. Edit it on `video-bench`; never on `docs-bench`.
* `working/docs/DOCS_HANDOFF.md` — **canonical on `docs-bench` only.** Every other branch carries a marked stub whose first line is `<!-- DOCS_HANDOFF_STUB: the document lives on docs-bench -->`, so no prose on the wrong branch can be mistaken for the briefing. Gate 0b refuses a stub on `docs-bench` and refuses non-stub prose anywhere else. (Ruled 2026-09-08 after a fresh session cloning `video-bench` read the stale 7-Sep text; the earlier "land the handoff on video-bench" instruction was transitional and outlived its transition.)

Adding a file to the list is a `video-bench` edit of `autoland.sh` plus a null control in the self-test, then a merge forward.

Gate 7 is register entry 26 made mechanical. Previously the read-back was a separate command a human remembered to run; now "pushed" and "landed" cannot diverge, because the script exits non-zero unless origin agrees.

```bash
working/harness/autoland.sh "commit message" path [path ...]   # explicit paths, always
working/harness/autoland.sh --dry-run "msg" path [path ...]     # every gate, no commit/push
working/harness/autoland.sh --verify                            # is HEAD landed on origin?
working/harness/autoland.sh --self-test                         # the null controls
```

There is no all-files mode: a `git add -A` once swept ~170 local run records into this public repo. `--verify` answers "am I actually landed?" by the same ls-remote read-back.

### `working/harness/figure_guard.py`

Scans changed prose for the never-quote figures enumerated in `DOCS_HANDOFF.md` §3.6. A pattern firing is **not** a failure; firing **without a caveat marker within 6 lines** is. The handoff itself therefore passes — it caveats all of them, which is why they appear in it — while a fresh report writing "RocketRide is 6.9x lighter" is refused.

Nine patterns. `--null-control` seeds a file with every banned figure uncaveated and asserts the gate refuses it, exiting 3 if the gate fails to fire; it also seeds a **commit message** and asserts the message path refuses it and passes a caveated one. `autoland.sh` runs the null control **before** the real scan every time, so a broken checker can never sit green. `--message-file FILE` is the commit-message mode gate 5 uses.

The `dup-patch-false` pattern bans the *assertion* that `duplication_patch_applied` is False, not the field name: the field is trustworthy from `provenance_leela.py`'s label-reading fix forward (d98aa7c) and is legitimately quotable; only the two 18-Aug `smoke50_parser_in` exports carry a false `False`.

**Scope, stated honestly:** it catches the bare quote. It does not judge whether a caveat is *good*. Do not claim more coverage than that.

**Adding a figure:** append to `BANNED` with an id, a pattern, what it is, and *why it is banned* — the why is printed in the refusal, so a future session learns the reason at the moment it is blocked rather than having to go find it.

---

## §3. Loop discipline — Claude Code

Every task ends with this block. Not a summary — a **self-audit**, run before reporting, against the specific ways this campaign has already been wrong.

```
SELF-AUDIT
1. HYPOTHESIS  — what I set out to test, stated before the result.
2. EVIDENCE    — file:line, artifact filename, or command output. Not "I verified".
3. NULL CONTROL— what I ran that had to FAIL, and whether it did. If none, say so
                 and say why the check is still trustworthy.
4. REGISTER    — which entries in working/video/METHODOLOGY_REGISTER.md (35 entries)
                 apply here, checked by name.
5. NOT VERIFIED— what I did not check, and what it would take. Never empty.
6. GATES       — autoland/box.sh output, pasted. "It passed" is not the output.
```

### The four failure classes to check yourself against by name

Each has cost this campaign real rounds. They are not hypothetical.

1. **The one-armed check** (defects #24, #25, #37; register 33). A probe that measures one arm twice and reports agreement. The 560px mystery cost **three rounds** because the probe called the backend's `predict` — which is LlamaIndex's own path. **Cure:** every cross-arm probe enters through the same entry point the measured leg uses — the engine through its pipe, the service through its HTTP endpoint — never an inner function both happen to share.

2. **Self-consistency as evidence** (register 2). A check that can only pass. Census, structure and determinism all pass on a doubled document. **Cure:** the check must cross an independence boundary, and a null control that must fail is mandatory.

3. **A source trace is not a measurement** (register 1). The `chunk_size=512` prediction was read from source and lost to the records, which said ~4000. **Cure:** source tells you what to measure, never what the answer is.

4. **The unexecuted string** (register 4). `py_compile` proves a file parses, not that its names exist; a green suite is a claim about the paths it ran. **Cure:** read-backs, not assertions. `static_names.py` exists because of this one.

### Standing rules

- **A commit message names WHAT changed — never HOW MUCH, HOW MANY, or HOW EXACTLY it matched** (ruled 2026-09-08, widened the same day). No counts, no "differs only by X", no "identical except", no "N checks passed", no "content-identical to". Artifacts, checker output and the gate transcript carry all of that, and a message is written before the run it describes has been compared — three messages in three days asserted a count or a scope that was wrong by the time they landed (a checker run reported at 236 where 239 ran; a test run at 107 where 105 ran; a set of carried files described as differing from the target branch only by one commit when one of them carried hundreds of pre-existing lines). None can be corrected without a rewrite we never do; they stay in history as the reason. No checker enforces this; it is a rule about writing.
- **Prompts carry hypothesis + evidence, never an open-ended task.** Open-ended prompts produced this campaign's weakest answers.
- **Anything not explicitly reported as done is PENDING.** Never assume a command ran.
- **Own errors plainly.** If a command you handed over was wrong, name it and correct it. This document exists partly because a `--full` flag that did not exist was handed over and caught on read-back.
- **Refuse rather than skip.** A missing gate is not a passing gate. Fail closed, always.
- **Box rules** (`DOCS_HANDOFF.md` §8): `~/.venv/bin/python` never bare `python3`; `${PIPESTATUS[0]}` never `$?`; `command -v` to test for a tool; re-copy custom nodes after every `docker rm`; long blocks are committed script files that print their own sha256.

---

## §4. Box automation

`box.sh` already drives the box from the laptop with a refusal list, UTC transcripts and session-count hygiene. Automation extends it; it does **not** relax it.

**Required additions, in priority order:**

1. **`box.sh launch`** — long runs as `nohup … > ~/logs/<name>.log &` through the same pty channel, so a dropped SSM session does not kill a leg. The pty is load-bearing: no-TTY piped sessions die instantly *and* leak "Connected" server-side until 25 hit the per-instance cap and lock the box out.

2. **A stop-on-exit trap.** The auto-stop fires at 1% CPU for an hour and is **silent**. Automation that forgets to stop a `c7i.8xlarge` burns budget with no warning channel. Ansh ruled on 3 Sep that box time is not a constraint for the films work — this is hygiene, not a budget gate, and it should log hours used rather than refuse.

3. **A campaign preflight that refuses a leg**, extending the existing quiet-box check:
   - `load1` above the arm's own idle baseline → refuse. ⚠️ The engine burns **1.004 cores idle**, so a naive `load1 > 2.0` threshold conflicts with the arm's own baseline and will refuse valid legs. It must exclude the arm's idle floor — and at M tokens the floor may be ~M, which is itself unmeasured (see below).
   - corpus `VERDICT MATCH` (`verify_corpus_manifest.py`, **no flag** — full is the default; `--subset` is the wrong gate here)
   - image digest matches the expected one, read back from the running container
   - thread pins read back **inside the task process**, both arms, absence failing first
   - disk headroom

4. **Keep-alive discipline, unchanged and non-negotiable.** Required during unattended builds and downloads; **forbidden** during any measured leg. Always bounded and self-terminating — never a respawning parent. An unbounded one contaminated every 18-Aug run with ~8 cores and was only caught weeks later:

```bash
for i in $(seq 1 8); do (timeout 2700 md5sum /dev/zero >/dev/null 2>&1) & done
```

**Open question that gates the posture sweep:** is the engine's 1-core idle spin per-*server* or per-*token*? At M=16 on a parse-bound workload, per-token means 16 of 32 cores burned before any work starts. Measure it at the first sweep point.

---

## §5. Loop discipline — Advisor

- At every architectural crossroad: **The Current Decision** (the exact question), **The Trade-offs** (advantage of the recommendation vs disadvantage of the alternative), **The Final Call** (what is settled and why it is the production-grade choice here). Make the call; do not present a menu.
- Never state a measurement not actually seen. Label `[VERIFIED <date>]`, `[REPO]`, `[PRIOR-RECORD]`, `[HYPOTHESIS]`.
- Treat everything unreported as pending.
- Correct Ansh when he is wrong rather than letting it pass — including when he is overruling a rule he himself set, if the reason given does not cover the actual risk.
- Messages to teammates: short, human, no long paragraphs, no listing our own failures. Detailed findings go in the record and the report, not the message.
