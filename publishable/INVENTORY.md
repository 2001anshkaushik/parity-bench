# INVENTORY — classification before any file moves

**Repo hygiene run, 2026-08-07.** Every file classified BEFORE restructuring. Nothing deleted;
moves only. `PUBLISHABLE` = push-ready, every number VERIFIED or explicitly PROVISIONAL and
traceable to a live result file. `ARCHIVE` = superseded/withdrawn, preserved because the
correction history is an asset. `WORKING` = active harnesses and raw data.
`EXCLUDE-FROM-GIT` = large, regenerable, or machine-specific.

## Root documents

| file | size | modified | class | why |
| --- | ---: | --- | --- | --- |
| `A3_SERIALIZATION_FINDING.md` | 9,034 | 08-06 | **PUBLISHABLE** | product finding: thread oversubscription (current) |
| `ADVERSARIAL_AUDIT.md` | 8,189 | 08-04 | **ARCHIVE** | audit of numbers now superseded |
| `CEILING.md` | 6,828 | 08-05 | **ARCHIVE** | ~2,600/s superseded (client-bound, not engine-bound) |
| `CONCURRENCY_CEILING.md` | 9,556 | 08-05 | **ARCHIVE** | same ceiling story, superseded |
| `CONCURRENCY_CHARACTERIZATION.md` | 12,484 | 08-06 | **ARCHIVE** | saturation + 31% decay content withdrawn s11 |
| `CROSSOVER_FINDING.md` | 20,320 | 08-05 | **ARCHIVE** | ON HOLD; central framing refuted s6 |
| `DEPLOYMENT_PARITY.md` | 5,592 | 08-04 | **ARCHIVE** | pre-protocol Tier1/Tier2 numbers |
| `DOCKER_ARCHITECTURE.md` | 13,735 | 08-07 | **PUBLISHABLE** | container design, awaiting approval, nothing built |
| `ENVIRONMENT.md` | 7,384 | 08-04 | **PUBLISHABLE** | pinned environment + engine SHA256 |
| `FAIRNESS_BASIS.md` | 11,165 | 08-07 | **PUBLISHABLE** | comparison basis + canonical pipeline decision (current) |
| `FAULT_ISOLATION_PROBE.md` | 9,241 | 08-04 | **ARCHIVE** | contains the withdrawn 13.82/1.95 hang ratio |
| `FAULT_MATRIX.md` | 10,428 | 08-04 | **ARCHIVE** | superseded fault numbers |
| `FINDINGS_FOR_WS1.md` | 25,172 | 08-05 | **ARCHIVE** | built on the 7,871-8,540 cluster and pre-protocol numbers |
| `LLAMAINDEX_DEPLOY_QUESTION.md` | 7,198 | 08-06 | **ARCHIVE** | superseded by PARSER_DECISION.md + llama-deploy deprecation |
| `OPERATIONAL_COMPLEXITY.md` | 3,255 | 08-04 | **ARCHIVE** | pre-protocol |
| `PARITY_CORPUS_FINDINGS.md` | 10,442 | 08-05 | **ARCHIVE** | 1.73x withdrawn; burst-mode crossover superseded |
| `PARITY_REPLICATION.md` | 8,064 | 08-05 | **ARCHIVE** | carries a WITHDRAWN banner |
| `PARSER_DECISION.md` | 7,972 | 08-07 | **PUBLISHABLE** | decision brief for Shashi (current) |
| `PARSER_PREMISES.md` | 7,376 | 08-07 | **PUBLISHABLE** | both parser premises tested and refuted (current) |
| `PDF_PIPELINE_NOTES.md` | 10,303 | 08-06 | **ARCHIVE** | superseded by PARSER_PREMISES.md; carries s8 corrections |
| `PROCESS_SCALING.md` | 10,767 | 08-04 | **ARCHIVE** | pre-protocol |
| `READINESS.md` | 6,059 | 08-07 | **ARCHIVE** | saturation points withdrawn s11; gap list survives in publishable/README |
| `README.md` | 7,163 | 08-04 | **ARCHIVE** | superseded by publishable/README.md; cites 155ms IPC |
| `REBASELINE_PLAN.md` | 8,503 | 08-06 | **PUBLISHABLE** | re-baseline anchors + container-tax metric |
| `RUNBOOK_LLAMAINDEX.md` | 14,112 | 08-05 | **PUBLISHABLE** | service runbook, verified by execution |
| `SCHEMA_PROPOSAL.md` | 14,637 | 08-05 | **PUBLISHABLE** | wire contract v0.2 (unagreed — Leela owns) |
| `SCOPED_CLAIM.md` | 5,278 | 08-05 | **ARCHIVE** | rests on the withdrawn burst/sustained framing |
| `STATE.md` | 35,788 | 08-07 | **PUBLISHABLE** | durable resume point + full supersession history (history section may cite withdrawn numbers by design) |
| `TIER2_RESULT.md` | 7,774 | 08-05 | **ARCHIVE** | 3.69x superseded by 2.36x, itself PROVISIONAL |
| `TOIL_INSTRUMENT.md` | 8,696 | 08-06 | **PUBLISHABLE** | pre-registered toil instrument + COI declaration |
| `TOIL_LLAMAINDEX.md` | 17,637 | 08-05 | **ARCHIVE** | superseded by TOIL_INSTRUMENT.md |
| `TWO_TIER_PARSER_DESIGN.md` | 6,748 | 08-07 | **PUBLISHABLE** | Tier1/Tier2 design incl. quality metric (design only) |
| `VARIANCE_PROTOCOL.md` | 8,442 | 08-05 | **PUBLISHABLE** | measurement protocol |
| `progress.md` | 44,711 | 08-07 | **ARCHIVE** | chronological log — cites withdrawn numbers by nature |

**13 publishable, 21 archived, 34 total root documents.**

## Directories

| path | files | bytes | class | why |
| --- | ---: | ---: | --- | --- |
| `working/ws1/` | 10 | 55,359 | **WORKING** | the LlamaIndex service — schema/pipeline/service, deliberately isolated layers |
| `working/scripts/` | 56 | 473,185 | **WORKING** (9 deprecated → archive) | harnesses; deprecated ones get an exit guard |
| `working/harness/` | 9 | 62,107 | **WORKING** | engine_ops, seeds, stats, collector |
| `working/nodes/` | 24 | 22,570 | **WORKING** | benchmark-only engine nodes (split_embed, cpu/noop/env/pdf probes) |
| `working/handoff/` | 11 | 101,230 | **WORKING** | drop-in modules for Shashi + parity replication request |
| `working/results/` | 43 | 157,023 | **WORKING** | raw JSON; withdrawn ones move with their doc |
| `working/dossiers/` | 31 | 58,011 | **WORKING** | package provenance from verify_frameworks |
| `working/pipes/` (8 hand-written) | 8 | 3,986 | **WORKING** | canonical + probe pipelines |
| `working/pipes/generated/` | 2,008 | 939,092 | **EXCLUDE-FROM-GIT** | harness-generated per-run pipe files; fully regenerable |
| `working/results/selftest/` | 82 | 298,193 | **EXCLUDE-FROM-GIT** | instrument self-tests, regenerable |
| `logs/` | 54 | 296,850 | **EXCLUDE-FROM-GIT** | run logs; contain absolute paths |
| `data/mt10k/` | 1 | 4,152,355 | **EXCLUDE-FROM-GIT** | corpus sample; rebuildable from Leela's manifest (10,000/10,000 sha256 verified) |
| `pdftest/` | 6 | 72,630 | **EXCLUDE-FROM-GIT** | generated PDF fixtures, regenerable |
| `engine/` | — | 1.2 GB | **EXCLUDE-FROM-GIT** | vendored engine bundle + hand-copied pypdf (see §Provisioning) |

## Deprecated harnesses — archived WITH an execution guard

A quarantined script that still runs will get run. Each of these exits non-zero with an
explanation if invoked.

| script | why deprecated |
| --- | --- |
| `burst_vs_sustained.py` | produced the 31% decay artifact: n=1, no control arm, swallowed failures |
| `token_sweep_extended.py` | fresh-task-per-rep; burst-mode framing withdrawn |
| `token_sweep_persistent.py` | sustained curve invalidated s6 |
| `topology_and_chunking.py` | 37-61% spreads; superseded by topology_persistent.py |
| `concurrency_parity.py` | per-rep burst boundaries across unsynchronised drivers (12-58% spreads) |
| `isolated_profile.py` | ASCENDING cold sweep — under-measures (s11). Use the pre-warm variant |
| `isolated_profile_rr.py` | ASCENDING cold sweep — all four saturation points withdrawn (s11) |
| `optimal_point.py` | operating points came from withdrawn saturation figures |
| `decay_rootcause.py` | phase-5 aggregation summed per-burst-index rates across desynced drivers |
