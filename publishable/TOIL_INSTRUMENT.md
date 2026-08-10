# Toil Instrument — pre-registered BEFORE the gold-standard build

**Pre-registration.** Ansh · 2026-08-06. Written **before** the LlamaIndex gold-standard service is
built and before any toil is counted. Changing these definitions after seeing results invalidates
the instrument.

---

## 0. The claim this instrument is meant to support, stated honestly

We intend to say something like *"standing up a production-grade embedding service costs materially
more effort with LlamaIndex than with RocketRide."* That claim is only credible if the measurement
was defined in advance, applied symmetrically, and includes **RocketRide's own toil** rather than
treating "handled natively" as free.

**If the instrument shows no material difference, that is the result and it gets published as
such.** Pre-registering is what makes that outcome possible.

## 1. Conflict of interest — declared

**I build the LlamaIndex service and I also measure how hard it was to build.** I do not build the
RocketRide service; Shashi does. That is a direct conflict: I have more visibility into one side's
difficulty, and an incentive to have my own work look substantial rather than trivial — or, in the
opposite direction, to look efficient.

Guards, in order of strength:

1. **Counts come from artifacts, not recall.** Line counts from `git diff --stat`, file counts,
   dependency counts, config-key counts, and timestamps from commit history. Not "how long did that
   feel."
2. **The RocketRide column is filled in by Shashi**, from his own build, using this same document.
   I do not estimate his side. Where I have listed RocketRide items in §4 they are *categories to
   be filled*, plus specific costs already measured in this project with citations.
3. **Every number carries who produced it.** No blended figures.
4. **A category where I cannot get a symmetric count is reported as a gap, not estimated.**
5. **The instrument is published with the result**, so a reader can see what was and was not
   counted.

**What this does not fix:** I still chose the categories in §2, and category choice can steer a
result. Leela and Shashi should challenge the category list *before* building, which is why this
document exists now rather than after.

## 2. Categories — FIXED NOW, not to be changed after results are seen

| # | category | counted as | explicitly excludes |
| --- | --- | --- | --- |
| 1 | **Scaffolding** | LOC written by us that is not pipeline logic: server setup, lifecycle, wire types, health/readiness | the embedding/splitting logic itself, which both sides must write |
| 2 | **Configuration** | count of distinct config keys/env vars that must be set correctly for a *correct* run, plus count of those whose default is wrong for our workload | keys that can be left at default safely |
| 3 | **Error handling** | LOC + distinct failure modes explicitly handled (bad input, model load failure, timeout, backpressure) | failures neither side handles |
| 4 | **Deployment** | steps from clean machine to serving requests, counted as discrete actions; plus artifacts needed (Dockerfile, entrypoint, readiness gate) | the benchmark harness |
| 5 | **Ongoing operations** | recurring actions to keep it healthy: restarts required, manual interventions, known operational hazards | one-time setup |

**Counted for both sides identically. A category with no symmetric count is reported as a gap.**

## 3. Starting state — declared, because "already running on our laptops" is not one

| | declared starting state |
| --- | --- |
| Machine | clean, no prior install of either stack, no warmed caches, no pre-downloaded models |
| Network | available (both sides need to fetch something) |
| **My prior experience** | Full-Stack AI/ML engineer; **fluent** in FastAPI/uvicorn/Python packaging; **first time** building a benchmark suite; ~5 sessions of accumulated RocketRide-specific knowledge from this project |
| **Shashi's prior experience** | to be declared by Shashi in the same terms, before he starts |
| Documentation allowed | each framework's own public docs; no internal RocketRide knowledge unavailable to an external user |

**The prior-experience asymmetry is the instrument's biggest weakness and must be stated in any
result.** I am fluent in one stack and a five-session novice in the other. That advantage flows
toward LlamaIndex looking easier. Two partial mitigations:

* count **artifacts** (LOC, config keys, steps) rather than **time**, since artifacts are far less
  sensitive to familiarity
* record time as a *secondary, clearly-labelled* figure, never the headline

## 4. RocketRide's own toil — the column that must not be empty

"Handled natively" is not free; it trades effort for control. These are **already-measured** costs
from this project, with citations, and they belong in the same table as LlamaIndex's scaffolding:

| RocketRide cost | evidence | category |
| --- | --- | --- |
| **~60 s engine cold start**, ~36 s model load — must be outside every timed region and every readiness gate | STATE §9 traps | 4, 5 |
| **No config surface for node thread count.** The only lever found is process environment at engine start, global to every pipeline on that engine. Costs 19 % throughput and 2.2× scaling if wrong | `A3_SERIALIZATION_FINDING.md` | 2 |
| **Splitter kwargs silently dropped** by `_filter_kwargs_for` — configuration that appears to apply and does not. Required writing a custom node to work around | session-5 notes; `working/nodes/split_embed/` exists only because of this | 2, 3 |
| **~150-pipeline livelock** in the N-concurrent-pipelines model, leaving 81 orphaned `node.py` processes | finding 16 (VERIFIED, reproduced twice) | 5 |
| **One live task per `project_id`** — N concurrent tasks require N distinct pipe files, generated | STATE §9 traps | 1, 4 |
| **`get_server_info()` broken** (`public=True` stored, never read); health must use `GET /version`, and `/ping` is auth-gated returning 401 | STATE §9 traps | 3, 4 |
| **Custom nodes must be copied into the engine bundle** (`engine/nodes/`) and the engine restarted | observed this session; `start_engine.sh`'s comment claiming otherwise is stale | 4, 5 |

**And the corresponding LlamaIndex costs already known:**

| LlamaIndex cost | evidence | category |
| --- | --- | --- |
| **Device silently resolves to `mps`** when unset, with 14–25 % irreducible variance; required an explicit startup assertion | findings 6, 13 | 2, 3 |
| **Declared 14 workers measured 8** effective | finding 9 | 2 |
| **`/health` returns 200 before the service is ready** (answered by one worker); readiness requires counting `warm in` lines | `RUNBOOK_LLAMAINDEX.md` | 3, 4 |
| **Deployment path ambiguity** — the framework's own `llama-deploy` is deprecated; we hand-rolled | `LLAMAINDEX_DEPLOY_QUESTION.md` | 4 |

**Both columns already have real entries.** Any result claiming one side is effortless is wrong on
the evidence we already hold.

## 5. Reporting format — fixed now

For each category, a table with: **count**, **who measured it**, **artifact the count came from**,
and a **VERIFIED / PROVISIONAL / UNVERIFIED** label. Plus, mandatory in any published result:

* the starting-state declaration from §3, including the prior-experience asymmetry
* the conflict-of-interest note from §1
* categories where a symmetric count was not obtainable, listed as gaps
* **the control trade**: what the lower-toil side gives up in control (§4 shows this is not
  hypothetical for RocketRide)

**Not permitted:** a single blended "toil score", a time-only headline, or any comparison that
omits §4.

## 6. What would falsify the claim we expect to make

Pre-registered, so the outcome cannot be reinterpreted afterward:

* if **scaffolding LOC** is within ~30 % between the two, the scaffolding claim fails
* if RocketRide's **configuration** count (§4 already lists three landmines) meets or exceeds
  LlamaIndex's, the configuration claim fails
* if **ongoing operations** favours LlamaIndex (livelock and cold start are real recurring costs),
  that reverses the expected direction and gets reported as such
* if the only difference is **deployment steps**, the claim narrows to deployment and must not be
  stated as general setup effort

## 7. Open, to be settled before building

1. **Shashi to declare his starting state** in §3's terms, before he starts.
2. **Leela and Shashi to challenge the category list** in §2 — after building, changes are not
   allowed.
3. Whether a second LlamaIndex arm on `llama-agents-server` is required
   (`LLAMAINDEX_DEPLOY_QUESTION.md` §3). If so its toil is counted **separately**, not merged into
   the FastAPI column.
