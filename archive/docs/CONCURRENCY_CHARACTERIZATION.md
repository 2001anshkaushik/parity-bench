# Concurrency, Document Weight, and What Actually Bounds Each Service

**INTERNAL WORKING NOTES — not a team deliverable, not for sending.** Written 2026-08-05 (session 6)
after the 31 % sustained decay was withdrawn. Audience: engineers deciding what to build.
No ranking, no winner. Mechanism, conditions where it holds, conditions where it does not.

---

> ## ⚠️ CORRECTION 2026-08-06 (session 7) — THE FLATNESS IS CONDITIONAL, AND IT IS NOT THE ENGINE
>
> "RocketRide is flat in offered concurrency" holds **only at default thread settings**, and the
> cause is **not** the engine. A four-arm ladder shows the engine's request path scales **3.69×**,
> Python-node dispatch costs ~3 %, and pure-Python CPU inside a node scales **3.59×**. Only the
> embedding arm is flat (1.46×).
>
> Cause [VERIFIED, 2 methods]: the engine does not constrain native BLAS/torch thread pools for
> node code. One embedding request occupies **1.45 cores**; under concurrency those threads
> oversubscribe and per-request CPU cost inflates **80 %**. Pinning the thread-limit env vars to 1
> at engine start gives **3.19× scaling and +19 % throughput at concurrency 8** (73.3 → 87.6 /s),
> at the cost of ~1.8× worse single-request latency. A pure-Python null control was unmoved (2 %).
>
> **Consequence for every prior comparison:** our LlamaIndex service already pins
> `OMP_NUM_THREADS=1`, so all previous RocketRide-vs-LlamaIndex throughput numbers were
> **tuned service versus untuned engine**. That is a configuration difference, not a framework one.
>
> Full detail and product implications: `A3_SERIALIZATION_FINDING.md`.


## 0. What was withdrawn, and why this document exists

The previous framing — *burst capacity vs sustained throughput, with RocketRide decaying 31 % under
sustained load* — **does not survive replication.** Details in §1. Removing it also removes the only
reason we had for preferring one harness's direction over the other's, so the token curve derived
from it is invalid too.

What replaced the question: if the two harnesses disagreed by 1.5–1.8× on the same nominal
workload, **what configuration variable were they actually varying?** The answer is concurrency,
and the two services respond to it in completely different ways.

## 1. The decay is not real [VERIFIED — 2 methods, both with a control arm]

`burst_vs_sustained.py` measured RocketRide only, once, with no control, and swallowed exceptions
without recording them. Four rival explanations were separated by experiment.

| experiment | design | result |
| --- | --- | --- |
| exact replication, instrumented | 1 proc / 1 conn / 1 task, no cooldown, 20 bursts | decay **6.0 %**, not 31.3 % |
| failure accounting | ok/fail recorded per burst, all phases | **0 failures in ~10,000 requests** |
| engine-tree RSS | sampled between bursts | **flat at ~891 MB** from burst 5 on |
| recovery after 60 s idle | same task, same connection | returns to **98 %** of opening rate |
| fresh task per burst | task recreated each burst, connection reused | **0.0 %** decay — same as persistent |
| **interleaved RR/LI** | alternating bursts, one shared host timeline | **RR +1.1 %, LI −0.8 %** — neither decays |
| **symmetric continuous, n=3** | both arms, 20-burst sequences, randomised order | **RR median +1.5 %, LI median +1.0 %** |

Per-sequence decay values, which is the point:

```
RocketRide   +5.2 %   −8.7 %   +1.5 %      median +1.5 %   spread 13.9 pp
LlamaIndex   +6.4 %  −12.0 %   +1.0 %      median +1.0 %   spread 18.4 pp
```

**Both arms swing in both directions by up to 12 pp.** The decay statistic's own noise band is
±12–18 pp, so a single 31.3 % reading is one unreplicated draw from a very noisy estimator. The
null control (decay vs position in session) shows no trend, so session drift is not it either.

**All four rivals are moot** — funnelling, pipeline accumulation, and thermal were candidate
explanations for a phenomenon that does not exist. Each was nevertheless refuted on its own terms:
thermal by the interleaved control (both arms flat on a shared timeline), accumulation by flat RSS
plus full recovery plus fresh-task equivalence, silent failure by direct accounting.

## 2. The mechanism that does hold: the two services are bounded by different things

Concurrency swept 2 → 32 in flight, spread across up to 4 driver processes on **both** arms
identically, 400 and 1,600 tokens/doc, randomised cell order.

**RocketRide's throughput is flat in offered concurrency. LlamaIndex's rises, then plateaus.**

Authoritative numbers are from the **barrier-synchronised** harness (`results/concurrency_barrier.json`);
the per-rep harness (`results/concurrency_parity.json`) agrees on shape but fails the variance gate
almost everywhere.

**400 tokens/doc**

| offered concurrency | 2 | 4 | 8 | 16 | 32 |
| --- | ---: | ---: | ---: | ---: | ---: |
| RocketRide | 55.8 | 60.7 ✅ | 57.9 ✅ | 64.9 | 62.2 ✅ |
| LlamaIndex | 62.0 ✅ | 76.7 ✅ | 92.9 ✅ | 94.6 | 91.1 |
| ratio RR/LI | 0.841 | 0.800 | 0.633 | 0.689 | 0.687 |

**1,600 tokens/doc**

| offered concurrency | 2 | 4 | 8 | 16 | 32 |
| --- | ---: | ---: | ---: | ---: | ---: |
| RocketRide | 28.5 ✅ | 27.7 ✅ | 24.3 ✅ | 29.4 ✅ | 28.5 ✅ |
| LlamaIndex | 23.9 ✅ | 31.4 | 37.2 ✅ | 36.9 ✅ | 37.2 ✅ |
| ratio RR/LI | **1.190** | 0.893 | 0.657 | 0.773 | 0.761 |

✅ = that cell passes the 10 % variance gate. **6 of 10 concurrency points pass on both arms** —
the first time the RocketRide arm has passed at all.

**RocketRide is flat: 56–65 /s at 400 tokens and 24–29 /s at 1,600, across a 16× range of offered
concurrency.** LlamaIndex rises to a plateau (~93 /s and ~37 /s respectively) by concurrency 8.

**Condition where RocketRide is ahead, cleanly measured:** heavy documents at low concurrency.
At 1,600 tokens and concurrency 2 the ratio is **1.190, CI [1.184, 1.196], and both arms pass the
gate** (spreads 1.6 % and 0.5 %). This is the only gate-passing head-to-head advantage for either
service in the whole study, and it belongs to RocketRide.

**Condition where LlamaIndex is ahead:** concurrency ≥ 4, at both document weights, by 12–58 %.
The gap comes almost entirely from LlamaIndex scaling rather than RocketRide slowing.

**The crossover is on the concurrency axis, and document weight moves it.** At 400 tokens
RocketRide is already behind at concurrency 2 (0.841); at 1,600 tokens it is ahead there (1.190).
Heavier documents push the crossing point to higher concurrency.

**Mechanism [PROVISIONAL — one method]:** something in the engine's request path serialises this
workload. Adding client concurrency, adding client processes, adding connections, and adding tasks
all fail to raise its ceiling. Note this refutes a hypothesis we held earlier the same day — that
the 8-in-flight sweeps had *under-driven* RocketRide relative to its measured ~17 effective pool
width. They had not: the engine does not go faster at 16 or 32 either. **Effective pool width and
throughput scaling are not the same property**, and the width measurement does not predict this.

**What would separate the remaining candidates** (a lock in the DAP/WebSocket request path, a
single dispatch thread, or per-task serialisation inside the node process): run the same sweep
against a pipeline whose node does no embedding at all. If the flat ceiling persists on trivial
work, it is the request path; if it scales, the serialisation is in the node. **~45 min, not run.**

## 3. Instrument failures found this session

All four were in our own harnesses, and three of them were introduced *while investigating the
other two*. This is the fifth consecutive session where the instrument was wrong more often than
the system under test.

| defect | effect | status |
| --- | --- | --- |
| `burst_vs_sustained.py`: n=1, no control arm, `except: return None` with failures never recorded | produced the 31 % artifact that reframed the whole project | root cause of this session |
| `decay_rootcause.py` PHASE 5: summed per-burst-index rates across driver processes | drivers desynchronise → fake U-shaped curve (140 → 40 → 87 /s) reported as "+31.5 % decay" | caught, not reported as a finding |
| `concurrency_parity.py` v1: wall-clock-union aggregation | union window spans time an early-finishing driver has already left → every cell depressed, all gates failed | caught within one run, fixed |
| `concurrency_parity.py` v2: per-rep burst boundaries | desync → each driver measures itself during others' idle gaps → 12–58 % spreads | fixed by barrier-synchronised fixed-duration windows |

**Generalisable rule for this project:** any multi-process aggregate needs all drivers loading the
system over the *same* wall-clock window, enforced by a barrier, with no per-burst boundaries
inside it. Both alternatives we tried are biased, in opposite directions.

## 4. Variance status — the noise was the harness, not the engine

| harness | RocketRide spreads | LlamaIndex spreads | RR cells passing |
| --- | --- | --- | --- |
| per-rep bursts, 2 drivers (earlier sessions) | 17.9–28.3 % | 3.9–22.7 % | 0 |
| per-rep bursts, up to 4 drivers | 11.8–57.6 % | 1.0–28.1 % | 0/15 |
| **barrier-synchronised windows** | **1.2–43.0 %** | 0.5–16.7 % | **8/10** |

**The variance was the harness, not the engine.** Under barrier-synchronised fixed-duration windows
the RocketRide arm passes the 10 % gate in 8 of 10 cells — including 5/5 at 1,600 tokens with
spreads of 1.2–9.8 %. Every earlier harness attributed its own desynchronisation noise to the
engine, which is why "the RocketRide arm is systematically noisier" was reported in three previous
sessions. **That claim is withdrawn**: it was an artifact of per-burst boundaries across
unsynchronised driver processes.

The one cell that still fails badly (400 tokens, concurrency 2, 43.0 %) uses only 2 driver
processes and the shortest windows, so it has the least averaging — consistent with the same
mechanism rather than with engine instability.

## 5. What holds, what does not

| statement | label |
| --- | --- |
| The 31 % sustained decay does not reproduce | **VERIFIED** (2 methods, both with control arms) |
| Neither service decays under sustained load (RR +1.5 %, LI +1.0 % median, n=3) | **VERIFIED** |
| Both services complete 100 % of requests under all loads tested | **VERIFIED** (0 failures, ~10,000 requests) |
| RocketRide's throughput is flat in offered concurrency 2→32 | **VERIFIED** (2 harnesses with opposite aggregation biases agree on the shape; 5/5 RR cells pass the gate at 1,600 tokens) |
| LlamaIndex converts concurrency into throughput up to a plateau at ~8 | **VERIFIED** (2 harnesses) |
| RocketRide ahead 1.190× at 1,600 tokens / concurrency 2 | **PROVISIONAL** (1 harness, but both arms pass the gate; CI excludes 1.0) |
| At 400 tokens LlamaIndex is ahead at every concurrency tested | **PROVISIONAL** (1 harness) |
| Cause of RocketRide's flat concurrency response | **UNVERIFIED** — separating experiment in §2, ~45 min |
| Everything derived from the burst/sustained distinction | **WITHDRAWN** |

## 6. Hostile reviewer

> *"You presented a 31 % decay as VERIFIED yesterday and withdraw it today. Why trust this?"*

Because this time both arms were measured, n=3 with randomised order, failures were counted, and a
null control was run — none of which was true of the original. The original was n=1 with no control
arm. The correct conclusion is that it should never have carried a VERIFIED label with n=1.

> *"Three of your four instrument bugs appeared during this investigation. How is the new number
> better?"*

The load-bearing claim is a shape (flat vs rising) that survived two aggregation schemes with
**opposite** biases — the union estimator depresses cells, the per-driver sum inflates them, and
both show the same shape. The one point estimate quoted (1.190× at 1,600 tokens / concurrency 2)
is the only head-to-head in this project where both arms passed the variance gate simultaneously.

> *"Does any of this change which service to use?"*

Not on this evidence. At concurrency ≈ 2 they are indistinguishable; above that they differ in how
they respond to load, and the RocketRide numbers are not yet precise enough to quote. The decision
should rest on the axes that were never in dispute — fault isolation, memory, operational
complexity — until the flat-concurrency mechanism in §2 is understood.
