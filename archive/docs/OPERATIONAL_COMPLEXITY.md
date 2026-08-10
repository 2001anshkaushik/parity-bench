# STEP 4 — Operational Complexity

Facts only. **Kept deliberately separate from every performance table** — ease of operation is a
real procurement input, but folding it into a performance chart is how a benchmark becomes
marketing. (Same reason "lines of code" was dropped from the metric set entirely: trivially
gameable, and it measures API taste rather than anything operational.)

Raw data: `results/operational/operational.json`.

| | langgraph | crewai | RocketRide SDK | FastAPI+uvicorn stack |
| --- | ---: | ---: | ---: | ---: |
| Transitive dependencies | 35 | **135** | **8** | 19 |
| Install size on disk | 23.4 MB | **592.0 MB** | **7.9 MB** | 15.9 MB |
| Cold import time | **0.1 ms** \* | **4,531.8 ms** | 467.7 ms | 458.0 ms |
| Hosted service / API key required to run? | no | no | no | no |
| Processes required to operate | 1 (in-process) | 1 (in-process) | **1 client + 1 engine + 1 task tree per live pipeline** | 1 master + N workers |
| Engine cold start | n/a | n/a | **~60 s first launch** (embedded-Python bootstrap), ~1 s warm | ~1 s |
| Config required | none | none | `.pipe` file (JSON) + `project_id` GUID + `source` field + `ROCKETRIDE_URI` + `ROCKETRIDE_APIKEY` | none beyond app code |

\* langgraph's 0.1 ms is a lazy top-level import — the real cost is deferred to first graph
construction and is not captured here. Do not read it as "600× faster to start than crewai".

## Notable

- **crewai is the heavy one by a wide margin**: 135 dependencies, 592 MB on disk, 4.5 s to import.
  That is a real operational cost in container image size and cold-start latency.
- **RocketRide's SDK is the lightest thing measured** — 8 dependencies, 7.9 MB. But the SDK is only
  the client: operating it also requires the ~172 MB engine bundle and a running server process,
  which the Python frameworks do not need. The fair statement is *small client, separate server*,
  not *small footprint*.
- **RocketRide is the only entry needing a config file.** A `.pipe` requires a literal GUID
  `project_id`, a `source` field (documented as optional / extension-managed, but the engine
  rejects the pipeline without it), and `components` ordered first. The Python frameworks need no
  file at all.
- **Nothing tested requires a hosted service or API key to run.** RocketRide's `MYAPIKEY` is a
  built-in local dev key, not an account credential.

## UNVERIFIED / scope

- **Install times are meaningless as measured** (0.13–0.6 s): `uv`'s cache was already warm, so
  these are cache-hit times, not first-install times. Ignore that column; dependency count and
  on-disk size are the reliable signals.
- **Downscaled for the session budget**: `deepagents` (built on langgraph — not an independent
  data point) and `omnigent` (Track A locality still PENDING) were dropped from this pass. Both
  belong in the full table before publication. Stated, not silently skipped.
- "Time to first working pipeline from a clean machine" was not measured as a wall-clock figure.
  What *is* recorded, from this session: RocketRide needed a 172 MB engine download, a ~60 s
  first-launch bootstrap, and two undocumented discoveries (`source` is required; the tarball is
  flat and must not be extracted with `--strip-components=1`).
