# Archive Films benchmark — two-minute summary (2026-09-03)

**What we ran.** Two deployed AI video pipelines — RocketRide's engine
and a LlamaIndex-based service, running the identical model stack and
the identical work — processed the same 35 feature films (49 hours of
footage) on one 32-core machine, both tuned and out-of-the-box, every
measured configuration run twice.

## What we found

**1. Out of the box, the engine runs at a quarter of its own speed.**
A developer who deploys RocketRide without tuning gets 2.35 frames/s;
the same engine on the same machine and corpus, tuned (16 workers × 2
threads), gets 9.5 — a **4.05× gap**, with the untuned run using 20% of
the machine. The comparison arm is configuration-limited out of the box
too. The performance a customer sees is decided by a tuning step
neither framework performs for them.

**2. Tuned head-to-head, the gap is idle cost, not work efficiency.**
LlamaIndex delivered **+6.5%** throughput. On cores actually consumed
it looks far better — **+26.7% per core** — but strip out what each
side burns while doing nothing and the gap collapses to **+3.9%**. The
two engines do the work at nearly the same per-core cost; the
difference is that RocketRide's process model burns **4.66 of 32 cores
(14.6% of the machine) standing still** just holding 16 workers
resident — 1.23 cores even with a single worker — while the comparison
arm's idle cost is near zero. That idle burden is a property of the
engine's design, and it is the number to fix.

**3. The two deployments disagree about what they see in big video.**
Same detector, same code, same weights, byte-identical frames in: on
video at or below the detector's 560-pixel input size, the two
systems' detections are identical to the last bit; above it — where
every frame must be shrunk first — their results drift by fractions of
a percent, enough to flip borderline detections (27 of the 35 films; measured corpus-wide since: 435 of all 500 films — 87% — sit above the edge). The obvious explanations are all disproven by measurement:
in isolation the detector is provably bit-identical on both stacks,
even on the exact frames that disagreed in production, at two thread
settings. The drift appears only under the full production workload,
and the evidence so far points at the engine's serving path as the
side that departs. Frame counts and every throughput number above are
unaffected.

## What it means for the product

Two costs ship with the engine's defaults today, and together they —
not competitor speed — dominate every measured gap: an untuned
deployment runs ~4× below the engine's own attainable throughput, and
each resident worker burns idle CPU (4.66 cores at 16 workers) before
any work arrives, which is the entire difference between "27% worse
per core" and "4% worse per core." Fixing them closes most of the
measured gap and brings per-core work cost within 4% of the comparison
arm — not parity: the tuned throughput gap was still +6.5%, and
removing the idle burn from a denominator does not remove it from the
machine.
Separately, detection reproducibility above 560px is an exposure: two
correct deployments of the same stack can disagree on borderline
detections in large video — a QA and audit-reproducibility risk, filed
upstream with a ready-made isolation test attached.

## Not settled

Which serving-side condition triggers the big-video drift (the
evidence points at the engine's serving path; the instruments to
settle it are written and committed). And the cross-team question: our
RocketRide runs ~19–20% more CPU per frame than two other teams
measure at matched utilization on byte-identical data — a handover
package with a specific ask is ready.

## Where the detail lives

`WS1_Phase2_Films_Benchmark_DEFINITIVE.md` — the full report; every
figure traces to a committed artifact. `AMI_CROSS_TEAM_COVER.md` — the
cross-team CPU question, one page, with its table and ask.
