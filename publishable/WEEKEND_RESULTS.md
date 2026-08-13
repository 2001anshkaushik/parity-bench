# Weekend Run — rolling results

> ### ⚠️ MEASURED PARSER-OUT — needs re-baselining under Parser IN (scope change 2026-08-12)
> Every number in this section was measured with **PDF extraction in the driver**, common-mode to
> both arms and outside each arm's measured region. The team has since standardised on **Parser
> IN**: extraction moves inside each framework so the whole product is benchmarked (Tier 2 in
> [`PARSER_DECISION.md`](PARSER_DECISION.md), chosen deliberately over the Tier 1 framework
> comparison these numbers represent).
>
> **Parsing adds work to both arms, in directions not yet measured.** The engine now runs Tika 3.2.3
> in-process; the LlamaIndex service now runs pypdf inside its workers. Memory and wall clock will
> both move, and **the C ≈ 3.2 memory crossover in particular may move** — it sits between two
> quotable levels only 2 apart.
>
> **These numbers are NOT withdrawn and NOT overwritten.** They are a valid Tier 1 framework
> comparison. They are simply no longer the topology the team is measuring. Re-baseline before
> quoting alongside any Parser IN result, and never place the two in the same table.
>
> **Also changed:** goodput and fault counts now include parser behaviour, so they are not
> comparable with the counts below.

_Generated 2026-08-09T19:44:43 from 7 checkpoints._

**Both arms ran NATIVELY, not containerised.** `server-v3.3.1` ships darwin-arm64, linux-x64 and win64 — there is no linux-arm64 build — so containerising RocketRide on this host would need x86 emulation, which would corrupt exactly the numbers being measured. Running one arm containerised and one native would be asymmetric, which is worse. The memory ceiling is therefore a SOFT limit enforced by the worker, not a cgroup: a breach is detected and recorded, but it is not proof the process would have been killed at that point.

**Throughput is not reported.** Rates from this host are invalid (open item A13).

**Slope is reported only where the window is long enough to mean anything** (>=500 documents after the warm-up ramp). A slope fitted across a shorter window measures oscillation, not trend: the withdrawn +1,505 MB/1k figure came from exactly that mistake. See `WEEKEND_FORENSICS.md` section 2.

| phase / arm | status | docs | goodput | faults | peak RSS | post-ramp slope /1k | elapsed |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `endurance_rocketride` | running | 1400 | 1377 | 23 | 2914 MB | +61.8 MB | 0.29 h |
| `p0_insurance_llamaindex` | completed | 200 | 198 | 2 | 951 MB | — | 0.02 h |
| `p0_insurance_rr_rocketride` | completed | 200 | 198 | 2 | 3034 MB | — | 0.04 h |
| `p2_llamaindex_llamaindex` | completed | 10000 | 9898 | 102 | 1250 MB | +14.8 MB | 1.12 h |
| `p3_rocketride_rocketride` | goodput_failure | 267 | 265 | 2 | 2236 MB | — | 0.06 h |
| `p4_sim_llamaindex` | cap_reached | 8888 | 8794 | 94 | 1255 MB | +20.4 MB | 1.00 h |
| `p4_sim_rocketride` | goodput_failure | 267 | 265 | 2 | 2348 MB | — | 0.06 h |

## Fault classes

* `endurance_rocketride`: empty_extraction=17, goodput:1 empty chunk(s) at [0]=2, goodput:1 empty chunk(s) at [1]=1, goodput:2 empty chunk(s) at [0, 1]=1, goodput:2 empty chunk(s) at [0, 7]=1, parse:PdfReadError=1
* `p0_insurance_llamaindex`: empty_extraction=2
* `p0_insurance_rr_rocketride`: empty_extraction=2
* `p2_llamaindex_llamaindex`: empty_extraction=94, parse:LimitReachedError=1, parse:PdfReadError=7
* `p3_rocketride_rocketride`: empty_extraction=2
* `p4_sim_llamaindex`: empty_extraction=87, parse:LimitReachedError=1, parse:PdfReadError=6
* `p4_sim_rocketride`: empty_extraction=2
