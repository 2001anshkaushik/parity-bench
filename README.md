# parity-bench

Measurement work for **WS-1 "Service Parity"**: two implementations of the same document pipeline —
the **RocketRide engine** and a **LlamaIndex FastAPI service** — running PDF → text → chunks →
384-d embeddings, plus the instrumentation built to make that comparison trustworthy.

**Private. Not for distribution outside the team.**

---

## Start here

| you want to… | read |
| --- | --- |
| **build or reproduce the harness** | [`publishable/BENCHMARK_SETUP.md`](publishable/BENCHMARK_SETUP.md) — §7 is the pitfalls table, the most useful page in the repo |
| **see current findings** | [`publishable/MEETING_2026-08-10.md`](publishable/MEETING_2026-08-10.md) |
| **check what a number means, or whether it still stands** | [`publishable/STATE.md`](publishable/STATE.md) — §5 is every withdrawn number, with why |
| **run it** | [`publishable/PROVISIONING.md`](publishable/PROVISIONING.md) first — the engine and corpus are not in this repo |

## Headline result

**Under a matched configuration the two implementations are functionally identical except for one
defect.** [**VERIFIED** — 3 blocks × 2,000 documents per arm, interleaved, reproduced 3/3]

| arm | goodput (3 blocks) | faults | content-suspect |
| --- | --- | --- | --- |
| LlamaIndex | 1,972 · 1,972 · 1,972 | 28 · 28 · 28 | 23 · 23 · 23 |
| RocketRide | 1,965 · 1,965 · 1,965 | 35 · 35 · 35 | 23 · 23 · 23 |

Identical to the document, every block. The arms differ by **exactly 7 documents per 2,000
(0.35 %)**, and every one is the same defect: [`BUG_NUL_TRUNCATION.md`](publishable/BUG_NUL_TRUNCATION.md).

### Other findings that stand

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

## How claims are labelled

Every claim carries **VERIFIED** (two independent methods, reproduced) / **PROVISIONAL** (one
method) / **UNVERIFIED** (asserted, not established). Numbers that did not survive are not deleted
— they are listed with the reason in `STATE.md` §5. **More findings have been withdrawn than kept**,
including several that were favourable, and the corrections run in both directions.

## Layout

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

## Not in this repo

| excluded | size | how to get it |
| --- | ---: | --- |
| `engine/` — engine bundle | ~1.2 GB | [`PROVISIONING.md`](publishable/PROVISIONING.md) §1. Also contains a **hand-copied pypdf** inside its embedded interpreter that is not manifest-reproducible — §3 |
| `corpus/` — GovDocs1 PDFs | ~5.9 GB | public domain, digitalcorpora.org; fetch script in `working/scripts/` |
| `data/` — mt10k sample | 4 MB | rebuildable from Leela's manifest (sha256-verified) |
| model weights | — | baked at image build; `HF_HUB_OFFLINE=1` at runtime |
| `.venv/`, logs, generated pipes | — | regenerable |

`.env` is excluded on principle. It holds only a local URI and the placeholder key `MYAPIKEY`, but
committing it is a habit that eventually leaks a real one — copy `.env.example` instead.

## First thing to run

```bash
../.venv/bin/python working/scripts/regression_selftest.py
```

Ten tests, one per defect that produced a wrong number in this project. It is the fastest way to
find out whether your environment differs from the one these results came from.
