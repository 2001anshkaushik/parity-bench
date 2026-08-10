# Docker Architecture — design for review, NOTHING BUILT

**For Ansh's review before any build.** 2026-08-06.
No image has been built, no Dockerfile written, no daemon started. This is the design only.

---

## 0. Read this section before the rest

**Docker on macOS is a Linux VM under Apple's Virtualization framework.** Every container number we
produce runs inside that VM, on virtualised CPU and a virtualised network stack, with a filesystem
boundary between the VM and the host.

**Therefore: these are reproducibility-and-symmetry numbers, not production-performance numbers.**
Containerising buys us identical, declared, reproducible environments for both arms — which is
exactly what the last six sessions of instrument failures argue for. It does **not** buy us numbers
that predict production throughput on Linux hardware.

**A native Linux run is still required before anything goes outside the team.** Nothing in this
document changes that, and no container number should be quoted externally without it.

Specifically, what Docker-on-macOS does **not** give us:

| | |
| --- | --- |
| Native CPU performance | VM scheduling sits between the container and the 14 cores |
| Real network behaviour | the bridge is virtual; loopback inside a VM is not loopback on a host |
| Real disk I/O | virtiofs/gRPC-FUSE for bind mounts is dramatically slower than native — model loads and corpus reads must not cross it (§4) |
| Host memory semantics | the VM has a fixed allocation; macOS memory compression is invisible inside it |
| Anything about Apple Silicon GPU | `mps` is not available in the VM at all — CPU-only, which happens to match our pinned device |

## 1. Platform: linux/arm64 only

**Requirement: no layer may pull an x86 image.** Rosetta emulation of an x86 base would silently
change every number, and it would look like a framework difference rather than an emulation
artifact.

Enforcement, in order of strength:

1. **Pin the platform explicitly** on every stage: `FROM --platform=linux/arm64 <image>@sha256:…`
2. **Assert at build time** — a `RUN` step that fails the build on the wrong arch:
   ```
   RUN [ "$(uname -m)" = "aarch64" ] || (echo "NOT arm64: $(uname -m)" && exit 1)
   ```
3. **Assert at runtime** — the service reports `platform.machine()` in its `/manifest`, and the
   run manifest records it. A number whose manifest says `x86_64` is void.
4. **Verify Rosetta is off**: Docker Desktop's "Use Rosetta for x86/amd64 emulation" must be
   disabled, and `docker info` must not list `rosetta` support in use.

**Both service images and the driver image get all four checks.** An emulated driver would skew the
client side, which is where several of this project's worst artifacts have come from.

## 2. What gets containerised: everything, or the comparison is void

Three images:

| image | contains |
| --- | --- |
| `ws1-llamaindex` | Python 3.12, LlamaIndex service, **model baked in** |
| `ws1-rocketride` | engine bundle + benchmark nodes, **model baked in** |
| `ws1-driver` | the load harness (barrier-synchronised windows), no model |

**Asymmetric containerisation is worse than none.** A containerised service measured by a native
driver mixes a virtualised server with a native client, and the container tax lands on one side
only. The driver is containerised for the same reason both arms are: so the tax is paid
symmetrically and can be measured.

## 3. Resource contract — identical, declared, and verified

Both **service** containers get identical limits, declared as contract fields in the run manifest
alongside `device`:

```
cpus     = 4.0
memory   = 12g            # EVIDENCE-BASED, and bounded by the VM. See the arithmetic below.
memory-swap = 12g         # equal to memory ⇒ swap disabled; otherwise a memory-pressure
                          # result is really a swap result
pids-limit = 4096
```

### The 8 GB proposal was wrong and would have voided the comparison [VERIFIED — measured 2026-08-06]

Peak RSS of the whole process tree, sampled continuously at 250 ms during load (a between-cell
sample understates the peak ~4.8×, which is how the first version of this measurement got it wrong):

| tokens/doc | conc | RocketRide peak | LlamaIndex peak |
| ---: | ---: | ---: | ---: |
| idle (no load) | — | **204 MB** | **4,642 MB** |
| 400 | 32 | 1,002 MB | 4,998 MB |
| 1,600 | 32 | 1,291 MB | 5,724 MB |
| **6,400** | **32** | **2,356 MB** | **7,950 MB** |

**An 8 GB cap sits at 99.4 % of the LlamaIndex arm's peak and 29 % of RocketRide's.** The first arm
to OOM would OOM because of a limit I picked, and it would look like a framework result. PDFs will
push the working set up, not down.

**Why the asymmetry is structural, not a defect:** the LlamaIndex service carries **4,642 MB before
a single request arrives** — 8 uvicorn workers each holding a model and a torch runtime. Its
parallelism comes from processes, so its floor scales with worker count. RocketRide's tree idles at
204 MB and grows with document size instead. These are different memory *shapes*, and a single
ceiling has to clear both.

### Ceiling = 12 GB per service — the arithmetic, corrected 2026-08-07

16 GB was the naive "2× the heavier peak" answer and **it does not fit**. The chain of ceilings:

```
host physical RAM                                  48 GB
Docker Desktop VM allocation (settings-store)      32 GiB      <- the real ceiling, not 48
  minus VM overhead + driver container (~4 GiB)    28 GiB usable for services
  two service containers, equal by contract        14 GiB each maximum
```

A 16 GB × 2 contract needs 32 GiB for services alone plus overhead plus the driver — **more than
the VM has.** Docker would either refuse the limits or, worse, accept them and let the VM thrash,
which would look like a framework result.

**12 GB per service** is what actually fits, and it is still comfortable against the evidence:

| | measured peak | headroom at 12 GB |
| --- | ---: | ---: |
| LlamaIndex (heavier arm) | 7,950 MB | **1.51×** |
| RocketRide | 2,356 MB | 5.09× |

2 × 12 GB = 24 GiB for services, + ~4 GiB driver and VM overhead = **28 GiB inside a 32 GiB VM.**

**The headroom is asymmetric and that is unavoidable** — the arms have genuinely different memory
shapes. What matters for validity is that the *limit* is identical and that neither arm reaches it.
1.51× on the heavier arm is thin enough that **peak RSS must be recorded every run**, and any run
where LlamaIndex exceeds ~10 GB is treated as approaching the ceiling and re-examined rather than
reported.

**If the 6,400-token cell ever exceeds 10 GB**, the response is to drop that cell from the
container comparison and measure it natively — not to raise one arm's limit.

**Recorded as a contract field** alongside `device`, and the manifest records observed peak RSS per
run so a future change in either arm's footprint is visible rather than silent.

The **driver** container gets its own separate, larger allocation (`cpus=4.0`) so it is never the
bottleneck — and that must be **demonstrated**, not assumed: if raising the driver's CPU changes
the measured throughput, the driver was the limit and the run is void.

**Declared ≠ measured.** `--cpus 4.0` is a CFS quota, not four dedicated cores. The manifest must
record what the container actually observed:

```python
os.cpu_count()                                        # often reports HOST cpus, not the quota
len(os.sched_getaffinity(0))                          # affinity, still not the quota
open("/sys/fs/cgroup/cpu.max").read()                 # "400000 100000" ⇒ the real 4.0-core quota
open("/sys/fs/cgroup/memory.max").read()              # the real memory ceiling
```

This matters directly: `torch` and BLAS size their thread pools from `os.cpu_count()`, which under
a CPU quota reports the **host's** 14 rather than the allotted 4 — so a container would spawn 14
threads into a 4-core quota. Given the A3 finding, that is exactly the oversubscription pathology
we just measured. **Both images must therefore pin thread counts explicitly rather than letting the
libraries infer them**, and the manifest records the pinned value.

## 4. The model is baked in, never fetched

**Requirement: no network at runtime, no model download during a measured run.**

* the model is fetched **during build** into the image
* runtime env sets `HF_HUB_OFFLINE=1`, `TRANSFORMERS_OFFLINE=1`
* the image records the model's resolved **revision hash**, and the service reports it in
  `/manifest`
* containers run with `--network` scoped to the benchmark network only (no egress needed)

Rationale beyond reproducibility: a runtime fetch would put a multi-hundred-MB download inside the
first measured window, and it would cross the slow VM filesystem boundary. Baking also means the
model file is in the image layer (fast overlay read), not on a bind mount (slow virtiofs).

**Nothing measured crosses a bind mount.** The corpus is baked in or copied into the container
filesystem at start, before any measurement.

## 5. Network: same mode both sides, and the tax is measured

**Both services get the same network mode.** The candidate topologies:

| topology | note |
| --- | --- |
| **user-defined bridge**, driver + both services on it, addressed by service name | **recommended** — symmetric, isolated, realistic |
| `--network host` | not available in a useful form on macOS; would not be symmetric with the VM's networking |
| published ports to the host | driver would leave the VM and come back — a different and larger tax |

**The bridge tax is a first-class measured number, not an assumption.** Method: a null-work
endpoint (the `probe_minimal` pipeline, and an equivalent `/ping` on the LlamaIndex service) is
measured three ways in the same session:

1. driver and service in the **same container** (loopback, no bridge)
2. driver and service in **different containers on the bridge**
3. native host loopback (the pre-Docker baseline)

The delta between (1) and (2) is the bridge tax; between (2) and (3) is the total container tax.
Both arms must show the **same** tax within tolerance — §6 of `REBASELINE_PLAN.md` defines the
asymmetry test. Given the request path runs at ~1,690 req/s natively, a per-request network cost of
even 0.2 ms would be ~25 % of that arm and cannot be waved away.

## 6. Build hygiene

* **Multi-stage**: builder stage compiles/downloads; runtime stage carries only artifacts. Keeps
  the model and site-packages without the toolchain.
* **Digest-pinned bases**: `FROM python:3.12-slim@sha256:…`. **No `:latest`, no floating tags** —
  a base image that moves silently invalidates cross-day comparisons, and this project already has
  an unexplained between-session drift problem (open item F).
* **Dependencies pinned by hash**: a fully-pinned requirements file with `--require-hashes`.
* **The image digest is recorded in every run manifest** — `docker inspect --format '{{index .RepoDigests 0}}'`. A result whose manifest lacks the digest is not reproducible and does not count.
* **Non-root runtime user**; `--read-only` root filesystem with an explicit `tmpfs` where needed.
* `.dockerignore` excludes `working/results/`, `logs/`, `engine/` tarballs, and `.venv` so the build context
  stays small and cache-stable.

## 7. Docker Desktop VM allocation — required, and how to verify

**This is where a silent failure is most likely.** The VM's allocation caps *everything* inside it.
Two service containers at 8 GB each plus a driver cannot fit in a VM smaller than their sum.

**Required allocation:**

| resource | required | reason |
| --- | --- | --- |
| Memory | **≥ 28 GiB** (32 GiB currently declared) | 2 × 12 GB services + ~4 GiB driver and VM overhead. Fits the declared 32 GiB allocation with margin. **Still DECLARED, not measured** — `docker info` remains the gate |
| CPUs | **≥ 10** | 2 × 4.0 service quotas + driver headroom, on a 14-core host |
| Disk | ≥ 60 GiB | model layers and multi-stage build cache |

**Current state [PARTIALLY VERIFIED]:** the Docker CLI is not on `PATH` and the daemon is not
reachable from this shell, so I could **not** verify the live VM. The stored settings file
(`~/Library/Group Containers/group.com.docker/settings-store.json`) declares `MemoryMiB: 32768`
(32 GiB), which would satisfy the requirement. **That is a declared value, and this project's rule
is that declared ≠ measured** — the earlier observation of an 8.32 GB cap against a 48 GiB host is
exactly the failure mode.

**Verification that the setting actually took effect — run inside the VM, not from the settings UI:**

```bash
docker info --format 'CPUs={{.NCPU}} MemTotal={{.MemTotal}} Arch={{.Architecture}}'
docker run --rm --platform linux/arm64 alpine sh -c 'nproc; free -m; uname -m'
```

`docker info`'s `MemTotal` is the VM's real memory. If it reports ~8.3 GB while the settings file
says 32 GiB, the setting did not apply — restart Docker Desktop and re-check. **Both numbers go
into the run manifest.**

## 8. What I need approved before building

1. The **resource contract** in §3 (4.0 CPUs / 8 GB per service) — these are my proposal, not a
   measured requirement.
2. The **bridge topology** in §5, and that the bridge tax is measured rather than assumed.
3. That **thread counts are explicitly pinned in both images** (§3) rather than inferred — this
   follows from the A3 finding and changes what "default configuration" means for the RocketRide
   arm, which is a comparison-fairness decision, not just a build detail.
4. Confirmation that the VM allocation is genuinely ≥ 24 GiB by `docker info`, not by the settings
   file.

**Nothing is built until these are approved.**
