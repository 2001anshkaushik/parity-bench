# Metrics & Verification — WS-1 walk-in document

**Ansh · 2026-08-14 · pre-Phase-2 sync.** Every number in this document resolves to a result file in
`working/results/` (named inline) or is labelled PROVISIONAL/UNVERIFIED. Nothing here is aspirational.

---

## §1 — One page

**We run three layers of metrics, and a rule that connects them:**

1. **Performance** — memory (median + peak + decomposition), wall clock, per-document latency,
   concurrency (offered *and achieved*), census counts. Throughput only on hardware that can
   support it — never from a laptop (2.2× swing from measurement order alone).
2. **Correctness** — seven per-document gates, from vector shape through independent-reference
   chunk hashing and content sanity.
3. **Provenance** — engine binary sha256, all versions read from the live system, thread counts
   measured in-process, config read back from live objects, collision-proof result files.

**The rule: no performance number is quotable unless its correctness gates passed and its variance
gate passed.** A fast wrong answer is not a result. A single measurement is never a result (the gate
refuses n=1).

**Why gates and not just metrics: this stack produced two product findings this week.**

* **`BUG_CHUNK_DUPLICATION.md`** — any text payload over **~239.8k characters** gets its complete
  chunk list emitted **exactly twice**. Silent: every vector valid, response healthy. Found by our
  independent-reference gate on a document that **passes census, structure, and determinism**.
  4-line synthetic reproducer, threshold bisected, deterministic n=3. **Full-corpus census: 534/9,992 documents (5.34 %) exceed the threshold** — a full 10k run doubles chunks on every one.
* **`BUG_NUL_TRUNCATION.md`, re-scoped with data** — the truncation defect is real and still
  reproduces, but **0/303 documents** show NUL (or any control character) in Tika output, so under
  Parser IN it has no observed path on this corpus. "Real defect, no observed instance" is a
  different — and correct — report from "0.70 % affected" (the full-census pypdf figure).

In this project's history, **the instrument has been wrong more often than the systems under test**
(§5: the defect log). The gates exist because each one caught something real.

## §2 — The metric table, mapped to the spec

> M0–M7 / M13 / M14 mapping is against the spec item list as relayed; the spec document itself is
> not in Leela's repo at `b9b4736`. Rows marked ⚠ need her definitions confirmed on the call.

| spec | our metric | definition — clock start/stop, in/out | gate before quotable | evidence it works |
| --- | --- | --- | --- | --- |
| M0 ⚠ | **census** | offered = successful + expected + unexpected; N records, unique ids, zero silent. Counted at the driver from responses | asserted per run, hard fail | closes 50 = 49+1+0 on both arms — `smoke50_parser_in__20260813T194514Z` |
| M1 ⚠ | **goodput** | documents passing ALL correctness gates (§4), per block | census must also close | same file |
| M2 ⚠ | **wall clock / block** | clock starts after warm-up documents complete, stops at last response; fixed doc count; parse inside the arms (Parser IN) | 10 % spread, n≥3, **block-0 excluded** | 0.24 % / 1.79 % spread after exclusion vs 12–38 % with block 0 — `matched_layers__20260811T092254Z` |
| M3 ⚠ | **per-document latency** | send → response per doc, run position recorded | first ~100 reps are warm-up (measured, §6) | warm-up curve, SPEC_RECONCILIATION §2 [PROVISIONAL — inline run, no result file] |
| M4 ⚠ | **memory median** | median RSS post-warm-up; RR = engine parent + task tree (by listening socket) + driver; LI = uvicorn parent + workers + driver; continuous 0.25 s sampling in sweeps | 10 % spread n≥3 · swap gate (evicted/compressed cell = unquotable) · topology + concurrency printed with every number | C-curve with per-cell verdicts — `matched_layers_sweep__20260811T165055Z` |
| M5 ⚠ | **memory peak** | max of same series | same; peak never in a median column | same file |
| M6 ⚠ | *(spec: LOC)* **four-way size split + toil ledger** | pipeline def / framework glue / defect workarounds / harness, plus per-obstacle time cost | n/a (reported) | `TOIL_INSTRUMENT.md`; position: Aug 4 exec review replaced LOC with total tech overhead |
| M7 ⚠ | **fault classes** | typed error classes per document; **known asymmetry**: LI returns typed classes, RR returns empty document list | recorded; cross-arm class comparison NOT quoted until taxonomies align | probe matrix — PI5/PI6 in STATE.md |
| M13 ⚠ | **cold/warm start** | cold: process start → first successful response (engine ~60 s, uvicorn worker warm-line). warm: first request on a warm service (measured 4.04× steady RR, 1.61× LI) | reported separately from steady state, never mixed | warm-up curve [PROVISIONAL — inline run]; per-worker `warm in` lines in service logs |
| M14 ⚠ | **recovery time** | terminate/wedge → next successful response | **not yet built**; we have the raw material (300 s stall observation, Leela's wedge forensics) | UNVERIFIED — needs a fault-injection runner; propose building jointly |
| — | **achieved concurrency** | in-flight counter sampled continuously; max + median-while-busy per cell | cell SHORT if achieved < offered → ratio not quoted | every sweep cell achieved=offered — sweep file above |
| — | **cross-arm extraction fidelity** | char ratio + word-Jaccard (order-insensitive) + seqmatch (order-sensitive, autojunk OFF) | **reported, never gated** — parsers differ by construction | median 0.9963 over 50 docs — smoke50 file |

## §3 — How each metric is verified (the part you will push on)

Five mechanisms, each with a concrete instance from this project:

**1. Declared ≠ measured.** Every config value is read back from the live system.
*What could be wrong:* a worker count, thread count, device, or chunk size that the system accepted
and ignored. *The check:* in-process read-back — `torch.get_num_threads()` inside the task process
and inside each uvicorn worker; device off the loaded model parameters; chunk size off the live
splitter object. *Has it fired:* yes, repeatedly — the service **declared 14 workers, measured
effective width 8** (`ws1_service_device.json`, STATE #9); a full 10,000-document comparison ran
**1-thread vs 10-thread and nothing detected it** until the in-process probe existed; the engine
**silently drops splitter kwargs** (found independently by all three teams); `TORCH_NUM_THREADS=1`
does not reach interop threads (stays 14).

**2. Null controls.** Run the variant where no difference is predicted; a difference means the
instrument is broken. *Instances:* the original collector was rebuilt after **biasing results
~100×** (archive-era, recorded in STATE §5); the RSS sampler null control measured **−0.4 %**
(instrument clean); the difflib similarity null control *passed* on identical strings but the
near-identical control exposed **autojunk scoring 99.3 %-identical text as 0.0000** — the null
control alone was insufficient, which is itself recorded.

**3. Two independent methods.** *Instance:* the concurrency-1 memory ratio measured by two harnesses
sharing no code path — synchronous 2,000-doc blocks (**1.795×**, `matched_layers__20260811T092254Z`)
vs async 500-doc sweep cells (**1.952×**, `matched_layers_sweep__20260811T165055Z`) — agreeing to
**8.8 %**. Quoted as a range (~1.8–2.0×), never as three digits. Also: memory byte totals verified
by working-tree stat AND git blob sizes; NUL prevalence by offline scan AND live pipeline detection.

**4. Variance gating.** The gate **refuses n=1** — a single measurement has zero spread by
construction, and a gate that cannot fail is worse than no gate. *Has it fired:* yes — LlamaIndex
memory at C=8 failed at 17.5 % spread (real drift, reported direction-only); C=16 failed on host
compression (+5.5 GB compressed, RSS meaningless); block-0 wall clock fails at 12–38 % until the
block-level exclusion is applied.

**5. Mutation testing on the gates themselves.** Remove the fix, confirm the test fails, restore,
confirm it passes. *Instance:* the silent process-match fix — guards disabled → test fails with
"counts() returned silently while 2 engine node processes were running"; restored → passes. The
regression suite is 12 tests + 1 known-open xfail, one per defect that produced a wrong number, and
the xfail flips to a loud XPASS if the upstream bug is ever fixed.

## §4 — The gate ladder: what each catches, what it cannot, and the case that proved it

**Lead exhibit — `000_000159.pdf`, one real corpus document, three runs
(`dup_prevalence__20260813T203833Z`):**

| gate | verdict on 159 |
| --- | --- |
| census | PASS |
| structure | PASS — all 164 vectors valid |
| determinism (n=3) | PASS — 164 chunks every run |
| **independent reference** | **FAIL — 164 ≠ 82: content silently doubled** |

Three gates pass on a document whose entire content is stored twice. That is why the ladder has four
rungs and not three.

| gate | catches | **cannot catch** | proved by |
| --- | --- | --- | --- |
| **census** | dropped/silent documents, duplicate ids | anything about content | Leela's PDF-1K zero-record reps |
| **structure** (384-d, finite, L2 ± 0.001, one vector/chunk) | zero vectors, dim drift, NaN, broadcast embedder | wrong text — garbage embeds as cleanly as prose (39,803 chars of binary passed as 11 unit-norm vectors) | our session-13 incident |
| **determinism** (blast vs sequential) | non-determinism, races | **any deterministic defect** — it reproduces identically and the gate agrees with itself: 3/3 PASS on a doc that lost 84 % to NUL truncation; PASS on the doubled 159 | both, this week |
| **independent reference** (per-arm chunk hash; LI: own extracted text; RR: parse-tap) | deterministic loss & duplication downstream of parse | defects **inside** parse (it trusts parse); cross-parser differences (by design → fidelity metrics) | caught 159; scoped honestly after the standalone-Tika reference produced 4/5 false failures |
| **content sanity** (NUL + printable < 0.90, threshold derived from 991 docs) | garbage extraction, control chars, reference-free | subtle loss with clean statistics (a doc losing 98.9 % had printable ratio 0.992) | `nul_characterization__20260810T023701Z` |

## §5 — The instrument defect log

Every line is a defect in **our measurement tooling**, not in the systems under test — and every
major retraction in this project traces to one. This is the credibility argument for the gates.

| # | defect | would have shipped as |
| --- | --- | --- |
| 1 | collector biased results ~100× | every early comparison |
| 2 | IPC cost mis-measured 115× | "IPC is the bottleneck" |
| 3 | single-process driver saturating at ~2,500/s | engine throughput understated **4.8×** ("flat 100→20,000" was the driver) |
| 4 | asymmetric deadlines between arms | a fake **7×** gap |
| 5 | alloc test freed memory immediately | a memory-pressure result that tested nothing |
| 6 | "hang ratio" was pool-width arithmetic | a reliability finding that was math |
| 7 | worker count taken from config (14) vs measured width (8; an earlier "4" was an mps artifact) | capacity overstated ~1.75× |
| 8 | engine matched by process NAME — counted an unrelated 5-day-old install | +104 MB (~5.8 %) on RocketRide's memory |
| 9 | warm-up included in slope | "+1,505 MB/1k documents leak" that was ramp + endpoint luck |
| 10 | unsynchronised driver windows | 12–58 % phantom spread read as engine noise |
| 11 | `str.replace("", x)` in a doc tool | two corrupted published documents (7 KB → 269 KB) |
| 12 | `grep -q` inside a git msg-filter | destroyed 18 commit messages (recovered from the manifest) |
| 13 | `self._stop` shadowing `threading.Thread._stop` | sweep crash at teardown |
| 14 | one asyncio loop driven from a ThreadPoolExecutor | **7/8 false non-determinism against RocketRide** |
| 15 | warm-up measured across documents whose sizes span 2018× | "no convergence" — it measured size, not warm-up |
| 16 | difflib `autojunk` default on natural language | 99.3 %-identical text scored **0.0000** similarity |
| 17 | swap-only memory gate missed the compressor | C=16 cells (5.5 GB compressed away) would have passed |
| 18 | standalone-Tika reference (glyph mapping differs in-process) | **4/5 false defect reports against RocketRide** |

18 recorded (the count was 13 at the start of this week; 13–18 were caught during Parser IN
preparation, before AWS).

**Test coverage, stated exactly:** the regression suite is **13 tests covering 11 of the 18**
(#7-threads, #8 ×2 tests, #9, #16, plus the NUL/content/goodput/collision/setsid/artifact-guard
classes). The other 7 are guarded differently and deliberately: **#1–6** belong to retired
archive-era instruments with no live code to test (the defence is the protocol's two-method rule);
**#11–12** are workflow rules (assert-nonempty edit pattern; no `grep -q` in filters) recorded in
BENCHMARK_SETUP §7; **#14** is checked implicitly by the 50/50 blast-vs-sequential determinism run;
**#15** is a methodology rule (fixed-fixture warm-up); **#17** (compressor gate) has **no test yet —
open item, and the gate itself is macOS-specific and being replaced for Linux (§6)**. **Notice the direction: several would have unfairly hurt RocketRide, one
unfairly flattered it. The gates cut both ways, which is the point.**

## §6 — Open items, with our position and the evidence

| item | positions on the table | ours, with evidence |
| --- | --- | --- |
| **warm-up count** | Shashi: 25 | **100.** Fixed-fixture 200-rep run: RR within 5 % by rep 25, **LlamaIndex still 1.08× at reps 25–50**, steady ~rep 100. 25 bakes an 8 % bias into one arm only. [PROVISIONAL — one fixture, one host, inline run recorded in SPEC_RECONCILIATION §2; re-run on AWS is cheap] |
| **RocketRide parse reference** | spec §4.3 self-capture | **parse-tap** (2nd `response_text` node). Self-capture provably passes on 100 % deterministic loss; standalone Tika gives 4/5 false failures; the tap matched **97/98** and caught the duplication. Limitation stated: trusts parse itself |
| **memory boundary on AWS** | tree+driver / cgroup / driver-only | **cgroup (Leela's).** Ours folds the driver into RR (+250–320 MB, disclosed); Shashi's `getrusage(SELF)` misses the engine entirely. Switch at the AWS boundary so history stays comparable |
| **driving modes** | closed-loop / blast / sequential | **run all three, never one table.** Burst percentiles include queueing (her own annotation); a "p50" must carry its driving mode |
| **ladder to 32** | spec: 32 | run it, but **re-measure pool width first on the 32-vCPU host** — 17.24 (`anchor_c_width.json`) is a macOS number; cells above the measured width are past-saturation and must say so |
| **per-file corpus sha256 manifest** | both teams have one | **we don't yet — our gap, being closed.** Until then our corpus provenance is the weakest of the three |
| **M14 recovery time** | in Leela's proposal | not built by anyone end-to-end; we have the stall/wedge raw material — propose building the fault-injection runner jointly |

## §7 — Pre-armed answers

**"What would you cut?"** Census + structure + the independent reference + the provenance manifest
are the floor — each catches a class the others cannot. Fidelity metrics are reporting, not gating:
zero run-time cost to keep. The expensive item is n≥3 with warm-up exclusion, and it is the one that
turned 12–38 % phantom instability into a 0.24 % measurement. Cut that and every wall-clock number
becomes noise we then argue about in meetings instead.

**"Why so many gates?"** Because they disagree — that is the design. 159 passes three and fails one;
the NUL document passes structure and fails content sanity; C=16 passes the swap gate and fails the
compression gate. A gate set where every gate agrees is one gate with extra steps.

**"Isn't this slowing us down?"** The gates are one-time builds that run in seconds per document.
What actually cost time this project was the *absence* of a gate: 18 instrument defects, several
worth days each (the 10,000-document run at mismatched threads, the weekend phase lost to a fixed
project_id). The stack exists because we measured which was more expensive.

**"How do we know the gates themselves are right?"** Four ways: mutation testing (remove the fix,
watch the gate fail, restore, watch it pass — done for the process-match gate); null controls on the
gates (both arms match the offline reference 12/12 before any defect hunting); the gates disagreeing
in the designed pattern on known cases; and when a gate was wrong, saying so — the standalone-Tika
reference was demoted to advisory the same day it produced false failures, in the published record.

**"Your metrics found bugs — are you benchmarking or QA-ing?"** Both, deliberately. A benchmark that
cannot detect a silently doubled document is publishing 2× chunk-throughput for the affected arm.
Correctness gating is what makes the performance numbers mean anything.
