# Weekend Run — Forensics

**Ansh · 2026-08-09.** Forensic analysis of the unattended run launched 2026-08-07 22:42.
Every claim is labelled. Denominators are stated before conclusions.

---

## 0. Denominators first — one failure in N means nothing without N

**Both arms ran NATIVELY.** No containers were involved in this run (verified: the only running
containers are MCP servers; `LlamaArm` loads `LlamaIndexPipeline` in-process). The containerised
LlamaIndex ladder in `DOCKER_DEMO_RESULTS.md` is a **separate artifact from a different run** and
its numbers are not comparable to these. **This run is already native-on-native and is the
symmetric comparison.**

| phase / arm | status | docs attempted | goodput | faults | fault classes | peak RSS | elapsed |
| --- | --- | ---: | ---: | ---: | --- | ---: | ---: |
| p0 insurance · LlamaIndex | completed | 200 | 198 | 2 | empty_extraction 2 | 951 MB | 0.02 h |
| p0 insurance · RocketRide | completed | 200 | 198 | 2 | empty_extraction 2 | 3,034 MB | 0.04 h |
| **p2 · LlamaIndex** | **completed** | **10,000** | **9,898** | 102 | empty_extraction 94, PdfReadError 7, LimitReachedError 1 | 1,250 MB | 1.12 h |
| **p3 · RocketRide** | **goodput_failure** | **267** | 265 | 2 | empty_extraction 2 | 2,236 MB | 0.06 h |
| p4 sim · LlamaIndex | cap reached | 8,888 | 8,794 | 94 | empty_extraction 87, PdfReadError 6, LimitReachedError 1 | 1,255 MB | 1.00 h |
| p4 sim · RocketRide | **goodput_failure** | **267** | 265 | 2 | empty_extraction 2 | 2,348 MB | 0.06 h |

**The single most important number here: RocketRide processed 267 documents, LlamaIndex processed
10,000.** Every RocketRide statement below rests on a 267-document sample, 2.7 % of the corpus.

> **There is no RocketRide endurance result.** It stopped at 2.7 % of the corpus. Any claim about
> its behaviour over 10,000 documents is UNVERIFIED and cannot be made from this run.

The three LlamaIndex fault classes are **pypdf extraction faults that occur before either arm sees
the text**, in shared harness code. They are corpus properties, identical for both arms — not a
framework difference.

## 1. Document 267 — VERIFIED, reproducible, and it is a payload bug not a compute bug

### The trace

Both p3 and p4 failed on **the same document at the same index** with the identical message:

```
[GOODPUT FAILURE] 001_001157.pdf: 2 empty chunk(s) at [0, 1]
```

Gate check **#2** fired (every chunk non-empty after strip). Not a crash, not a timeout, not
memory, not a dimension or norm failure.

### The document

| | |
| --- | --- |
| name / index | `001_001157.pdf`, corpus index **267** (confirmed by sorted position) |
| sha256 | `5e35cfd71bf58da392e29b0f633f37b921648fcb9b195eb645b7a90298178ffd` |
| size / pages | 348,092 bytes · 6 pages |
| extracted | 39,803 chars · ~9,950 tokens |
| in the known 1.42 % malformed set? | **No.** Manifest `fault` field is null — it parsed cleanly |

**But the extracted text is binary garbage**: `\x00\x02\x01\x04\x03\x06\x05\x08...` — a broken font
encoding, so glyph codes map to control characters rather than Unicode. It survives the harness's
`empty_extraction` check because control characters are not whitespace, so `.strip()` leaves 39,801
characters.

### Reproduction — VERIFIED

Fed the single document to RocketRide three times in isolation:

| run | chunks | non-empty | vector dims | gate |
| --- | ---: | ---: | --- | --- |
| 1 | 11 | 9 | all 384 | FAIL: 2 empty chunks at [0,1] |
| 2 | 11 | 9 | all 384 | FAIL: 2 empty chunks at [0,1] |
| 3 | 11 | 9 | all 384 | FAIL: 2 empty chunks at [0,1] |

**3/3 identical. This is a deterministic, document-specific failure, not a transient.**

### Did LlamaIndex handle it? Yes — and that is the sharpest form of the finding

Same input text, same chunk parameters: **LlamaIndex produced 11/11 non-empty chunks and passed
the gate.** RocketRide produced 11 chunks of which 2 were empty.

### The mechanism — VERIFIED, with a null control

The embeddings are **not** wrong. Cosine similarity between the two arms' vectors, chunk by chunk:

```
chunk    0      1      2      3      4      5      6      7      8      9     10
cos   1.0000 1.0000 1.0000 1.0000 1.0000 1.0000 1.0000 1.0000 1.0000 1.0000 1.0000
```

**RocketRide computed exactly the same embeddings as LlamaIndex on all 11 chunks**, including the
two whose text came back empty. Those two vectors are also *not* embeddings of empty text
(cos 0.177 / 0.142 against `embed(" ")`). So the engine had the full text internally and embedded
it correctly.

What differs is the **returned text**. Predicted mechanism: the response truncates at the first NUL
byte, i.e. C string semantics leaking into serialisation. Test — for each chunk, is the returned
length exactly the offset of the first `\x00` in the corresponding source chunk?

| chunk | 0 | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 | 10 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| source length | 3933 | 3999 | 3984 | 3998 | 3988 | 3999 | 3975 | 3994 | 3969 | 3979 | 1867 |
| first `\x00` at | 0 | 0 | 170 | 193 | 455 | 1294 | *none* | 2174 | *none* | 1144 | 50 |
| returned length | 0 | 0 | 170 | 193 | 455 | 1294 | 3975 | 2174 | 3969 | 1144 | 50 |
| match | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |

**11/11 exact, including the two chunks with no NUL, which return in full.**

**NULL CONTROL** (rule 3 — predicted no difference): identical pipeline, clean ASCII text with no
control characters. Chunk lengths returned by the two arms: **byte-identical, all 11 chunks.**

> ### The finding, stated precisely
> **RocketRide's response payload truncates `page_content` at the first NUL byte.** Embeddings are
> computed correctly over the full text; only the returned text is lost. **[VERIFIED]** —
> deterministic (3/3), mechanism confirmed on 11/11 chunks, null control clean.
>
> **Operational impact:** a RAG system over documents containing NUL bytes would retrieve the right
> chunks and display truncated or empty text. The failure is silent — vectors look perfect.

### Fault isolation — the claim that matters more than the failure

**The engine did not crash and did not cascade [VERIFIED].** It answered `/version` normally
afterwards, and the null-control document ran through the *same* engine immediately after the
failing one and returned full-length chunks. The run stopped because **our gate is deliberately
fatal**, not because the engine died.

### ⚠️ The gate cut against RocketRide here, and that deserves saying plainly

Rule 5 in reverse. **LlamaIndex "passing" on this document is arguably the worse outcome**: it
embedded 39,803 characters of binary control codes into eleven confident, unit-norm 384-d vectors.
Every check in our gate passed. The gate verifies *shape*, not *meaning* — it cannot distinguish a
real embedding from a fluent-looking embedding of garbage.

So the honest framing is not "RocketRide failed where LlamaIndex succeeded". It is:

* RocketRide **loses text** it correctly embedded — a real, reproducible bug.
* LlamaIndex **silently embeds garbage** as though it were content — a real, undetected risk.
* Our instrument flags the first and is blind to the second. **That is an instrument limitation,
  logged as an open item**, not a point in either framework's favour.

## 2. The memory slope — the instrument was validated first, and the figure did not survive

### What the sampler actually counted [DECLARED ≠ MEASURED]

RocketRide's sample was `engine_tree_rss_mb() + rss_mb()`: a `psutil` scan matching processes whose
name is exactly `engine`, plus that process and all its recursive children, plus the worker's own
RSS. LlamaIndex's sample was the worker RSS alone (the model is in-process).

Two defects:

1. **Name-matching counted an unrelated engine.** Two `engine` processes were resident. One
   (pid 11835, port 5565, age 55.8 h) *is* the run's engine — correctly counted. The other
   (pid 32361, a different installation under `~/Library/Application Support`, age 129 h) predates
   the run entirely and was **wrongly included: 104 MB**, about **5.8 %** of RocketRide's median.
2. **A task process living less than one sample interval is invisible to a tree walk.** In this run
   the worker creates **one long-lived task** reused for the whole phase, so there is no
   per-document process churn — the exposure is low here, but the instrument cannot prove it.
   **Cross-check available but not applicable retroactively:** system-wide used-memory deltas
   (`vm_stat`) cannot miss any resident process regardless of parentage or lifetime. The weekend
   run did not record it, so these numbers cannot be corrected after the fact. **Logged as a
   required instrument fix.**

### The +1,505 MB / 1,000 docs figure is WITHDRAWN

It was computed over a **267-document window** against LlamaIndex's **10,000-document** window.
Same-window and ramp-excluded numbers:

| window | LlamaIndex | RocketRide |
| --- | ---: | ---: |
| including warm-up ramp, docs ≤ 267 | **+971** MB/1k | **+3,158** MB/1k |
| **excluding ramp, docs 50–267** | **−22** MB/1k | **−642** MB/1k |
| full run, post-ramp, docs 50–10,000 | **+15** MB/1k | *not measured — arm stopped at 267* |

**Both arms show a NEGATIVE slope once warm-up is excluded.** A negative leak is not a physical
claim; it is proof that an endpoint-fitted slope over this window measures oscillation, not trend.

RocketRide's series oscillates with an amplitude of **487–751 MB** within each half of the
post-ramp window, against a half-to-half median difference of only **+252 MB**. The oscillation is
2–3× larger than the "trend" being fitted.

> **[WITHDRAWN]** "RocketRide leaks ~1,500 MB per 1,000 documents." The figure is an artifact of
> (a) including the warm-up ramp and (b) endpoint placement inside a ±500 MB oscillation, over a
> window 37× shorter than the arm it was compared against.

### Leak vs allocator retention — answerable only for LlamaIndex

**LlamaIndex [VERIFIED — two independent windows under different conditions]:** the post-ramp
slope is **+14.8 MB/1k** in p2 (sequential, 10,000 docs) and **+20.4 MB/1k** in p4 (simultaneous
with RocketRide competing for the machine, 8,888 docs). Two runs, different contention regimes,
same near-flat answer. Detail: current RSS
plateaus (685 → ~1,090 MB) while the running peak drifts 685 → 1,241 MB. Post-ramp slope
**+15 MB / 1,000 docs**, band 853–1,241 MB. Peak rising slowly while current is flat is the
signature of **allocator retention with a slowly-climbing high-water mark, not runaway
accumulation**. Extrapolated, 10,000 further documents would add ~150 MB.

**RocketRide: UNVERIFIED.** 267 documents and 53 samples is not enough to separate leak from
retention. **The experiment that would settle it:** re-run p3 past the NUL document (skip index 267
or relax the gate to a warning) for ≥ 2,000 documents and check whether peak stays pinned while
current oscillates. **~40 min. Not run — the arm never got there.**

## 3. Native-vs-native memory — the only quotable comparison

Both arms, native, same corpus, same documents, same gate, same session.

| window | LlamaIndex peak | RocketRide peak | ratio | LlamaIndex median | RocketRide median | ratio |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| p0 insurance, 200 docs | 951 MB | 3,034 MB | **3.19×** | — | — | — |
| p2/p3, docs 0–267 | 975 MB | 2,235 MB | **2.29×** | 922 MB | 1,785 MB | **1.94×** |
| p2/p3, 0–267, minus the 104 MB stale engine | 975 MB | 2,131 MB | **2.19×** | 922 MB | 1,681 MB | **1.82×** |

**[VERIFIED direction — two independent windows, both arms native, same session]** RocketRide's
resident memory is materially higher than LlamaIndex's on identical work.
**[PROVISIONAL magnitude]** the ratio ranges 1.82×–3.19× depending on window and statistic; there
is no single defensible number, and the corrected same-window median ratio of **1.82×** is the most
conservative reading.

**Why the two arms differ structurally:** RocketRide's total spans a worker process *plus* an
out-of-process engine tree that holds the model in a separate task process; LlamaIndex holds one
model in one process. This is a real deployment difference, not an accounting error — but it means
the ratio would move with worker count on either side, and it is **not** a per-document memory
efficiency figure.

> *Hostile reviewer: "You measured RocketRide over 267 documents and LlamaIndex over 10,000, then
> compared memory. Why is that legitimate?"*
> The memory comparison uses **only the overlapping 0–267 window on both arms**, plus a second
> independent 200-document window (p0). The 10,000-document figures are reported separately and
> never set against a 267-document number.


## 3b. MATCHED-WINDOW MEMORY (session 14) — supersedes the ratios in §3

§3 compared a 267-document RocketRide window against LlamaIndex windows of different sizes, and
its RocketRide numbers included 104 MB from an unrelated engine. Both are fixed here: the
endurance re-run resolves the engine **by PID via lsof**, and only ranges both arms covered are
compared, post-warm-up (n ≥ 50).

| window | LlamaIndex median | RocketRide median | ratio | LI amplitude | RR amplitude |
| --- | ---: | ---: | ---: | ---: | ---: |
| docs 0–267 | 938 MB | 1,954 MB | **2.08×** | 122 MB | 1,675 MB |
| docs 0–2,100 | 972 MB | 2,018 MB | **2.08×** | 238 MB | 1,783 MB |

**The ratio is identical at both windows despite a 7.9× increase in coverage** — the strongest
evidence yet that ~2× is the real figure rather than a window artifact.

**A second, separate finding: RocketRide's memory is far less stable.** Its oscillation amplitude
is **7–8× LlamaIndex's** (1,675–1,783 MB against 122–238 MB). That is about predictability of
provisioning, not average consumption, and it is what makes any single peak reading unreliable.

### Reproducibility — n=3 over the identical first 200 documents

| run | median (post-warm-up) | correction |
| --- | ---: | --- |
| p0 insurance | 2,501 → **2,397 MB** | −104 MB stale engine |
| p3 weekend | 1,743 → **1,639 MB** | −104 MB stale engine |
| endurance (session 14) | **1,811 MB** | PID-matched, no contamination |

**Spread 758 MB — 42 % of the median, on byte-identical input.** LlamaIndex over the same window:
940 MB. Ratio across the three runs: **1.74×–2.55×**.

> **Direction [VERIFIED]** — three independent runs, two matched windows, both arms native:
> RocketRide's resident memory is about **2× LlamaIndex's** on identical work.
> **Magnitude [PROVISIONAL]** — 1.74×–2.55× run to run; 2.08× at matched windows is the best
> estimate. Quote the direction and the range, never a single decimal.

> *Hostile reviewer: "42 % run-to-run spread — is your instrument just noisy?"*
> The same instrument reads LlamaIndex with an amplitude of 122–238 MB over the same windows, so
> it resolves that arm to within a few percent. The spread is in the system under test, and it is
> itself a reportable property.

## 4. What is defensible, in one table

| claim | label | basis |
| --- | --- | --- |
| RocketRide truncates returned `page_content` at the first NUL byte | **VERIFIED** | 3/3 reproduction, 11/11 chunk-level mechanism match, clean null control |
| RocketRide's embeddings are correct on that document | **VERIFIED** | cos = 1.0000 vs LlamaIndex on all 11 chunks |
| The engine did not crash or cascade | **VERIFIED** | `/version` healthy, null control ran on the same engine immediately after |
| LlamaIndex completed 10,000 documents, 9,898 goodput, 102 corpus-level faults | **VERIFIED** | phase checkpoint, 1,974 samples |
| LlamaIndex post-ramp memory ≈ flat (+14.8 and +20.4 MB/1k) | **VERIFIED** | two independent windows, sequential and under contention |
| RocketRide resident memory ~2x LlamaIndex on identical work | **VERIFIED (direction)** | 3 runs, 2 matched windows, PID-clean (see 3b) |
| Magnitude 1.74x-2.55x run-to-run; **2.08x** at matched windows | **PROVISIONAL** | superseded the 1.82-3.19x range in section 3 |
| RocketRide memory oscillation is 7-8x LlamaIndex's | **VERIFIED** | amplitude 1,675-1,783 MB vs 122-238 MB |
| "RocketRide leaks 1,500 MB / 1,000 docs" | **WITHDRAWN** | window mismatch + oscillation artifact |
| RocketRide behaviour beyond 267 documents | **UNVERIFIED** | never measured; 2.7 % of the corpus |
| Our goodput gate detects garbage-in | **REFUTED** | it passed 39,803 chars of binary as 11 valid vectors |

## 5. Fixes — APPLIED AND VERIFIED this session

All five are implemented in `weekend_worker.py` / `weekend_summarise.py` and demonstrated, not
merely described.

| # | fix | verification |
| --- | --- | --- |
| 1 | **Match the engine by PID, not name.** Resolved via `lsof -nP -iTCP:5565 -sTCP:LISTEN`, with the `logs/engine.pid` file as fallback | Measured live: tree **by name 215 MB, by PID 111 MB** — **104 MB of contamination removed**, independently reproducing the figure estimated in §2 |
| 2 | **Record system-wide memory** (`system_used_mb()`) alongside the tree walk, so the tree walk becomes falsifiable | Returns a value; wired for the next run |
| 3 | **Slope gated on window length** — no slope reported unless ≥500 documents remain after dropping the warm-up ramp | Regenerated summary now prints `window too short` for every 267-document arm and reports only the two ≥8,888-document LlamaIndex windows |
| 4 | **Content gate made non-fatal.** Classify and continue; abort only after 25 *consecutive* goodput failures, which is the systemic case the gate exists to catch | Re-ran across document 267: logged `[goodput fault]` and **ran to completion at n=275**, where the old gate ended the phase |
| 5 | Garbage-input check (printable-character ratio) | **NOT implemented** — logged as an open item; see §1 |

> ⚠️ **Fix 1 was itself wrong on the first attempt and is worth recording.** The initial version used
> `psutil.net_connections()`, which requires root on macOS and returns nothing without it — so the
> lookup silently produced `pid=None` and fell straight back to name matching. It *looked* applied
> and was not. Caught only by printing the resolved PID. That is the same class of failure as the
> instrument defect it was meant to fix.

### Original text of this section

Required fixes before the next run

1. **Match the engine by PID, not by name.** Record the PID at engine start and walk only that
   tree. Name-matching silently counted a five-day-old unrelated engine.
2. **Record system-wide memory alongside the tree walk.** It cannot miss short-lived processes and
   makes the tree walk falsifiable rather than trusted.
3. **Discard the warm-up ramp before fitting any slope**, and refuse to report a slope whose
   window is shorter than the oscillation period.
4. **Make the goodput gate non-fatal for content faults.** A single pathological document ended a
   16-hour phase at 2.7 % completion. Classify and continue; abort only on systemic failure.
5. **Add a garbage-input check to the gate** — e.g. printable-character ratio of chunk text. The
   gate currently cannot tell a real embedding from a confident embedding of binary noise.
