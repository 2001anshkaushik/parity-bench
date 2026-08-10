# WS-1 LlamaIndex Service — Readiness Verdict

**What the service is ready for, what it is not, and the exact gap list.**
Ansh · 2026-08-07.

---

> ## 🛑 CORRECTION 2026-08-09 (session 11) — SATURATION POINTS IN THIS DOCUMENT ARE WITHDRAWN
>
> Ascending concurrency sweeps measure a machine in a low-power state. With a 30 s pre-warm the
> same harness reads **2.2× higher above c8** and saturation moves from c4 to **c16 (~226 /s at
> 400 tokens)**. Readiness gate, RSS sampler, background load, sustained decay and harness design
> were each ruled out by direct experiment first. See the session-11 correction at the head of STATE.md §4b.
>
> **Do not quote any saturation point or operating-point comparison from this document.**



## Verdict in one line

**Ready for text-in/embeddings-out benchmarking up to concurrency 4. Not ready for PDF ingestion,
not ready for head-to-head reporting, and not ready for container work.**

## Ready — established by measurement

| capability | evidence |
| --- | --- |
| Text embedding pipeline, split + embed, wire contract stable | `ws1/smoke.py` ALL PASS; used in every measurement since session 4 |
| Device pinned to CPU and **asserted at startup** (refuses to boot on a mismatch) | `ws1/pipeline.py`; finding 6 — `mps` is silently selected otherwise, with 14–25 % irreducible variance |
| Correct under sustained load | **0 errors in ~10,000 requests** (session 6) and **0 errors across all 70 concurrency cells** in the isolated profile, up to concurrency 64 |
| Does not decay under sustained load | +1.0 % median over n=3 randomised sequences (session 6) |
| Saturation profile characterised | `results/isolated_profile_llamaindex.json` |
| Memory envelope known | idle 4,642 MB → peak 7,950 MB at 6,400 tok / conc 32 |
| PDF text extraction available | **pypdf 6.15.0 installed this session** (BSD-3-Clause, per the licence finding) |

### The operating range, which is narrower than we have been using

| tokens/doc | peak throughput | **saturation** | at saturation | past saturation |
| ---: | ---: | ---: | --- | --- |
| 400 | 74.7 /s | **concurrency 4** | P50 51 ms, P99 81 ms | c=64: P99.9 **2,987 ms**, throughput *lower* (58.7 /s) |
| 1,600 | 29.1 /s | **concurrency 4** | P50 135 ms, P99 210 ms | c=64: P99.9 **4,605 ms**, throughput flat |

**Beyond concurrency 4 this service buys latency, not throughput.** Throughput is flat-to-degrading
from c=8 onward while tail latency grows roughly linearly with offered load — textbook queueing
past saturation.

**This invalidates the operating point of most of our prior head-to-head work.** Sessions 6–8
compared at concurrency 8, 16 and 32 — all past this service's saturation. Numbers taken there
measure queue behaviour, not serving capacity. **[VERIFIED, one method — the profile is n=5 gated
per cell but has not been reproduced in a second session, so the exact saturation point is
PROVISIONAL; the shape is unambiguous.]**

⚠️ **The automated "knee" figure in the raw JSON is unreliable.** The rule (last doubling that
bought ≥15 %) reports c=32 at 1,600 tokens because 25.4 → 30.6 /s looks like a gain; it is noise
recovery in non-monotonic data, not scaling. **Use the saturation point (c=4), not the knee field.**

## Not ready — the gap list for head-to-head

| # | gap | blocks | cost |
| --- | --- | --- | --- |
| 1 | **RocketRide has no isolated profile.** We now know one arm's saturation point and not the other's. Choosing a shared concurrency needs both | any head-to-head at a defensible concurrency | ~40 min |
| 2 | **`llama-index-readers-file` still absent.** pypdf is installed, but the framework's own `PDFReader` wrapper is not. Core maps `.pdf → PDFReader` and **silently returns `{}`** when it is missing — PDFs are skipped, not errored | Tier 2 PDF work using the framework's native path | ~15 min |
| 3 | **No PDF path wired into `ws1/pipeline.py`.** The library is present; the service still only accepts text | any PDF measurement | ~1 h |
| 4 | **Ground-truth extraction references do not exist** | Tier 2 quality scoring (`TWO_TIER_PARSER_DESIGN.md`) | ~1 h |
| 5 | **PDF corpus not selected or manifested** (SEC EDGAR proposed, nothing fetched) | all PDF work | ~1.5 h |
| 6 | **Tika JVM startup cost unmeasured** — per-request, per-task-process, or once per engine is unknown and would dominate a Tier 2 number | Tier 2 speed figures | ~20 min |
| 7 | **Container work not started** and the VM allocation is still declared-not-measured | everything containerised | gated on `docker info` |
| 8 | **Between-session drift unexplained** (open item F). The session-8 null control moved +3.4 % median, up to +19.5 % | any cross-day comparison | ≥1 h |

## Two asymmetries that must be disclosed with any result

1. **Worker count is tuned on this arm and untunable on the other.** We set `--workers 8` from a
   measured knee; RocketRide's ~17 width is not configurable from outside (open item H). **Favours
   LlamaIndex.**
2. **I build, tune and measure this arm.** Declared in `TOIL_INSTRUMENT.md` §1; the RocketRide
   column is Shashi's to fill.

## What changed this session

* **pypdf 6.15.0 installed** into the measurement venv — chosen because it is permissive
  (BSD-3-Clause) *and* LlamaIndex's own default, so it needs no fairness justification.
  **PyMuPDF was rejected: AGPL-3.0.** See `PARSER_PREMISES.md`.
* **Saturation characterised** — the first time any operating point in this project has been chosen
  from evidence rather than picked.
* **Fairness asymmetry 2 closed**: inter-op thread pinning was tested and *rejected* — it costs
  14.3 % at concurrency 8 and does nothing at concurrency 2. The engine's default is correct.

## Recommended next step

**Run the isolated profile against RocketRide** (gap 1). It is the cheapest item on the list, it
closes the last blocker to a defensible head-to-head, and until it exists we cannot honestly choose
the concurrency at which to compare — which is the mistake this whole phase exists to correct.
