# Pre-Push Review Package

**Repo:** `parity-bench` (private) · **branch:** `main` · **generated:** 2026-08-10

**Nothing has been pushed. No remote is configured.** This document is the complete contents of the repository as it stands, for review before a first push.

---

## a) Tracked file tree

**339 files, 4.17 MB.** The working tree is 7.1 GB; everything else is excluded (§e).

| directory | files | size |
| --- | ---: | ---: |
| `./` | 9 | 55 KB |
| `archive/` | 1 | 4 KB |
| `archive/docs/` | 21 | 251 KB |
| `archive/results/` | 8 | 57 KB |
| `archive/scripts/` | 9 | 115 KB |
| `docker/` | 5 | 13 KB |
| `publishable/` | 24 | 323 KB |
| `repl_state/` | 9 | 231 KB |
| `weekend_state/` | 7 | 347 KB |
| `working/dossiers/` | 31 | 58 KB |
| `working/handoff/` | 7 | 71 KB |
| `working/handoff/parity/` | 4 | 30 KB |
| `working/harness/` | 12 | 73 KB |
| `working/harness/adapters/` | 3 | 17 KB |
| `working/nodes/cpu_probe/` | 4 | 3 KB |
| `working/nodes/env_probe/` | 4 | 3 KB |
| `working/nodes/fault_probe/` | 4 | 6 KB |
| `working/nodes/noop_probe/` | 4 | 2 KB |
| `working/nodes/pdf_probe/` | 4 | 3 KB |
| `working/nodes/split_embed/` | 4 | 7 KB |
| `working/pipes/` | 8 | 4 KB |
| `working/results/` | 68 | 1,915 KB |
| `working/results/alloc_hold/` | 1 | 2 KB |
| `working/results/ceiling/` | 1 | 1 KB |
| `working/results/deployment_parity/` | 1 | 1 KB |
| `working/results/docker_ladder/` | 5 | 15 KB |
| `working/results/fault_isolation/` | 2 | 23 KB |
| `working/results/fault_matrix/` | 4 | 33 KB |
| `working/results/model_a/` | 1 | 3 KB |
| `working/results/operational/` | 1 | 1 KB |
| `working/results/pool_width/` | 1 | 1 KB |
| `working/results/process_scaling/` | 3 | 6 KB |
| `working/results/tier2/` | 1 | 5 KB |
| `working/scripts/` | 57 | 434 KB |
| `working/wrappers/` | 1 | 4 KB |
| `working/ws1/` | 10 | 55 KB |
| **total** | **339** | **4.17 MB** |

### Repository root

| file | size |
| --- | ---: |
| `.env.example` | 0.3 KB |
| `.gitignore` | 2.6 KB |
| `README.md` | 6.0 KB |
| `REPLICATION_README.md` | 2.7 KB |
| `matched_replication.py` | 14.9 KB |
| `requirements.txt` | 1.7 KB |
| `weekend_runner.sh` | 7.1 KB |
| `weekend_summarise.py` | 3.7 KB |
| `weekend_worker.py` | 16.4 KB |

### `publishable/` — the documents a reader is meant to start from

| file | size |
| --- | ---: |
| `A3_SERIALIZATION_FINDING.md` | 10.2 KB |
| `BENCHMARK_SETUP.md` | 12.0 KB |
| `BUG_NUL_TRUNCATION.md` | 8.6 KB |
| `DOCKER_ARCHITECTURE.md` | 13.7 KB |
| `DOCKER_DEMO_RESULTS.md` | 12.6 KB |
| `ENVIRONMENT.md` | 7.9 KB |
| `FAIRNESS_BASIS.md` | 13.0 KB |
| `INVENTORY.md` | 6.8 KB |
| `MEETING_2026-08-10.md` | 35.5 KB |
| `PARSER_DECISION.md` | 8.0 KB |
| `PARSER_PREMISES.md` | 7.4 KB |
| `PROVISIONING.md` | 6.1 KB |
| `README.md` | 7.1 KB |
| `REBASELINE_PLAN.md` | 8.5 KB |
| `RUNBOOK_LLAMAINDEX.md` | 13.9 KB |
| `SCHEMA_PROPOSAL.md` | 14.6 KB |
| `STATE.md` | 59.0 KB |
| `TOIL_INSTRUMENT.md` | 8.7 KB |
| `TWO_TIER_PARSER_DESIGN.md` | 6.7 KB |
| `VARIANCE_PROTOCOL.md` | 8.5 KB |
| `WEEKEND_FORENSICS.md` | 19.3 KB |
| `WEEKEND_RESULTS.md` | 2.4 KB |
| `WEEKEND_RUN.md` | 6.4 KB |

## b) Commits

All commits carry today's date: this is an initial import of work developed without version control. The grouping is by module, not a development narrative.

**Subject lines only, no bodies — and here is why.** A `git filter-branch --msg-filter` that used `grep -q` emptied 18 of the 19 commit messages: `grep -q` exits early and leaves the rest of stdin unread, and in a msg-filter stdin *is* the message. The bodies could not be recovered, because the reflog and the `refs/original` backup were expired in the same session (both pitfalls are now recorded in `BENCHMARK_SETUP.md` §7). The subjects were restored from an earlier revision of **this table**, which is the only place they survived; every commit's file contents were untouched throughout, and all 19 tree hashes were verified identical to a pre-restore backup. One subject — the last one below — is **derived from its own diff** rather than restored, because a table cannot list the commit that writes it. Treat the subjects as accurate and the absence of bodies as a known loss, not a style choice.

| # | hash | message (subject) | files | lines |
| ---: | --- | --- | ---: | ---: |
| 1 | `1ad0b0d2` | chore: initial import of WS-1 benchmarking work | 2 | +73/-0 |
| 2 | `14802a5a` | feat(harness): measurement instruments | 15 | +2266/-0 |
| 3 | `89ca7d4a` | feat(service): LlamaIndex FastAPI service | 10 | +1287/-0 |
| 4 | `a41e2417` | feat(nodes): benchmark-only RocketRide engine nodes | 32 | +709/-0 |
| 5 | `296d580e` | feat(runners): benchmark runners and probes | 61 | +11321/-0 |
| 6 | `c1b12df9` | test(evidence): result files, checkpoints and archived material | 186 | +166560/-0 |
| 7 | `44e86d00` | docs: findings, protocol and handoff material | 23 | +4640/-0 |
| 8 | `09fe48af` | docs: BENCHMARK_SETUP.md — build guide for Leela | 1 | +186/-0 |
| 9 | `d672a869` | fix(evidence): retain container-ladder results where evidence lives | 6 | +1056/-1 |
| 10 | `e8309011` | docs: note pre-existing date inconsistencies in the archived progress log | 1 | +9/-0 |
| 11 | `588699c5` | docs: root README | 1 | +92/-0 |
| 12 | `afbf12ee` | docs: state cross-repo version pairings as facts, not verdicts | 2 | +29/-20 |
| 13 | `27f01742` | docs: PREPUSH_MANIFEST.md — complete review package | 1 | +345/-0 |
| 14 | `08082e8d` | docs: demote inlined README headings in the manifest | 1 | +11/-8 |
| 15 | `3508b0db` | docs: demote the inlined README title too | 1 | +1/-1 |
| 16 | `5a346de6` | docs: archive/README.md and repo metadata | 3 | +108/-3 |
| 17 | `a50fa610` | docs: remove tool-authorship attribution from two archived documents | 2 | +2/-2 |
| 18 | `4e470bc7` | docs: regenerate manifest commit table after the attribution edit | 1 | +1/-2 |
| 19 | `a3e5711a` | docs: repair manifest commit table and section c heading | 1 | +20/-0 |
| 20 | `eb1b033c` | docs: restore commit subjects, record the two git pitfalls that cost them | 2 | +77/-69 |
| 21 | `7e613357` | fix(docs): make a fresh clone actually runnable | 7 | +137/-37 |
| 22 | `ce453336` | docs: note that the manifest's quoted README uses root-relative links | 1 | +5/-0 |
| 23 | `1d9c7118` | fix(selftest): skip the thread-match check when this tree has no engine | 1 | +4/-1 |

The last two commits cannot appear in the table above: they are the ones that *write* it. **24** `docs: regenerate the manifest against final history` and **25** `docs: re-inline the current README into the manifest` — a manifest can describe every commit except its own. Verify with `git log --oneline` against the clone; 25 commits total.

## c) Root `README.md` — complete text

This is what GitHub shows on landing.

> Quoted **verbatim**, so its links are written relative to the **repo root**, not to this file in
> `publishable/`. They resolve correctly on GitHub's landing page and do not resolve from here. That
> is a property of quoting, not a broken link — rewriting them would stop this being the actual
> README text, which is the one thing this section is for.

---8<--- BEGIN README.md ---8<---

*(Headings below are demoted one level so the inlined file does not create sections in this manifest. Otherwise verbatim.)*


### parity-bench (README title)

Measurement work for **WS-1 "Service Parity"**: two implementations of the same document pipeline —
the **RocketRide engine** and a **LlamaIndex FastAPI service** — running PDF → text → chunks →
384-d embeddings, plus the instrumentation built to make that comparison trustworthy.

**Private. Not for distribution outside the team.**

---

### Start here

| you want to… | read |
| --- | --- |
| **build or reproduce the harness** | [`publishable/BENCHMARK_SETUP.md`](publishable/BENCHMARK_SETUP.md) — §7 is the pitfalls table, the most useful page in the repo |
| **see current findings** | [`publishable/MEETING_2026-08-10.md`](publishable/MEETING_2026-08-10.md) |
| **check what a number means, or whether it still stands** | [`publishable/STATE.md`](publishable/STATE.md) — §5 is every withdrawn number, with why |
| **run it** | [`publishable/PROVISIONING.md`](publishable/PROVISIONING.md) first — the engine and corpus are not in this repo |

### Headline result

**Under a matched configuration the two implementations are functionally identical except for one
defect.** [**VERIFIED** — 3 blocks × 2,000 documents per arm, interleaved, reproduced 3/3]

| arm | goodput (3 blocks) | faults | content-suspect |
| --- | --- | --- | --- |
| LlamaIndex | 1,972 · 1,972 · 1,972 | 28 · 28 · 28 | 23 · 23 · 23 |
| RocketRide | 1,965 · 1,965 · 1,965 | 35 · 35 · 35 | 23 · 23 · 23 |

Identical to the document, every block. The arms differ by **exactly 7 documents per 2,000
(0.35 %)**, and every one is the same defect: [`BUG_NUL_TRUNCATION.md`](publishable/BUG_NUL_TRUNCATION.md).

#### Other findings that stand

| finding | label |
| --- | --- |
| **`page_content` is truncated at the first NUL byte** in the engine's response. Embeddings are computed over the full text (cos = 1.0000 vs reference); only the returned text is lost. Silent — the vectors look perfect. Affects ~0.30 % of documents | **VERIFIED** (2 methods: offline scan + live pipeline detection) |
| **Thread configuration is the largest lever measured.** Pinning changes concurrency scaling 1.43× → 3.04×, and costs 3.07× at concurrency 1. There is **no per-pipeline config surface** — only a process-level env var, global to the engine | **VERIFIED** |
| **RocketRide uses ~2× the resident memory** on identical work (2.08× / 2.05× / 2.03× by three independent methods) | direction **VERIFIED**, magnitude **PROVISIONAL** — a 24 % spread from bimodality, not drift |
| **~150 concurrent pipelines livelock**, leaving orphaned node processes. The other concurrency model shows no growth | **VERIFIED** (reproduced twice) |
| **Throughput on this host is unmeasurable.** Ascending-cold reads 101 /s where descending reads 241 /s on the same service — a 2.2× swing from measurement order alone | **VERIFIED** |

**No throughput comparison is published**, and none can be from this hardware. That is the case for
moving Phase 2 to a Linux x64 host, along with the fact that **no `linux-arm64` engine build has
ever been released** (all 51 releases checked), so RocketRide cannot be containerised here at all.

### How claims are labelled

Every claim carries **VERIFIED** (two independent methods, reproduced) / **PROVISIONAL** (one
method) / **UNVERIFIED** (asserted, not established). Numbers that did not survive are not deleted
— they are listed with the reason in `STATE.md` §5. **More findings have been withdrawn than kept**,
including several that were favourable, and the corrections run in both directions.

### Layout

```
publishable/   push-ready docs — findings, setup guide, protocol, bug report, decision briefs
working/       the live code
  ws1/           the LlamaIndex service (schema / pipeline / service, deliberately isolated)
  harness/       resultio, goodput, content_sanity, engine_ops, stats
  nodes/         benchmark-only RocketRide nodes (env_probe, split_embed, pdf_probe, …)
  scripts/       probes, profiles, and the regression suite
  results/       every result file, named <name>__<UTC>__<payload-hash>.json
weekend_state/ per-block checkpoints — the RSS series behind the memory findings
repl_state/    matched-replication checkpoints
archive/       superseded docs and 9 deprecated harnesses, each guarded to exit non-zero if run
docker/        container design and the ladder runner
```

Top-level runners: `matched_replication.py`, `weekend_runner.sh`, `weekend_worker.py`.

### Not in this repo

| excluded | size | how to get it |
| --- | ---: | --- |
| `engine/` — engine bundle | ~1.2 GB | [`PROVISIONING.md`](publishable/PROVISIONING.md) §1. Also contains a **hand-copied pypdf** inside its embedded interpreter that is not manifest-reproducible — §3 |
| `corpus/` — GovDocs1 PDFs | ~5.9 GB | public domain, digitalcorpora.org; `working/scripts/fetch_govdocs.py` — see [`PROVISIONING.md`](publishable/PROVISIONING.md) §5 |
| `data/` — mt10k sample | 4 MB | rebuildable from Leela's manifest (sha256-verified) |
| model weights | — | baked at image build; `HF_HUB_OFFLINE=1` at runtime |
| `.venv/`, logs, generated pipes | — | regenerable |

`.env` is excluded on principle. It holds only a local URI and the placeholder key `MYAPIKEY`, but
committing it is a habit that eventually leaks a real one — copy `.env.example` instead.

### First thing to run

**Build the venv first — it lives one level ABOVE the clone, and a fresh clone has none.**
[`PROVISIONING.md`](publishable/PROVISIONING.md) §4 is three commands; `requirements.txt` pins the
set. Then:

```bash
../.venv/bin/python working/scripts/regression_selftest.py
```

Ten tests, one per defect that produced a wrong number in this project. It is the fastest way to
find out whether your environment differs from the one these results came from. It needs **no
engine and no corpus** — it runs on a bare clone plus the venv, which makes it the right first
move before provisioning the 7 GB of excluded material.

---8<--- END README.md ---8<---

## d) `BENCHMARK_SETUP.md` — headings and the pitfalls table

**Section headings:**

- Benchmark Setup — building the same thing
  - 1. What this is and what it measures
  - 2. Engine lifecycle
  - 3. Thread parity — and why the config value is not the answer
  - 4. The 10 % variance gate
  - 5. Goodput and content sanity — shape is not enough
  - 6. Reproducing the matched replication
  - 7. Pitfalls that cost us weeks
  - 8. Where to look

**§7 pitfalls table, in full** — the section most likely to be useful to a teammate:

| pitfall | symptom |
| --- | --- |
| **`setsid` does not exist on macOS** | `nohup setsid ...` exits instantly with *"setsid: No such file or directory"*; the job looks launched and never ran. Cost two hours once, then recurred. Verify every detached launch **by PID**. |
| **`/health` is answered by one worker** | The service reports ready while 7 of 8 workers are still loading the model, so the first measurements are on a half-warm service. Count `warm in` lines instead, one per worker. |
| **`os.cpu_count()` reports HOST cores inside a container quota** | 14 inside a `--cpus 4` container. torch and BLAS size their pools from it, so a container spawns 14 threads into 4 cores — the exact oversubscription you containerised to avoid. Pin explicitly; read `/sys/fs/cgroup/cpu.max` for the real quota. |
| **Declared ≠ measured thread counts** | Everything looks configured; the arms silently run at 1 vs 10 threads for an entire 10,000-document comparison. Only an in-process probe catches it. |
| **Hardcoded result paths clobber silently** | Three scripts wrote to `results/isolated_profile_llamaindex.json`; the third overwrote the first two. No error, no warning, data gone. Ours now embed a UTC stamp and a payload hash and refuse to overwrite. |
| **Ascending concurrency sweeps profile a low-power machine** | Ascending-cold reads 101 /s where descending reads 241 /s on the same service. Pre-warm before every measurement, or measure descending. |
| **`sentence-transformers` silently selects `mps`** | No error, ~3× the throughput, ~10× the run-to-run spread, and every cross-service number invalid. Set `device` explicitly and **assert the resolved device**, refusing to start on a mismatch. |
| **llama-index returns `{}` for PDFs when the reader package is absent** | Warns, returns empty, reports success. Ten thousand green results that embedded nothing. |
| **`.gitignore` has no trailing comments** | `engine/    # 1.2 GB` is parsed as a literal pattern including the comment and matches nothing. We nearly staged 7.4 GB. Comments go on their own line. |
| **`str.replace("", x)` inserts between every character** | A 7 KB file became 263 KB. Guard any programmatic edit against an empty pattern. |
| **`psutil.net_connections()` needs root on macOS** | Returns nothing without it, so a PID lookup silently falls back to matching by name — and then counts an unrelated five-day-old engine. Use `lsof`. |
| **Matching processes by name** | `pgrep -f mything` also matches your own monitoring shell, so a finished run looks alive. Match by PID. |
| **`grep -q` inside a `--msg-filter` eats the message** | `grep -q` exits the moment it decides, leaving the rest of stdin unread — and in a `git filter-branch --msg-filter` stdin *is* the commit message. Every commit the pattern did not match got an **empty** message, because the `cat` after it had nothing left to read. This emptied 18 of 19 messages here. Read stdin **fully into a variable first**, then decide. Test the filter standalone against one commit before pointing it at history. |
| **`gc --prune=now` after a filter-branch destroys the only undo** | `filter-branch` leaves three recovery paths — `.git/refs/original/`, the reflog, and the old commits as dangling objects. `git reflog expire --expire=now --all && git gc --prune=now` removes all three at once, and a `rm -rf .git/refs/original` beforehand removes the fourth. That sequence is routinely recommended as "cleanup"; it is what made the above unrecoverable. **Back up the whole directory including `.git` before any history rewrite, and leave the reflog alone until the result is verified.** |

## e) Excluded paths

| path | size | why excluded | how to restore |
| --- | ---: | --- | --- |
| `engine/` | 1.2 GB | vendored release bundle; also contains a hand-copied pypdf inside its embedded interpreter that is not manifest-reproducible | `PROVISIONING.md` §1 and §3 |
| `corpus/` | 5.9 GB | GovDocs1 PDFs, public domain | `working/scripts/fetch_govdocs.py`; manifest carries sha256 per file |
| `data/` | 4.0 MB | mt10k sample | rebuildable from Leela's manifest, sha256-verified |
| `.venv/` | — | python environment | `PROVISIONING.md` §4, versions pinned in `ENVIRONMENT.md` |
| `logs/, weekend_logs/, repl_logs/` | 1.3 MB | run logs, per-machine, contain absolute paths | regenerated by any run |
| `working/pipes/generated/` | 8.2 MB | ~2,000 per-run pipe files | regenerated by any run |
| `working/results/selftest/` | 0.6 MB | instrument self-tests | regenerated by the selftest |
| `pdftest/` | 0.1 MB | generated PDF fixtures | regenerated by the parser tests |
| `docker/out/` | — | container runtime output | the ladder results that are cited were copied to `working/results/docker_ladder/` |
| `.env` | — | excluded on principle; holds only a local URI and the placeholder key MYAPIKEY | copy `.env.example` |
| `weekend_state/*.tmp, repl_state/*.tmp` | — | atomic-write temp files | n/a — the `.json` checkpoints themselves ARE committed, they are evidence |
## f) Anything a reviewer might flag

Scanned every tracked text file. **Nine matches, all false positives**, listed so the reviewer can confirm rather than take my word.

| category | matches | assessment |
| --- | ---: | --- |
| TODO / FIXME / XXX / HACK | **0** | none in the repo |
| profanity or venting | **0** | — |
| personal notes | **0** | — |
| dead relative links | **0** | all markdown links resolve |
| "placeholder" | 6 | all are text *describing* a placeholder: the `MYAPIKEY` local key, and a competitor's docstring URL that our classifier once mis-flagged. No placeholder content left in. |
| informal aside | 1 | the word "obviously" mid-sentence in `ws1/smoke.py` |
| blame-ish wording | 2 | error-message strings: `"ENGINE FAILED TO BECOME READY"` and `"gate failed to catch"` |

### Content about teammates — reviewed and rewritten

The repo contains observations about colleagues' environments. **Every finding was kept; the phrasing now states the technical fact without an attached verdict.** Two passages changed:

| file | before | after |
| --- | --- | --- |
| `publishable/ENVIRONMENT.md` | heading *"Consequence for the team's existing repos"*; *"that repo is already running a mismatched pair"*; *"those results are not reproducible from any published artifact"* | heading *"Version pairings across the team's repos"*, prefaced *"not to grade any repo"*; *"a combination the manifests do not pair"*; *"reconstructing that environment needs the commit rather than a published artifact"* |
| `archive/docs/progress.md` | *"**Team repo mismatches found:**"*; *"— already mismatched"*; *"not reproducible from anything published"* | *"**Version pairings across team repos**"* with the same neutral framing |

Left unchanged because they are self-directed or neutral: *"Source inspection said GPU and was **wrong**"* (my own inspection), and all attribution references (*"Leela's manifest"*, *"for Shashi"*, ownership tables).

Also corrected in `archive/docs/progress.md`: two session headings carried the wrong day or number because sessions crossed local midnight (session 12 headed 08-08 though it followed session 11 on 08-09; session 2/4 labels swapped). Both fixed, body text unaltered, and the file says so.

## g) Verification numbers

| check | result |
| --- | --- |
| secrets (AWS keys, GH/Slack tokens, private keys) | **0** |
| absolute `/Users/ansh` paths | **0** |
| dangling evidence references in a fresh clone | **0** |
| broken markdown links | **0** |
| `.env` tracked | **no** · `.env.example` present |
| hand-copied pypdf tracked | **no** (inside excluded `engine/`) |
| working tree | **0** uncommitted |
| remotes configured | **0** |
| regression suite | **9 passed, 0 failed, 0 skipped, 1 xfail (known open upstream), 0 xpass** |

The one expected failure is the NUL-truncation test: the bug is open upstream, so the test is marked `xfail` and will turn into a hard failure if it is ever fixed and then regresses.

## h) Read as the recipient — what Leela would notice

Read back as a teammate who is building the same harness **and who finds her own work described in
it**. Seven things she would react to, and what was done about each.

**1. "You describe my environment in your repo."**
`ENVIRONMENT.md` and `progress.md` both record that her runs used source build `1ec7454` rather
than a release tarball. *Kept — it is true and it matters for comparing numbers.* Rewritten to say
what reconstructing that environment requires, with an explicit line that neither pairing is wrong
to use, and the reason this project pinned a tagged release stated as our own choice rather than a
correction of hers.

**2. "`BENCHMARK_SETUP.md` is addressed to me by name."**
It opens *"For Leela."* That is intentional and she is the audience, but it also means she is
reading a document that tells her what we got wrong for two weeks. §7 is framed as our pitfalls,
with the symptom she would actually see — not as advice about her work.

**3. "Half of these findings are about your own mistakes."**
That is deliberate and worth saying out loud when sharing: the repo withdraws more findings than it
keeps, and `STATE.md` §5 lists each with the reason. If that reads as excessive self-flagellation,
the counter is that every withdrawal was caught by the protocol rather than by a reviewer.

**4. "Your engine numbers disagree with mine."**
They may. The likely causes are documented rather than asserted: thread configuration (3.07× at
concurrency 1), measurement order (2.2× on this host), and the ascending-sweep power-state effect.
`BENCHMARK_SETUP.md` §3 shows how to check the thread count *inside* the process, which is the
first thing to compare if two sets of numbers disagree.

**5. "There is a bug report about the engine in here."**
`BUG_NUL_TRUNCATION.md` is written to be filed upstream and names version `3.3.1.35`. Shashi owns
the RocketRide service, so he should see it before it goes anywhere. It is a data-loss finding with
a minimal reproducer, not a criticism of anyone's work.

**6. "Can I actually run this?"**
Not without provisioning: the engine bundle and the corpus are excluded, ~7.1 GB of the working
tree. `PROVISIONING.md` covers each, and one item is honestly awkward — the hand-copied pypdf
inside the engine's embedded interpreter has no supported install path, so it is documented as a
manual step rather than automated.

**7. "Why is `archive/` in here at all?"**
Twenty-one superseded documents and nine deprecated harnesses. They are kept because the correction
history is the most reliable part of the project, and every archived script exits non-zero if run.
A reviewer who only wants current material should read `publishable/` and ignore the rest.

## i) What I would still flag to you before sending

- **`archive/docs/` contains the full unedited history**, including earlier phrasings of findings
  that were later withdrawn. The withdrawals are marked, but a reader who starts in `archive/`
  rather than `publishable/` could quote something stale. The root `README.md` points at
  `publishable/` first for that reason.
- **`BUG_NUL_TRUNCATION.md` is filing-ready.** Consider whether Shashi should see it before it is
  visible to anyone else.
- **Commit dates are all today.** The first commit message says so explicitly, but it is the first
  thing a reviewer will notice in `git log`.

## j) GitHub repository metadata — ready to paste

Written for someone who has never heard of RocketRide or WS-1, and leading with **how** it measures
rather than **what won**. The repo is private, but the description and topics are the first thing
any future reader sees.

**Description** (309 characters, limit 350):

```
Benchmarking harness for two document-embedding pipelines, built around the measurement problem rather than the result: matched configuration verified in-process, per-document goodput and content-sanity gates, barrier-synchronised variance gating, and a correction history that records every withdrawn number.
```

**Topics** (8):

```
benchmarking  reproducible-research  performance-measurement  memory-profiling  embeddings  document-processing  llamaindex  python
```

| topic | why |
| --- | --- |
| `benchmarking` | the domain |
| `reproducible-research` | the actual subject: pinned environments, sha256-manifested corpora, a regression test per defect |
| `performance-measurement` | findable by someone with the same measurement problem |
| `memory-profiling` | the axis this hardware can actually measure |
| `embeddings` · `document-processing` | the workload |
| `llamaindex` | the one framework named in public metadata; the engine is not public, so naming it would be meaningless to an outside reader |
| `python` | language |

**Deliberately omitted:** any topic implying a verdict (`comparison`, `vs`, `faster`), and the
engine's name — no throughput comparison is published, and the metadata should not imply one.

**Note on the repo name.** `parity-bench` describes the method (parity testing) rather than an
outcome, which matches the description above. The previous name embedded both product names and a
comparison framing.

