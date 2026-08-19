# Review of RocketRide_Engine_Tickets.md against the artifacts and engine source

Checked 2026-08-18 against: the stock bundle (`engine/nodes/embedding_transformer/IInstance.py`),
the upstream clone (`rocketride-org/rocketride-server`, HEAD `1138936` + all server-v3.x tags),
`rocketlib/filters.py`, `packages/server/engine-lib/engLib/task/core/pipetask.process.cpp`,
teammate repos (Leela `a5c3b5d`+`0a0b558`, Shashi `83a1512`), and the local corpus bytes.

## MUST FIX — contradicted by source or SDK

1. **T2 Mechanism: "Work already assigned to a busy lane cannot migrate to an idle one" is
   WRONG.** Worker threads pop per-document items from a SHARED queue —
   `pipetask.process.cpp:73` and `:127` (`m_queue.pop()`). Dispatch is demand-driven already.
   The stranding is real but its mechanism is: per-DOCUMENT work items are indivisible, so in
   the drain the queue is empty and each remaining large document holds one thread (the 2.4-core
   tail). Rewrite the sentence; the steady-state 17.7/24 with a deep queue is a separate open
   question the ticket should hand to the engine team, not explain.
2. **T2 candidate "demand-driven dispatch" must be deleted** — proposing what the code already
   does invites "they didn't read it". "Work-stealing" likewise (a shared queue has nothing to
   steal). Replace with: size-aware ORDERING (LPT — largest documents first, shrinks the drain)
   and INTRA-document parallelism for the tail (split one document's chunk embedding across
   idle workers). "Internal windowing" bullet can stay.
3. **T2 "no progress signal of any kind during a batch" is contradicted by the SDK's own
   docstring** — `send_files` documents progress events `open/write/close/complete/error`
   (`rocketride/mixins/data.py`, Progress Events section). Soften to: the RESPONSE is atomic
   (confirmed); a per-file event interface exists but none of the three harnesses consumed it,
   and whether `complete` fires per-file mid-batch is untested.
4. **T1 Root cause verb: `preventDefault()` RAISES, it does not return** —
   `rocketlib/filters.py:180-190`: `raise APERR(Ec.PreventDefault, ...)`. The `return` at
   IInstance.py:80 is dead code. Shashi's own finding doc says "raises" — match him.
5. **Terminology: "lane" means a pipe DATA lane in this codebase** (`lane: "documents"` in every
   pipe config). T2 uses it for worker threads throughout — say "worker thread".

## FILL-INS — the ⟨VERIFY⟩ fields, now verified

* T1 upstream source path: **`nodes/src/nodes/embedding_transformer/IInstance.py`** (bundle
  flattens `src/`). Authored, not generated: byte-identical bundle<->source at every tag, MIT
  header, no codegen markers.
* T1 trigger: **`maxDocuments: int = 64` — class attribute, `IInstance.py:40`, used only at
  `:79`. NOT configurable** (no config plumbing anywhere; absent from `services.json`). Phrase
  the predicate ">= maxDocuments (64, hard-coded)".
* T1 Affects: **byte-identical at server-v3.2.0, 3.2.1, 3.2.2, 3.3.0 (+prerelease, +hackathon),
  3.3.1, and current HEAD (`1138936`)** — every visible release AND unfixed upstream.
  Independently corroborated: Shashi's engine.Dockerfile comment "upstream HEAD still carries
  the bug".
* T1 fix anchor: verified — `# Flush the documents` + 8-space `self._flushDocuments()` at
  bundle lines 82-83, identical in source.
* T1 regression test: exists now — `working/upstream/test_embedding_transformer_flush.py`,
  null-controlled (stock fails exactly the two flush-path checks, patched 7/7). State the unit
  boundary: the duplicate emission is the ENGINE's default action, unreachable from a unit
  test; the unit test pins "writeDocuments must prevent the default on every path"; the 63/64
  synthetic-length formula (L = 4000+3800*(n-1)) stays PROVISIONAL.
* T1 mechanism strengthener worth adding: whole-list x2 because the pipeline delivers a
  document's chunks as ONE write; sub-64 documents drain via `close()` (IInstance.py:94-96)
  with no event in flight — which is exactly why the >=64 predicate is clean.
* T2 corpus sha: **VERIFIED against local bytes** — sorted(*.pdf)[:9975] = `22177c33c3651fce`,
  and 9,975 + 25 disjoint warm docs consume the 10,000-doc corpus exactly.
* T2 threads note: verified in our drivers — batched passes `use(threads=24)`, per-document
  passes none. Accurate, and the conservative-direction framing is right.
* T1 workaround: "all three harnesses patch" VERIFIED (Leela arms/rocketride/Dockerfile, ours,
  Shashi engine.Dockerfile). But do not conflate field names: `engine_boot_patch` is SHASHI'S
  ONNX field; the duplication keys are `duplication_patch_applied`/`duplication_patch_id`
  (Leela's id value "BUG_CHUNK_DUPLICATION", ours "preventDefault-after-embedding-flush").

## VERIFY BEFORE SENDING — not checkable from this laptop

* The two artifact JSONs T2 names (T094225Z / T150551Z) and every number from them (2.776 vs
  1.910, 69.2%/50.4%, 16.61/12.09, the 1780%/237% phase split) — internally consistent
  (all deltas recompute), but the files are box/S3-only.
* T1 "0 duplicated of 9,847" — consistent with 9,975 offered minus ~1.3% empty, unverified.
* Leela's rows (56.7%/18.1, 60.9%/14.6, the 34-minute 3-chunk wait, 310s->2050s) — his
  exports; get his sign-off.
* Cross-team ratios (1.4x/2.1x/2.4x), Shashi uniform-corpus 92.8%, first-result 3,466s vs
  0.089s, Ticket-3 teaser 0/1 and 0/4.
* Appendix "61 GB" — c7i.8xlarge is nominally 64 GiB; state measured MemTotal with units.
* "Full reports": `WS1_Benchmark_Complete.md` does not exist in our repo, and the named Shashi/
  Leela reports are not in their repos at our clones — confirm they are S3 paths or fix.
* Repro caveat worth one line: `000_000674.pdf` carries an `/Encrypt` marker (Tika parses it;
  a repro attempt with a different parser may fail on that one document).
