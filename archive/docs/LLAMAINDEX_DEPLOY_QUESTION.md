# Is Our Hand-Rolled FastAPI Service a Strawman? — llama-deploy decision

**For Leela and Shashi. A decision, not a change — nothing has been switched.**
Ansh · 2026-08-06 · evidence: `dossiers/llama-deploy.json`, package metadata, upstream repos.

---

## Recommendation

**Keep the FastAPI service. Do not adopt llama-deploy.** The concern that prompted this — that we
built a strawman against our own framework — is legitimate, but the specific alternative does not
survive contact with its own repository.

**llama-deploy is deprecated by its authors.** Its README states plainly:

> "This project is deprecated. To serve workflows, use llama-agents instead."

Adopting a deprecated deployment path would be a *worse* representation of LlamaIndex production
practice than what we have now, not a better one. [VERIFIED — upstream repo README]

**There is a live successor, and it deserves a decision of its own** (§3). I am not making that
call unilaterally.

## 1. What llama-deploy actually is [VERIFIED — PyPI metadata + repo]

| | |
| --- | --- |
| Latest version | **0.9.2** |
| Last release | **2026-04-06** (121 days before this note) |
| Release count | 77 |
| Requires Python | `>=3.10,<4.0` — compatible with our 3.12.13 |
| License | **not declared in package metadata** — UNVERIFIED, would need repo inspection before any use |
| Upstream status | **DEPRECATED** |

**Blocking technical fact independent of the deprecation:**

```
llama-deploy 0.9.2 requires  llama-index-core >=0.11.17, <0.14.0
our service runs             llama-index-core   0.14.23
```

Adopting it **forces a downgrade of llama-index-core below 0.14**. We would be benchmarking an
older LlamaIndex than the one we have characterised, and every existing measurement would need
redoing on the downgraded stack. [VERIFIED — declared dependency metadata. Note the *resolver
behaviour* was not executed: no pip/uv is available in the venv, so this is the declared
constraint, not an observed downgrade.]

**What its dependency list tells you about its shape:** `aiokafka`, `kafka-python-ng`, `redis`,
`aio-pika` (RabbitMQ), `prometheus-client`, and five OpenTelemetry packages. This is a
**distributed, message-queue-based control plane for multi-service agent deployments** — not a
"wrap your pipeline in HTTP" library. For a single stateless `POST /process` doing split+embed, it
is a large amount of moving infrastructure to stand up, containerise, and keep symmetric with the
RocketRide arm.

## 2. So were we building a strawman?

**No, on the evidence.** WS-1's standard is "follow each framework's own documented production
deployment guidance." LlamaIndex's own guidance does not point at llama-deploy — it points away
from it.

Our service is also not naive: single-purpose FastAPI, uvicorn with uvloop and httptools, model
loaded once in `lifespan`, CPU device asserted at startup, sync endpoint dispatched to Starlette's
threadpool for CPU-bound work, 8 workers. That is a normal, defensible production shape for a
stateless embedding endpoint.

**The honest caveat:** "not a strawman" is a weaker claim than "the framework's blessed path." I
can defend the first. The second now depends on §3.

## 3. The open question I am NOT deciding alone — llama-agents

The successor is **`llama-index-workflows`**, marketed as **LlamaAgents**
(`github.com/run-llama/workflows-py`). From its README [VERIFIED — upstream repo]:

* self-described as "an open-source framework for building and shipping **document-centric agents**"
* **requires code to be structured as `Workflow` classes with `@step`-decorated async functions
  that emit and consume events**
* offers three deployment tiers: as a library, **mounted into an existing app via
  `llama-agents-server`**, or end-to-end via a `llamactl` CLI

**Does it impose structure our task does not need? Yes.** Our split+embed has one step, no
branching, no agent loop, no state to carry between steps, and no events. Expressing it as a
Workflow with `@step` functions and event classes is ceremony that exists to serve multi-step
agentic pipelines. It would not make the service faster or more production-like; it would make it
more idiomatic to that framework.

**The middle path that makes this cheap:** `llama-agents-server` is documented as mountable inside
an existing application. So the pipeline logic in `ws1/pipeline.py` could stay exactly as it is and
be exposed *additionally* through the framework's own server, letting us measure both without
rewriting the work.

### Toil delta, both directions [PROVISIONAL — estimates, not measured]

| | keep FastAPI | adopt llama-agents |
| --- | --- | --- |
| Rewrite pipeline as Workflow + events | — | ~3–5 h |
| New dependency surface to pin, containerise, digest-lock | — | ~1–2 h |
| Ongoing: track a framework in active churn | low | medium |
| Risk of "you didn't use their real path" in review | **medium — this is the whole risk** | low |
| Risk of measuring framework ceremony instead of embedding work | low | **medium** |

Estimates are labelled PROVISIONAL because they are judgement, not measurement. Under
`TOIL_INSTRUMENT.md` they must not be quoted as toil results — that instrument requires the work
to actually be done and counted.

## 4. What I recommend we decide

1. **Now:** keep FastAPI for WS-1. It is defensible, it is current, and the alternative is
   deprecated. *(My call, reversible.)*
2. **Leela/Shashi to decide:** whether WS-1's "documented production path" standard obliges a
   second LlamaIndex arm built on `llama-agents-server`. If yes, I would mount the existing
   pipeline rather than rewrite it, and report both arms.
3. **Before any adoption:** resolve the llama-agents license and pin its version, and re-run
   `verify_frameworks.py` against it — I ran it against llama-deploy only.

## 5. Labels

| claim | label |
| --- | --- |
| llama-deploy is deprecated upstream | **VERIFIED** (repo README) |
| llama-deploy 0.9.2 pins `llama-index-core<0.14.0`, conflicting with our 0.14.23 | **VERIFIED** (declared metadata) — resolver behaviour **UNVERIFIED**, no pip/uv available to execute a dry run |
| llama-deploy last released 2026-04-06; license undeclared in metadata | **VERIFIED** |
| llama-deploy is a distributed queue-based control plane | **VERIFIED** (dependency set) |
| `llama-index-workflows` requires `Workflow`/`@step`/event structure | **VERIFIED** (repo README) |
| llama-agents can be mounted into an existing app | **PROVISIONAL** — stated by the README, not executed by me |
| Our FastAPI service is not a strawman | **PROVISIONAL** — rests on the absence of a live documented alternative, which §3 could change |
| Toil estimates in §3 | **UNVERIFIED** — judgement, not measured |

> *Hostile reviewer: "You benchmarked LlamaIndex with code you wrote yourself and concluded your
> own code was fine."*

The deprecation is the framework's own statement, not my judgement, and the version conflict is in
the package's declared metadata. The part that is genuinely my judgement — whether llama-agents is
obligatory — is exactly the part I am handing to Leela and Shashi rather than settling.
