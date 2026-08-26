# Hostile-reviewer audit — RR vs LI video, before the final apples run (2026-08-25)

State audited: RR-parity 16x2 = 12.741 f/s @91.9% (n=2, banked, earlier
session); RR 8x4 = 12.048 @93.9% (n=1); LI-balanced 8x4 = 13.555 @~94.9%
(n=2, CPU SPOT-measured — the Task-1 collector defect means this CPU figure
is not yet quotable; the fix landed at 7c1cd81 and the rerun measures it
properly). Detection agreement PASS 168/168.

## Task 2 — every remaining asymmetry in the 8x4 cell
Direction: +RR = flatters RocketRide, +LI = flatters LlamaIndex.
P = product property, C = our choice.

| # | asymmetry | direction | P/C | note |
|---|---|---|---|---|
| 1 | Transport: RR ~237 x 1 MiB DAP request/responses per video on ONE shared websocket vs LI whole-body HTTP on 16 independent connections | +LI (RR pays round-trips + shared-socket serialization) | P-adjacent | whole-frame is the SDK's send(); it cannot survive this payload x C (measured, 3 deaths); chunked = the SDK's own send_files shape. Quantified by probe_transport_cost.py (Task 3) |
| 2 | Memory shape: 1x58g vs 8x7g (16x2: 16x3g) | slight +RR (LI instance can hit its 7g lid while the box has room; RR pools) | C | observed LI peaks 1.1-2.3 GiB -> lids have >=3x headroom; wait_ready fails loudly if wrong |
| 3 | Idle burden: RR 2.83 cores (16 idle tokens spinning, Ticket 4) vs LI 0.005 | -RR on every CPU-efficiency metric (numerator inflated by non-work burn); NEUTRAL on f/s | P | reported-beside per standing ruling, never subtracted |
| 4 | Queue depth at C=16: RR 16 lanes -> <=1 deep; LI 8x4 -> 2 deep per instance | -LI on per-video wall_s/latency (queue inside wall); ~neutral on throughput | C | **the 16x2 LI cell equalizes this to <=1 deep — the core reason 16x2 is the right headline cell (Task 4)** |
| 5 | cgroup accounting: RR's single cgroup INCLUDES the non-serving engine master (web server); LI's 8 cgroups contain only serving workers | -RR slightly (master burn charged to RR service CPU) | P | small; disclose |
| 6 | Image vintage: rr baked 2026-08-22 (deliberately frozen, Crossroad 33) vs li REBUILT 2026-08-25 with unpinned pip | unknown direction | C | per-run pip freeze recorded; disclose; both LI cells share the new image so LI-internal comparisons are clean |
| 7 | Splitter overlap realization: RR embeds ~4.75% fewer chars for identical frames (langchain whole-unit overlap = 0 on this corpus vs LI ~200) | +RR ~1-2% on f/s and cpu/frame (embed is a large stage share) | P | CHAR_CONSERVATION_MECHANISM.md; disclose beside the headline, or report chars/s alongside frames/s |
| 8 | ~~In-wall hashing~~ **FIXED (ruling 2026-08-25):** chunk hashes now computed driver-side from returned texts (same formula/place as RR, values identical by construction — controlled); frame hashes removed from the serving path (no leg-gate consumer). Responses+records carry `hashing_locus`; banked legs self-describe as in_service_in_wall | was -LI, now closed | C | image rebuilt; never silently compared |
| 9 | Response payload: LI returns frame arrays + hashes over HTTP inside wall; RR returns documents only | -LI, small | C | bundled with #8 as "instrumented-arm overhead" |
| 10 | Warm-up: both driver-addressed round-robin (tokens / ports); RR gate = tokens-seen, LI gate = markers | symmetric | — | closed by Crossroads 40/41 + balanced mode |
| 11 | ffmpeg uncapped, corpus, order, eviction, reads-in-threads, C=16, breaker | symmetric | — | verified previously |

## Task 3 — transport probe (committed: probe/probe_transport_cost.py)
Same container, same token, same file, C=1, strictly interleaved
whole/chunked pairs, unmeasured warm send first, refuses to summarize if
same-mode spread exceeds the mean delta (rc=2 INCONCLUSIVE). It is cleanly
measurable at C=1; it is NOT measurable at C=16 (whole-frame dies there —
that death is itself the recorded reason the delta cannot be measured at
concurrency, and the C=1 delta is a LOWER bound on what chunking costs
under contention).

## Task 4 — is 8x4 the right cell? No: 16x2 is the headline cell.
RR's own balanced sweep prefers 16x2 (12.741 > 12.048), and 16x2 equalizes
per-instance queue depth at C=16 (asymmetry #4). LI 16 instances is
FEASIBLE: observed 1.1-2.3 GiB/instance -> 16 x 3g lids = 48g of 61
(models dominate; torch=2 shrinks arenas slightly). 8x4 stays as the
secondary cell (both arms measured there too). Bring-up is li_leg 16 2 in
overnight_apples.sh.

## Flags beyond the listed items (Task "anything misjudged")
1. **The headline pairing is cross-session:** RR 16x2 is banked from an
   earlier session; LI 16x2 runs tonight. Cheapest insurance if the gap is
   close: add RR 16x2 p1/p2 in-session (+~2.8h, 8 legs total). Flagged for
   ruling, not assumed.
2. **LI 13.555 vs RR 12.741 is a 6.4% gap** — asymmetries #7 (+RR ~1-2%)
   and #8 (-LI, similar order) are the same magnitude as a third of that
   gap. They must be disclosed with direction, or the wall/hashing moved
   out; a hostile reviewer finds either in a day.
3. **n=2 everywhere:** by Leela's own published standard this is "sizing
   evidence"; the determinism gate semantics differ across arms (RR repeat
   on sequential legs only). Label the run accordingly or add reps.
4. **LI CPU% provenance:** every LI-balanced CPU figure quoted so far was
   spot-measured during the collector defect; nothing CPU-side from those
   runs is quotable. The rerun with 7c1cd81 is the first quotable LI
   efficiency measurement.
5. RR 8x4 n=1 today — tonight's plan fixes that (n=2 fresh, interleaved).
