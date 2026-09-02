# RocketRide on ami_full — cross-team comparison, cover

**The table**: `AMI_CROSS_TEAM_TABLE.md` — Leela's and Shashi's
published RocketRide columns beside Ansh's three measured
configurations (16×OMP2, 8×OMP4, engine default), full AMI corpus:
168 meetings, 23,049 frames, 96.06 h, shared $-basis. Every Ansh figure
is read from committed run exports; provenance and hashes are in
`results/AMI_LANDING.md`.

**The finding, plainly.** At matched utilization (~90–93%) on the same
corpus and the same five-stage pipe, Ansh's harness spends **~19–20%
more CPU per frame** than both of the other two — 2.308 vs 1.934/1.893
CPU-s/frame at 16×2, and the same-sized gap at the other matched
posture — which surfaces as ~20% lower throughput. Leela's and Shashi's
independently built harnesses agree with each other to 0.3–0.5%, so
Ansh's side is the outlier and the burden of explanation sits there.

**Candidate causes — all HYPOTHESIS, none established:**

1. **Engine build, the one code delta held in evidence**: Leela's runs
   carry a patched 3.3.1 (chunk-duplication correction among the
   patches); Ansh's runs are stock 3.3.1, and Ansh's own provenance
   marks patched-vs-stock results not comparable. One weakening fact is
   on record: Ansh's duplication gates found no organic doubling on
   this corpus.
2. CPU-bracket edges (both sides exclude warm-up; the brackets are
   constructed differently).
3. Client topology (one client per task, N websockets, versus 16
   tokens multiplexed on one websocket).

**The ask.** One identical file run through both harnesses at the same
posture with a per-stage CPU split — or, alternatively, an exchanged
cgroup sampler stream for one full leg. Either one names where the
extra CPU goes; nothing else in this package does.

Full reconciliation, corpus-identity proofs, idle-window and
memory-basis cautions, and every HYPOTHESIS label:
`AMI_CROSS_TEAM_RECONCILIATION.md`.
