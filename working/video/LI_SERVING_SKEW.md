# LI serving-layer skew — pre-publication review (2026-08-25, box stopped, no code changed)

## The correction that comes first
`stage_s.detect` **includes lock-wait time**: the stamp starts BEFORE
`with self._lock:` (pipeline.py:186-187; embed likewise :206-207). Therefore
my earlier claim — "`sum(stage_s.detect)/span = 8.00` proves exactly one
inference per worker, eight concurrent" — **is wrong.** 8.00 counts
requests whose detect CLOCK was running, including requests parked at a hot
worker's lock (≈ C × detect share = 16 × 0.542 ≈ 8.7 ≈ 8.0). The measured
per-worker occupancies >1.0 (4.84, 1.78) are the proof: a worker cannot
execute 4.84 s of detect per second of its own span — it can only have ~5
detect clocks ticking while queued. A stage clock that includes queue wait
measures the QUEUE, not the device. ARM_CONCURRENCY_CONFIG.md corrected in
the same commit.

## Answers 1-6

**1. [SOURCE]** `/process_video` is `async def`; body read on the loop; the
whole pipeline runs via `anyio.to_thread.run_sync` (service.py:131-144) — no
CPU work inline. A worker's event loop therefore never blocks, and **yes: a
single worker accepts unbounded concurrent requests while already
processing** (bounded only by anyio's default 40-thread limiter, > our C=16).

**2. [SOURCE]** No per-worker limit anywhere: the ENTRYPOINT has **no
`--limit-concurrency`** (Dockerfile.llamaindex-video:93), no app semaphore,
no queue. A request commits to a worker at kernel ACCEPT and never moves.
Kernel wake-up favors recently-active workers, an accepting-while-busy worker
keeps accumulating, and nothing sheds load — that is the whole mechanism of
pid12 taking 48 of 168 (even share 21; max/min ≈ 10×). Reproduced across
p1/p2 = structural, not noise.

**3. [ARITHMETIC on the measured numbers]** Cap each worker's occupancy at
1.0 (true busy fraction): p2 sum = 1+1+0.81+0.61+0.48+0.24+0.14+0.10 =
**4.38 concurrently-inferring workers** on average (p1: 4.69).
- W=8, torch 4: 4.38 busy × 4 threads × ~0.74 intra-op efficiency ≈ **12.96
  cores** — measured **13.013**. Fits.
- W=16, torch 2: same accept skew caps effective busy workers at ~5 (they do
  not scale with W); 5 × 2 × ~0.9 ≈ 9.0+extract ≈ **9.3** — measured
  **9.291**. Fits, and explains "more workers used LESS CPU": halving the
  width (4→2 threads) while the skew holds effective lanes ~constant.
  Also retro-explains B5's 16×2 = 0.0913 and its 15/16 serving.
So the ~2-3-busy guess was close but low: **~4.4 of 8 / ~5 of 16 effective**.

**4. [INFERRED from standard practice — not source]** The serving PATTERN
(uvicorn multi-worker, shared socket) is standard; running it with **no
admission control and no balancer is our deployment's defect**. Production
deployments put a least-connections proxy in front, or set
`--limit-concurrency` per worker (excess connections are refused and land on
another worker at re-accept), or use an external queue. Default uvicorn
behaves exactly as we measured; the default is known to skew under
long-request loads.

**5. [PROPOSAL — no code changed]** The minimal change that mirrors what we
already do for RocketRide: **8 single-worker uvicorn instances on ports
8802-8809, driver round-robins ports** — the exact structural twin of the
driver round-robining RR's 16 tokens. No handler, pipeline, or measurement
definition changes; stage_s stamps unchanged (though they should ALSO move
inside the lock so the clock stops measuring the queue — separate,
disclosable). Does it invalidate the banked LI legs? **They stay valid as a
posture, not as the headline**: they measure "default single-endpoint
deployment" — the LI analogue of RR's DEFAULT posture. Publishing RR
default+parity while publishing LI default-only is the asymmetry; a
"balanced" LI leg is the missing symmetric run. Ansh's ruling.

**6. Yes — as currently run it is an apples-to-apples violation.** Our
driver hand-balances the RocketRide arm (perfect token round-robin, coverage
asserted) and leaves the competitor arm to kernel accept. That is entry-12's
class — effort flowing to the home arm — expressed in infrastructure instead
of tuning. Either both arms get driver-side balancing (the 8-port change),
or the headline compares RR-parity against LI-default and says so. The
2.443-vs-2.44 default-vs-default agreement with Leela is untouched by any of
this; the 1.37x parity-over-LI figure is the number at stake, in LI's favor
if corrected.
