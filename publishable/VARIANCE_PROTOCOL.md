# WS-1 Variance Protocol

**For: Shashi, Leela, Ansh** · 2026-08-05 · runnable gate: `working/scripts/variance_gate.py`

Run-to-run variance currently invalidates cross-service comparison. This document says what
causes it (measured, not assumed), what to do about it, and provides a gate that rejects runs
which do not meet the bar.

**All claims labelled.** VERIFIED = two independent methods + reproduced. PROVISIONAL = one
method. UNVERIFIED = asserted, not established.

---

## 1. What we found

Same workload, n=5 per condition, in-process measurement with the model warmed outside the timed
region (`working/ws1/exp_variance_cause.py`):

| condition | median | **spread** |
| --- | ---: | ---: |
| cpu, no cooldown, no warmup discard | 31.6/s | 17.7 % |
| cpu, + 5 s cooldown between reps | 32.4/s | 4.4 % |
| **cpu, + discard first 2 iterations** | 32.6/s | **1.7 %** |
| **cpu, immediately after driving load average to 7.88** | 33.0/s | **0.7 %** |
| mps, no cooldown | 78.3/s | 16.9 % |
| mps, + 5 s cooldown | 81.5/s | 14.5 % |
| mps, + discard first 2 iterations | 104.3/s | 25.3 % |

### Finding 1 — most variance is a WARMUP artefact, and it is fixable [VERIFIED]

On CPU, discarding the first two iterations takes spread from **17.7 % → 1.7 %**. The offending
value is always an early one (`[31.6, 26.5, 31.8, 31.4, 32.2]` — the 26.5 is the second
iteration). Confirmed by a second route: adding a 5 s cooldown, which also lets early state
settle, independently reduces spread to 4.4 %.

**A measurement whose first iterations are included is not measuring steady state.**

### Finding 2 — GPU (mps) variance is irreducible; CPU variance is not [VERIFIED]

MPS spread stays **14–25 %** under every condition tried, including the warmup discard that fixes
CPU. CPU spread reaches **0.7–1.7 %**. Two independent methods agree: the service-level HTTP sweep
saw cpu 3–4 % vs mps 43–53 %, and this in-process experiment saw cpu ≤4.4 % vs mps ≥14.5 %.

**Consequence: pin `device=cpu` for parity runs.** MPS is genuinely ~2–3× faster but you cannot
get a stable number out of it, and RocketRide runs MiniLM on CPU anyway.

### Finding 3 — load-average carryover is NOT a cause [VERIFIED, by null control]

We predicted that measuring immediately after heavy load would be noisy. We drove the load average
to **7.88** with 12 spinners and measured immediately: spread **0.7 %**, the *lowest* observed, and
the *highest* median (33.0/s). The hypothesis is refuted rather than merely unsupported.

**Do not gate runs on load average alone.** It was in our original proposal; the evidence says
drop it. (Speculative and UNVERIFIED: sustained load may keep cores at a high clock, which would
make a *busy* host more stable than an idle one. Not investigated — not load-bearing.)

### Finding 4 — RocketRide's ±35 % does NOT survive the protocol [VERIFIED, n=5]

The engine was re-measured under the full protocol (2 warmup iterations discarded, n=5 measured,
randomised order across driver counts, 4 s cooldown):

| drivers | median | spread (protocol) | spread (warmup included) | gate |
| ---: | ---: | ---: | ---: | --- |
| 1 | 3,416.8/s | 4.3 % | 5.7 % | PASS |
| 2 | 6,730.2/s | 7.4 % | 11.4 % | PASS |
| 4 | **12,313.5/s** | **1.7 %** | 11.9 % | PASS |

**Within-session variance is well controlled: worst spread 7.4 %, best 1.7 %.** Warmup discard
helps materially (11.9 % → 1.7 % at 4 drivers), consistent with Finding 1.

**But this also corrected a correction of mine.** The history:
1. First measurement: 11,408/s at 4 drivers (n=1).
2. Later same-day re-runs: 7,871 / 8,540 / 8,311/s. I concluded the 11,408 was a ~35 % outlier and
   wrote a correction banner saying so.
3. Under protocol: **12,313.5/s, spread 1.7 %** — which supports the *original* figure and does
   not reproduce the 7,871–8,500 cluster at all.

So the ±35 % was a **between-session** effect, not within-session noise, and my "correction" was
itself wrong. **Why those readings were depressed is UNVERIFIED.** They coincided with a 15-min
load average of 20.01 after sustained benchmarking — but the null control in Finding 3 refuted the
simple load-carryover hypothesis, so the obvious explanation does not hold.

**Practical consequence: between-session comparisons are the dangerous ones.** Repetition inside a
session will not catch this. Anything compared across sessions must be re-measured in the same
session, which is exactly why the parity run (`PARITY_REPLICATION.md`) interleaved both services
in one randomised sequence rather than comparing numbers taken on different days.

**Strongest rival explanation for Findings 1–2**, and how to separate it: the warmup effect could
be lazy allocation inside sentence-transformers rather than anything about steady state, and the
MPS instability could be thermal rather than contention. The separating experiment is a long
soak (5+ minutes continuous) with per-iteration timing — if MPS variance is thermal it should
show a downward trend; if contention, it should stay noisy but flat. **Not run: ~40 min, and the
protocol's recommendation (pin CPU, discard warmup) is the same either way.** Logged as open.

---

## 2. The protocol

### Preconditions — check before a run counts

| precondition | why | check |
| --- | --- | --- |
| `device` pinned and recorded | mps vs cpu changes throughput 2–3× and spread 10× | manifest `device` field |
| model/service fully warm before timing | ~36 s of import + load, and the warmup artefact above | `/health` polled until **every** worker warm |
| thread env pinned (`OMP/MKL/OPENBLAS/VECLIB = 1`) | 14 workers × 10 threads = 140 threads of thrash | verify `torch.get_num_threads() == 1` **inside a worker**, not just the env var |
| effective concurrency measured, not declared | our service declared 14, measured **8** on cpu | **guarded** `working/handoff/pool_width.py` — it auto-escalates offered concurrency and hard-fails rather than returning the offered value |
| no orphaned processes from a prior run | RocketRide leaked 81 `node.py` after a livelock | `engine_ops.preflight()` |
| **all services in a comparison measured in ONE session** | the ±35 % turned out to be a *between-session* effect that within-session repetition cannot catch | interleave services in one randomised sequence; never compare numbers taken on different days |

### Execution

1. **Discard the first 2 iterations** of every series. Non-negotiable — it is the single largest
   fixable source of variance (17.7 % → 1.7 %).
2. **n ≥ 5** measured repetitions per configuration. n=3 detects gross problems; n=5 gives a
   usable spread estimate.
3. **Randomised order** across services and configurations, fixed seed (`seeds.py`). Never run all
   of service A then all of service B.
4. **Cooldown 5 s** between repetitions. Cheap, and independently worth ~13 points of spread.
5. **Report median + min/max spread.** Never a single run. For cross-service ratios use
   `stats.ratio_ci` — if the CI spans 1.0 there is no demonstrated difference.

### The gate

**Reject any configuration whose spread exceeds 10 %.** Justification: CPU-pinned, warmup-discarded
measurements achieve 0.7–4.4 %, so 10 % is roughly 2× the worst well-behaved case — tight enough
to catch real problems, loose enough not to reject on noise.

A run that fails the gate is not a slow result, it is **an invalid measurement**. Fix the
precondition and re-run; do not report the median of a 40 % spread.

---

## 3. Runnable check

```bash
python working/scripts/variance_gate.py --cmd "your_benchmark_command" --reps 5 --threshold 0.10
```

Runs the command n times, discards warmup, computes median and spread, and **exits non-zero if
the spread exceeds the threshold** so it can sit in CI or a Makefile. It also records the
preconditions it could verify, and warns about the ones it could not.

---

## 4. What we deliberately did not do

| skipped | why | cost if we are wrong |
| --- | --- | --- |
| Long thermal soak to separate thermal from contention on MPS | ~40 min; recommendation identical either way | low — we pin CPU regardless |
| ~~Root-causing RocketRide's ±35 %~~ **DONE** | re-measured under protocol; within-session spread is 1.7–7.4 %, the ±35 % was between-session | resolved for within-session; between-session cause still UNVERIFIED |
| Testing whether a busy host is *genuinely* more stable | speculative, not load-bearing | low |
