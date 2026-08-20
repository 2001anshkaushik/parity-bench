# Single-video probe — Phase 2 (video/detect), build-order step B

One recording (ES2002a.Corner.avi, sha-pinned), both arms, C=1, wall clock.
No harness imports. Local runs prove wiring only; every number that matters is
captured on the box (settled decision 6).

This directory was rewritten on 2026-08-20: the earlier staging predated the
audio-out decision (settled decision 1) and carried audio lanes, a fan-in pipe
and a mux step. All three are gone. The probe pipe is now THE pipe under test,
`../benchmark_video_detect.pipe` — never a lookalike.

## What it answers

1. **Per-stage wall time.** RR arm: send-1 (first-load installs + weight
   downloads + first inference) vs send-2 (steady state); per-frame
   decode/detect/emit from the detect node's own debug lines when the log
   level surfaces them. LI floor: every stage timed directly.
2. **Frames actually extracted** (verifies interval semantics, settled
   decision 2). Expected on ES2002a.Corner (1248.3 s @ fps=1/15): **84**.
   ~1248 means `interval` did not take — stop and re-examine config before
   trusting anything else.
3. **Chunks produced** = `len(response['documents'])` on the RR arm, plus
   `metadata.chunkId` monotonicity (proves accumulate-then-split, one split
   per video). Expected ~45-60 for a 21-min video: the engine's chunk-size
   config is INERT (_filter_kwargs_for strips **kwargs-routed params — box
   records adjudicated 2026-08-20), so splitting runs at LangChain library
   defaults 4000/200 regardless of any strlen setting. max chunk chars must
   sit in (512, 4000].
4. **Duplication signature.** On `rr:patched`: none. On stock the whole chunk
   list would appear twice ([A..Z,A..Z]). Organic exact-duplicate chunks
   (static scenes) are counted separately and are NOT the defect signature.
5. **Peak cgroup anon memory** (`memory.peak` + `memory.stat` anon — the
   quotable figure per memory_sources hierarchy) and **CPU utilisation
   against the container's own cgroup** (`cpu.stat` usage_usec ÷ wall ÷ 32),
   never the driver's affinity. Driver CPU sampled alongside.
6. **Disk read throughput during decode** (probe_disk.sh) — cold-cache raw
   read, cold decode, warm decode, and an O_DIRECT parallel-read ceiling.
   This is the number that decides storage; we do not upgrade on assumption.
7. **Token topology census** (`probe_rr.py --tokens M`): proves how many
   distinct detector instances actually serve, per arm — process census +
   per-process CPU deltas during concurrent sends, not config inference.

## What it is NOT

- Not a comparative benchmark. The LI side here is a bare-venv model floor.
- Not the concurrency probe. BLAS oversubscription and the blast-leg token
  count are a separate, later probe (HELD until this one reports).

## Order on the box

```
./probe_fetch.sh        # sha-pinned fetch; exits non-zero on any mismatch
./probe_disk.sh         # storage numbers (wants sudo for drop_caches; see below)
./probe_run.sh          # RR thread matrix + LI floor + token census, one at a time
```

## sudo / drop_caches

Cold-cache runs need `sudo tee /proc/sys/vm/drop_caches`. If sudo is absent
the scripts SAY SO, mark those numbers `cache=warm-only`, and continue — the
O_DIRECT parallel-read test still gives a device ceiling without sudo.

## Expected values (assumptions to be replaced, not trusted)

frames=84; chunks≈45–60 (4000/200 library defaults); detections/frame≈5–15;
whole-list duplication only on stock, and only on records with >=64 chunks —
which a 21-min video does NOT reach at 4000-char chunks (~29+ min meetings
do); cpu_util well under 1.0 at threads=1.
