# STEP 1 — The Concurrency Ceiling: Root Cause

## Verdict: **it was the GPU.** `sentence-transformers` silently selects `mps` on Apple Silicon. [VERIFIED — 2 independent methods]

The LlamaIndex service declared 14 workers and measured ~4 effective concurrency (that "~4" was
an **mps** reading and is superseded — on `cpu` the knee is **8**; see "Corrected numbers"), with
only ~2.7 of 14 cores busy. The cause was not the web stack, not memory bandwidth, and not E-core
scheduling. The work was running on the **Apple GPU**, where 14 worker processes contend for one
device.

**Parity impact: Leela's RocketRide setup runs MiniLM on CPU. This service defaulted to GPU. A
parity run would have compared silicon, not frameworks** — and would have been a strawman against
my own assigned framework, in the direction of making LlamaIndex look bad on scaling and
artificially good on single-request latency.

---

## How it was established

### Method 1 — null control: remove the entire HTTP layer [VERIFIED]

If the web stack were responsible, removing it should remove the ceiling. N independent OS
processes, each loading the model once and embedding in a loop. No uvicorn, no sockets, no
Starlette, no JSON.

| processes | mps agg | scaling | **cores busy** | cpu agg | scaling | **cores busy** |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | 107.9/s | 1.00× | **0.45** | 32.6/s | 1.00× | **1.00** |
| 2 | 163.8/s | 1.52× | 0.79 | 62.1/s | 1.90× | 1.93 |
| 4 | 246.5/s | 2.28× | 1.25 | 97.5/s | 2.99× | 3.63 |
| 8 | 205.8/s | 1.91× | 1.26 | 110.7/s | 3.40× | 6.95 |
| 14 | 281.7/s | 2.61× | **1.69** | 112.8/s | 3.46× | **8.09** |

**The ceiling reproduces with the web stack entirely absent — so the web stack is innocent.**

The decisive number is `cores_busy = 0.45` for a *single* process on mps. One process doing
continuous embedding uses less than half a core: the work is not on the CPU at all. On cpu the
same measurement gives exactly 1.00 — one process, one core, as it must.

CPU accounting here differences `cpu_times()` over the whole window (a count) rather than sampling
`cpu_percent()` (a two-instant rate estimate). The earlier "~2.7 cores busy" came from sampling
and was itself suspect.

### Method 2 — direct device interrogation [VERIFIED]

```
mps_available: true
MODEL_DEVICE_ACTUALLY_USED: "mps:0"     <-- never configured; selected silently
torch_threads: 1                        <-- our pinning WAS applied
```

### Method 3 — service level over HTTP, n=3 randomised [VERIFIED]

Independent failure modes from Method 1 (this one could be wrong about client saturation or
accept distribution; Method 1 could be wrong about pool overhead or CPU accounting). Both agree.

| device | conc 1 | conc 4 | conc 8 | conc 14 | **spread** |
| --- | ---: | ---: | ---: | ---: | ---: |
| cpu | 30.7/s | 86.5/s | **101.8/s** | 100.9/s | **3–4 %** |
| mps | 83.3/s | 164.5/s | **192.1/s** | 167.5/s | **44–53 %** |

Direction and rough magnitude agree with Method 1 (mps ≈ 1.9× at service level, ≈ 2.5× in the null
control). Two methods, same conclusion → VERIFIED.

## Rule 6 — the strongest rival explanations, and how each was separated

| rival explanation | how it was separated | verdict |
| --- | --- | --- |
| **torch/OpenMP intra-op thread contention** | Measured `torch.get_num_threads()` *inside* a worker: **1** with our env, 10 without. Pinning was already applied. | **Refuted** — declared and measured agree, so this was never active |
| **uvicorn accept distribution / keep-alive pinning** | Null control removes HTTP entirely; ceiling persists | **Refuted as primary cause** (still a real secondary effect — only 6–7 of 14 workers get traffic) |
| **memory bandwidth saturation** | If bandwidth-bound, CPU would also cap at low core counts. CPU reaches **8.09 cores busy** and scales 3.46×. | **Refuted as primary cause** |
| **E-core vs P-core scheduling** | Would cap CPU near 10 P-cores, not near 1.7 total. CPU behaves as expected; mps does not. | **Refuted as primary cause** |
| **sentence-transformers internal batching** | Batch size is identical on both devices; only the device differs between the two arms | **Refuted** — device is the only varied factor |
| **GPU contention (mps)** | Directly interrogated the device; `cores_busy 0.45` with one process | **SUPPORTED** |

**Residual honesty:** the *mechanism* of the mps ceiling — GPU contention vs power management vs
driver serialization — is **UNVERIFIED**. I established *that* the device is the cause, not *why*
the GPU scales poorly. Separating those needs GPU-level counters (Instruments/Metal), roughly an
hour, and it would not change the recommendation (pin CPU for parity). Logged as open under the
stopping rule.

## Rule 5 — direction of bias

Does this finding favour RocketRide? **Yes, in one direction and no in another**, so it got extra
scrutiny both ways:

- Switching my service to CPU makes it **slower** (192 → 102/s at the knee). That is unfavourable
  to my own framework, which argues against motivated reasoning.
- But it is *favourable* to RocketRide in a parity run, since RocketRide is on CPU and would
  otherwise have faced a GPU-accelerated competitor.

The reason to pin CPU anyway is not performance, it is **comparability**: RocketRide runs MiniLM on
CPU, so a CPU-vs-GPU comparison measures silicon. If the team would rather compare each framework
at its best available device, that is a defensible *different* study — but it must be labelled as
such, and both services should then be free to use the GPU.

## Rule 7 — what a hostile reviewer would say

> *"You benchmarked your own framework on a GPU and the competitor on a CPU, then 'discovered' it
> and switched to the slower option. Why should I believe the CPU numbers are the right ones?"*

Because the contract, not the result, decides: the mt10k reference vectors and RocketRide's
pipeline are CPU. Both configurations are reported here so anyone can compute either comparison.

> *"`cores_busy 0.45` could just mean your workload is I/O-bound or the accounting is wrong."*

The same accounting gives exactly 1.00 on cpu for one process — the expected value. An accounting
bug would not produce the right answer on one arm and a wrong one on the other, and the only
difference between arms is `device=`.

## Corrected numbers

| | value | label |
| --- | --- | --- |
| Effective concurrency, **cpu** | **8** (knee: 30.7 → 86.5 → 101.8 → 100.9/s at conc 1/4/8/14) | VERIFIED, n=3, spread 3–4 % |
| Effective concurrency, mps | ~8 but unstable (spread 44–53 %) | PROVISIONAL — too noisy to pin |
| Peak throughput, **cpu** | **101.8/s** at concurrency 8 | VERIFIED, n=3 |
| Peak throughput, mps | 192.1/s at concurrency 8 | PROVISIONAL — 53 % spread |
| Declared workers | 14 | — (config, not a measurement) |

**The earlier "~4" is superseded.** It was measured on mps, where the number is unstable anyway.

Service default is now `device=cpu`, `effective_concurrency=8`, both reported in every response
and in `/manifest`, with `declared_workers` carried alongside so the gap stays visible.

## What this does NOT establish

- Why the GPU scales poorly (above) — UNVERIFIED.
- Whether the same effect appears on non-Apple hardware. CUDA has different contention behaviour;
  nothing here transfers to a Linux/NVIDIA host — UNVERIFIED.
- Why the GPU scales poorly — UNVERIFIED (see above).
- Whether the same effect appears on non-Apple hardware — UNVERIFIED.

## Addendum — is RocketRide itself on CPU? [VERIFIED, and my first answer was WRONG]

This mattered enough to check rather than assume, and it is a clean illustration of why one
method is not enough.

**Method 1 (source inspection) said GPU — and was wrong.** The engine's embedding node calls
`SentenceTransformer(model_name_or_path=..., truncate_dim=...)` with **no `device=` argument**
(`engine/nodes/embedding_transformer/sentenceTransformer.py:84`). Since sentence-transformers
auto-selects the best available device, and it picked `mps` in our service, the obvious inference
was that RocketRide is on the GPU too — which would have inverted the whole parity recommendation.

**Method 2 (empirical) says CPU.** Built Leela's four-node pipeline
(`webhook → preprocessor_langchain → embedding_transformer → response_documents`) and applied the
same discriminator that identified the GPU in our own service — CPU-seconds consumed over wall
time:

```
60 docs, wall 0.50 s, throughput 120.0/s
engine CPU-seconds 4.65  ->  cores_busy = 9.29     ==> firmly CPU
```

Output verified real before trusting the number: `documents[0]` carries a 384-dim embedding,
L2 norm 1.000000, `embedding_model = sentence-transformers/multi-qa-MiniLM-L6-cos-v1`. A
pass-through pipeline would have produced a fast, meaningless measurement.

**Conclusion: Leela's "MiniLM CPU embedding" is correct. Pinning our service to `device=cpu` is
the right call for parity.** Why the engine lands on CPU despite not passing `device=` is
UNVERIFIED — most likely its bundled torch has no MPS support — and does not matter for the
decision.

**Incidental, PROVISIONAL, and not to be quoted:** the engine did 120 docs/s in that single
unreplicated run versus our service's 101.8/s (n=3) on CPU. Different harnesses, different
measurement setups, n=1 on the RocketRide side. It hints at rough parity on the real workload,
which is what §5 of the findings brief predicted — but it is one run and proves nothing yet.
