# BUG: `page_content` is silently truncated at the first NUL byte in the pipeline response

**Severity: data loss, silent.** Embeddings are computed correctly over the full text; only the
text returned to the caller is lost. Nothing errors, nothing warns.

| | |
| --- | --- |
| Product | RocketRide engine |
| Version | `3.3.1.35`, hash `a0817cc6`, build stamp `2026-07-07T04:45:25Z` |
| Release / asset | `server-v3.3.1`, `darwin-arm64` |
| Bundle SHA256 | `846df27ae8b52cd3ed4975124f76462f0cac3ba2e1677a012508247efde6a836` |
| Pipeline | `webhook → preprocessor_langchain → embedding_transformer → response_documents` |
| Affected field | `documents[].page_content` |
| Reported | 2026-08-10 · Ansh Kaushik · WS-1 Service Parity |
| Evidence | `working/results/nul_characterization__20260810T023701Z__5cced3ee5969.json` |

---

## Minimal reproducer

No PDF, no large file, no unusual configuration. One string through the standard pipeline:

```python
out = await client.send(token, "AAAA\x00BBBB", mimetype="text/plain")
print(repr(out["documents"][0]["page_content"]))
```

| | |
| --- | --- |
| **Expected** | `'AAAA\x00BBBB'` — 9 characters |
| **Actual** | `'AAAA'` — 4 characters |

Everything from the first NUL byte onward is discarded from the returned text.

## The embedding is correct — this is a response-path defect only [VERIFIED]

This is the part that makes the bug dangerous rather than merely annoying. Sent a probe whose
content differs sharply before and after the NUL, then compared the returned vector against
reference embeddings of the full and truncated texts:

| comparison | cosine |
| --- | ---: |
| returned vector vs embedding of the **full** text | **1.0000** |
| returned vector vs embedding of the **truncated** text | 0.7698 |

> ### ⚠️ Vector-similarity evidence has a measured limit — read before quoting any cosine here
> **The embedder truncates at 512 tokens while our chunks are ~4,000 characters** (finding credited
> to Leela's `bench_langgraph_prod`, CONTEXT_SNAPSHOT §4.10). Measured independently here
> (2026-08-12, MiniLM CPU, text identical to N chars then divergent):
>
> | divergence at | ~tokens | cos(full, truncated) | discriminating? |
> | ---: | ---: | ---: | --- |
> | 200 | 50 | 0.7128 | yes |
> | 1,000 | 250 | 0.7499 | yes |
> | 2,000 | 500 | 0.9378 | yes |
> | **2,500** | **625** | **1.0000** | **no — indistinguishable** |
> | 4,000 | 1,000 | 1.0000 | no |
>
> **Cosine cannot detect content lost beyond ~2,000–2,500 characters into a chunk.** Two chunks that
> differ only in the tail embed identically.
>
> **This claim is UNAFFECTED**, because the measured NUL offsets are **0, 0, 50, 170, 193, 455,
> 1,144, 1,294, 2,174** — every one inside the discriminating window, which is exactly why
> `cos = 1.0000` (vs full text) against `0.7698` (vs truncated text) separated the two hypotheses.
> Had a NUL fallen past ~2,500 chars, both candidates would have returned 1.0000 and the test would
> have proved nothing. The offset 2,174 sits at the edge of that window.
>
> Content is now verified by **chunk hash** (`harness/chunk_hash.py`), which has no such blind spot.

**The engine embedded the full text.** The vector is a perfect match for the complete input and
clearly distinguishable from the truncated one. So the text is not lost on the way in — it is lost
on the way out, in response serialisation.

**Consequence:** a caller receives a correct vector alongside text that does not correspond to it.
Retrieval works; display, citation, highlighting, and any re-chunking or re-embedding from stored
text silently operate on incomplete content. There is no signal that anything was dropped.

## Scope

### Only NUL truncates [VERIFIED]

Sent `"AAAA{c}BBBB"` for every control character `0x00`–`0x1F` plus `0x7F`:

| result | characters |
| --- | --- |
| **truncates** | **`0x00` only** |
| returns intact | all 32 others (`0x01`–`0x1F`, `0x7F`) |

Clean, single-character scope. `\t`, `\n`, `\r`, `\x1b` and the rest pass through with no length
loss.

### Not PDF-specific [VERIFIED]

The reproducer above involves no PDF at all. A second plain-text probe (1,851 chars, NUL at offset
1,050) returned exactly 1,050 characters. The defect is in the text path, not the PDF reader — the
PDF corpus is merely how it was discovered.

### Only `page_content` [VERIFIED, within the fields observed]

For a document sent as `"HEAD\x00TAIL"`:

| field | value |
| --- | --- |
| `page_content` | `'HEAD'` ← **truncated** |
| `embedding` | 384 floats, correct for the full text |
| `embedding_model` | `sentence-transformers/multi-qa-MiniLM-L6-cos-v1` — intact |
| `metadata` | `{'chunkId': 0, 'isDeleted': False, 'isTable': False, 'nodeId': …}` — intact |
| `type` | `'Document'` — intact |

Top-level response keys (`documents`, `name`, `path`, `result_types`, `objectId`) are unaffected.
**Not tested:** error-message payloads and non-`response_documents` output components.

### Boundary behaviour [VERIFIED] — always cut at the *first* NUL

| input | returned | note |
| --- | --- | --- |
| `'\x00ABCDEFGH'` | `''` | leading NUL ⇒ **entire document becomes empty** |
| `'ABCD\x00EFGH'` | `'ABCD'` | cut at offset 4 |
| `'ABCDEFGH\x00'` | `'ABCDEFGH'` | trailing NUL ⇒ no visible loss |
| `'AB\x00CD\x00EF\x00GH'` | `'AB'` | multiple NULs ⇒ cut at the first |
| `'AB\x00\x00\x00CD'` | `'AB'` | run of NULs ⇒ cut at the first |
| `'\x00'` | `''` | |

The leading-NUL case is the worst: a chunk that begins with a NUL is returned completely empty
while still carrying a valid embedding of its real content.

## Prevalence in a real corpus

Discovered on GovDocs1 (`digitalcorpora.org`, US government work, public domain) — 10,000 PDFs.
Documents with broken font encodings extract to text containing NUL bytes.

**Two independent methods agree [VERIFIED].** (1) An offline scan of a seeded 1,000-document
random sample. (2) The live pipeline's own detection during a 10,000-document endurance run, which
flagged **8 affected documents in the first 2,200 = 0.36 %** — inside the sample's confidence
interval. Different failure modes: one reads extracted text directly, the other observes the
engine's returned chunks.

Sample detail:
991 documents yielded extractable text; **3 contained at
least one NUL — 0.30 %, Wilson 95 % CI 0.10–0.89 %.**
Extrapolated to the 10,000-document corpus that is roughly **30 documents (CI 10–88)**.

Low prevalence, but the loss per affected document is severe and unbounded:

> ### ⚠️ PREVALENCE IS PARSER-OUT ONLY — re-measure under Parser IN
> The ~0.30 % figure and the per-document table below were measured when our driver extracted
> with **pypdf** and sent text into the engine. Under **Parser IN** (2026-08-12) the engine
> extracts with **Tika**, and on `038_038716.pdf` — the worst case below, 98.9 % lost — the
> engine's own parse output contains **no NUL at all**, so nothing is truncated on that path.
> **The defect is unchanged and still reproduces** (`'AAAA\\x00BBBB'` → `'AAAA'` on 3.3.1.35,
> re-verified 2026-08-13). Only the PREVALENCE is in question: it must be re-derived from NUL
> counts in *Tika* extractions before being quoted for a Parser IN run.

| document | chars | NULs | first NUL at | fraction of text lost | printable ratio |
| --- | ---: | ---: | ---: | ---: | ---: |
| `027_027492.pdf` | 20,674 | 93 | 0 | **100 %** | 0.679 |
| `038_038716.pdf` | 37,772 | 4 | 422 | **98.9 %** | 0.992 |
| `039_039797.pdf` | 14,154 | 64 | 12,904 | 8.8 % | 0.988 |

**Note the second row.** Its printable ratio is 0.992 — indistinguishable from a clean document —
yet 98.9 % of its text is discarded. **The damage is not predictable from how "clean" a document
looks**, so a content-quality heuristic will not protect a consumer from this defect; only fixing
the truncation will.

The document that surfaced it: `001_001157.pdf`
(sha256 `5e35cfd71bf58da392e29b0f633f37b921648fcb9b195eb645b7a90298178ffd`, 348,092 bytes, 6 pages).
Its extracted text is 39,803 characters containing multiple NULs. Chunked at 4,000/200 it produces
11 chunks, of which the returned text was truncated in **9**, two of them to empty:

| chunk | 0 | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 | 10 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| source length | 3933 | 3999 | 3984 | 3998 | 3988 | 3999 | 3975 | 3994 | 3969 | 3979 | 1867 |
| first NUL at | 0 | 0 | 170 | 193 | 455 | 1294 | — | 2174 | — | 1144 | 50 |
| returned length | 0 | 0 | 170 | 193 | 455 | 1294 | 3975 | 2174 | 3969 | 1144 | 50 |

Returned length equals the first-NUL offset in **11/11** chunks, including the two chunks with no
NUL, which return in full.

## Negative control

Identical pipeline, identical chunking, clean ASCII text with no control characters: returned chunk
lengths are byte-identical to the reference implementation across all 11 chunks. The truncation
appears only when a NUL is present.

## Suspected cause

C string semantics reaching the response path — a `char*`/`strlen`-style boundary where a
length-delimited string is required. The engine core is C++ and the node runtime is embedded
CPython, so the likely site is the marshalling of node output back into the response, rather than
the Python node itself (the Python node has the full string, since the embedding is correct).

**Not verified** — this is an inference from the observed behaviour and the architecture. The
authoritative check is on the maintainers' side.

## Suggested fix

Carry node output as length-delimited bytes end to end. If NUL is genuinely unsupported in
`page_content`, then **fail loudly or sanitise explicitly and report it in `metadata`** — the
current behaviour returns a confident, well-formed response whose text silently disagrees with its
own embedding, which is the worst of the three options.

## What a maintainer might reasonably ask

> *"Is a NUL byte even valid in a text document?"*
> Arguably not — but it arrives routinely from real PDF extraction with broken font encodings, and
> the pipeline accepts it, embeds it correctly, and returns a success. If it is unsupported it
> should be rejected or sanitised visibly, not dropped silently.

> *"Could this be the splitter, not the engine?"*
> No. The splitter's chunk boundaries are unaffected — chunk count and the boundaries themselves
> match the reference implementation exactly. Only the returned text differs, and the embedding
> proves the full text reached the encoder.

> *"Is it specific to `response_documents`?"*
> Untested against other output components. That is the one gap in this report.
