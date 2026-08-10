# Re-Baseline Plan — every existing number is invalidated by containerisation

**Design for review. Nothing re-measured yet.** Ansh · 2026-08-06.

---

## 0. The premise

Moving into a Linux VM changes the CPU scheduler, the network stack, the filesystem, the memory
ceiling, and the visible core count. **No native number survives the move.** Rather than re-run
everything, we re-measure a small set of anchors whose native values are well characterised, and
use the deltas to establish whether the container environment is *symmetric* — which is the only
property that makes any subsequent comparison valid.

**Between-session drift is an open, unexplained problem (item F).** Every native-versus-container
pair below must therefore be measured **in one session, interleaved**, not on different days.
Native-then-container-tomorrow would confound the container tax with the drift we already cannot
account for.

## 1. The three anchors

Chosen because each has a different failure mode, so a container problem that hides in one shows up
in another.

### Anchor A — the concurrency curve (both arms)

**Native reference:** RocketRide flat 2→32 at default threads (56–65 /s @400 tok); LlamaIndex
scales to a plateau by concurrency 8 (~93 /s @400 tok). `working/results/concurrency_barrier.json`.

**Why this one:** it is the shape the whole WS-1 comparison now rests on, and it is a *shape*
rather than a point, so it is robust to a uniform slowdown. If containers cost both arms 20 %, the
shape is unchanged and the anchor still validates.

**Re-measured as:** identical barrier-synchronised harness, driver in its own container, concurrency
{1,2,4,8,16,32} × {400, 1600} tokens, randomised order, n≥5, warmup discarded, 10 % gate reported
per cell.

**Container-specific risk:** the driver container's CPU quota becomes the limit at high
concurrency. Detected by re-running the top concurrency cell with the driver's quota doubled — if
throughput moves, the driver was the bottleneck and those cells are void.

### Anchor B — the 1.190× at 1,600 tokens / concurrency 2

**Native reference:** RocketRide ahead 1.190× [CI 1.184–1.196], both arms passing the 10 % gate
(spreads 1.6 % / 0.5 %). The only gate-passing head-to-head advantage in the project.

**Why this one:** it is a *point estimate with a tight CI*, so it is the most fragile thing we have
and the most sensitive detector of asymmetry. A container tax that lands unevenly will move this
number before it visibly distorts anchor A.

**Re-measured as:** exactly the native protocol, same document, same concurrency, n≥5, both arms
interleaved in one session.

**Pass condition:** the ratio's CI overlaps the native CI, **or** the divergence is fully explained
by a symmetric tax (§3). If the ratio moves and the tax is symmetric, that is a real finding about
containers, not an instrument failure — but it must be labelled as such.

### Anchor C — effective pool width (RocketRide ~17, LlamaIndex 8)

**Native reference:** findings 8 and 9, both VERIFIED by two methods.

**Why this one:** width is a *structural* property. Under a 4.0-CPU quota it should change in a
**predictable** direction for the service whose parallelism comes from worker processes
(LlamaIndex, 8 workers) and it tells us directly whether the cgroup quota is actually being
enforced. If width comes back at its native value, the quota is not applying and every other number
in the run is untrustworthy.

**Re-measured as:** the guarded `working/handoff/pool_width.py` instrument (finding 17: accurate to ~1 %
when guarded), both arms.

## 2. The container tax metric

For each arm independently:

```
container_tax(arm, cell) = 1 − ( throughput_container / throughput_native )
```

measured on **matched cells** in one interleaved session. Reported per arm, per cell, with CI.

Decomposed, because a single number hides where it comes from:

| component | isolated by |
| --- | --- |
| **network / bridge tax** | driver+service in one container vs across the bridge (`DOCKER_ARCHITECTURE.md` §5) |
| **CPU quota tax** | same container config with quota raised to the host core count |
| **VM tax** | the remainder — native host vs in-VM with quotas removed |

The null-work path (`probe_minimal`, and a `/ping` on the LlamaIndex service) is the cleanest place
to measure the network component, because it has almost no compute to hide behind: natively it runs
at ~1,690 req/s, so per-request overhead is directly visible there and invisible at 60 req/s.

## 3. Symmetry — the condition that makes the comparison valid

**Both arms must pay the tax within tolerance, or the container comparison is void.**

```
asymmetry = | container_tax(rocketride) − container_tax(llamaindex) |
```

| asymmetry | verdict |
| --- | --- |
| **≤ 5 pp** | symmetric — container results are comparable; report the tax as context |
| 5–15 pp | **investigate before reporting anything** — §4 |
| > 15 pp | **void** — do not report any container comparison until explained |

The threshold is deliberately tight because the effects we are chasing (a 1.19× ratio) are smaller
than the asymmetries a container misconfiguration can produce.

## 4. How we detect asymmetry — four specific traps

Asymmetry will not announce itself; each of these produces a plausible-looking number.

1. **Thread-count inference.** `os.cpu_count()` reports the **host's** 14 inside a 4.0-CPU quota,
   so BLAS/torch spawn 14 threads into 4 cores. Per the A3 finding this alone costs ~19 % of
   throughput and most of the scaling. Our LlamaIndex image already pins threads; if the RocketRide
   image does not, the container run reproduces the *tuned-versus-untuned* asymmetry that has
   already distorted this project. **Both images pin explicitly; the manifest records the value and
   `/sys/fs/cgroup/cpu.max` beside it.**
2. **Different network paths.** One arm on the bridge and one on published ports pays a different
   tax. Detected by the per-arm null-work measurement in §2 — the two arms' network components must
   match.
3. **Model load inside the measured window.** The engine takes ~60 s to start and the model ~36 s
   to load; in a container a cold start can land inside the first window. Detected by requiring a
   readiness gate before measurement (LlamaIndex: count `warm in` lines, not `/health`, which one
   worker answers) and by discarding warmup.
4. **Unequal memory pressure.** If one arm's working set fits in 8 GB and the other's does not, one
   arm swaps. Prevented by `memory-swap = memory` (swap disabled ⇒ OOM instead of silent
   slowdown) and detected by recording peak RSS per container.

**Null control for the whole exercise (rule 3):** run the *same image against itself* — the
LlamaIndex container measured by the driver twice under identical settings. Predicted difference:
zero. Any systematic gap is instrument, and the run stops until it is fixed.

## 5. What gets re-measured, in order

| # | step | gate before proceeding |
| --- | --- | --- |
| 1 | VM allocation verified via `docker info` (≥24 GiB, ≥10 CPUs) | must pass or nothing else runs |
| 2 | arch assertion on all three images (`aarch64`, no Rosetta) | must pass |
| 3 | cgroup quota observed from inside each container | quota must match the declared contract |
| 4 | null control (same image twice) | difference ≈ 0 |
| 5 | network/bridge tax, both arms, null-work path | per-arm components must match |
| 6 | **Anchor C** (pool width) | quota demonstrably enforced |
| 7 | **Anchor A** (concurrency curve) | shape preserved; driver-not-bottleneck check passes |
| 8 | **Anchor B** (the 1.190×) | symmetry ≤ 5 pp |
| 9 | publish container tax + re-baselined anchors | — |

## 6. What this plan explicitly does not do

| not doing | why |
| --- | --- |
| Re-measuring all 17 findings | most are structural (device selection, fault isolation, corpus shape) and unaffected by the environment; the three anchors test the environment itself |
| Comparing container numbers to native numbers as results | the container tax makes them different measurements; only *shape* and *ratio* cross the boundary |
| Treating any container number as production performance | `DOCKER_ARCHITECTURE.md` §0 — Linux VM under virtualisation. A native Linux run is still required |
| Re-running the withdrawn sustained curve | it is invalid for reasons unrelated to environment |

**Estimated cost:** ~2.5 h once images exist, dominated by anchors A and B at n≥5.
