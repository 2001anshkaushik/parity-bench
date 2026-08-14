# One page for Leela & Shashi — what we bring, what we take, what needs a decision

**Ansh · 2026-08-14.** Everything measured on engine 3.3.1.35 + SDK 1.3.0 (the team pin). File
references are in our repo, `publishable/` and `working/results/`.

---

## Offering — take any of these, they are portable

| item | what it does | proof it earns its place |
| --- | --- | --- |
| **parse-tap reference** (`product_pdf_tap.pipe` + `chunk_hash.py`) | 2nd `response_text` node taps the engine's own parse output; chunks are hashed against it offline | the only gate that caught **`BUG_CHUNK_DUPLICATION`** — a doc whose full chunk list is emitted twice while census, structure AND determinism all pass. 97/98 exact match on clean docs |
| **duplication detector / the bug itself** | any text payload > **~239.8k chars** → complete chunk list emitted **exactly 2×**, silently | 4-line synthetic reproducer, threshold bisected (239,062 clean / 239,843 double, n=3 each), factor exactly 2 up to 750k. **Check your long documents for chunk counts at exactly 2× expected** |
| **achieved-concurrency verification** | in-flight counter sampled continuously; a cell where achieved < offered is marked and its ratio not quoted | prevents "flat curve because we weren't actually concurrent" — bit us once |
| **in-process thread verification + config gate** | both arms report `torch.get_num_threads()` from inside the live worker; run refuses on mismatch | added after a full 10k-doc run silently ran 1-thread vs 10-thread |
| **block-level warm-up exclusion** | block 0 is 12–38 % slower on BOTH arms even after per-doc warm-up; exclude it | wall-clock spread 12–38 % → **0.24 % / 1.79 %** |
| **swap/compressor memory gate** | record swap + compressed pages at cell start/mid/end; evicting cell = unquotable | macOS compressed 5.5 GB during a C=16 cell; RSS looked fine and was meaningless |

## Adopting from you — already in our harness

* **Shashi:** engine **binary sha256** in the environment manifest (a tag is mutable, a hash is not);
  runtime **chunk-size read-back** from the store/probe rather than trusting config.
* **Leela:** census identity (offered = successful + expected + unexpected) · structure tolerance
  **L2 ± 0.001** · determinism re-run · splitter config read back off the live object · ground-truth
  hash discipline (our chunk-hash gate is your idea, per-arm) · the `tags`-lane wiring for `parse`.

## Verified together, worth filing upstream

* Leela's two expected-fail docs (`000164`, `000357`) **reproduce on 3.3.1** — 0 documents returned.
  Two engine versions, two harnesses. Cross-version confirmed.
* Dropped splitter kwargs — found **independently by all three teams**.
* Heads-up: `EXPECTED_FAIL` hardcodes filenames that match **zero** files in a `000_`-prefixed
  corpus (check passes vacuously). Propose deriving the set from the corpus manifest.
* NUL truncation re-scoped: defect still live on text lanes, but **0/303** docs have NUL (or any
  control char) in **Tika** output — under Parser IN it has no observed path on GovDocs1. The 0.30 %
  figure was pypdf-specific.

## Six decisions needed on the call

1. **Warm-up count** — Shashi 25 vs our measured 100 (LlamaIndex still 1.08× at reps 25–50; 25 bakes
   an 8 % one-arm bias). [PROVISIONAL, cheap to re-run on AWS]
2. **RocketRide parse reference** — §4.3 self-capture passes on 100 % deterministic loss (shown);
   standalone Tika false-fails on glyph mapping (4/5); **parse-tap** worked (97/98). Pick one.
3. **Memory boundary on AWS** — propose **Leela's cgroup**; ours counts our driver into RR,
   Shashi's `getrusage(SELF)` misses the engine.
4. **Driving modes** — closed-loop AND blast AND sequential, **never in one table**; every latency
   number carries its mode.
5. **Ladder to 32** — yes, but **re-measure pool width on the 32-vCPU host first** (our 17.24 is a
   macOS number); label cells above the width as past-saturation.
6. **Recovery time (M14)** — nobody has it end-to-end; we have stall/wedge raw material. Build the
   fault-injection runner jointly?

**Our named gap:** per-file corpus sha256 manifest — you both have one, ours is in progress. Until
it lands, our corpus provenance is the weakest of the three.
