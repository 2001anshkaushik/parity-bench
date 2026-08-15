# RUN_ON_EC2 — native 200-document smoke, both arms

> ## ⚠️ DECISION CHANGED 2026-08-14 (same day, after writing) — BOTH ARMS RUN IN DOCKER
>
> The team decision is now **both arms in containers on x86-64, not native**. The native plan
> below is **superseded for execution**: do not run §3 (native engine), §6 (native service) or
> §7 as written. What survives unchanged: §0–§2 (preflight, Python 3.12, apt set), §3a's
> onnxruntime patch (applies inside the image build — Leela's and Shashi's Dockerfiles both
> carry it), §4 (corpus), §8 (exfil), §9's traps, and §11.
> **Never mix topologies:** one arm in a container and one native is the exact confound
> documented in `MATCHED_LAYERS.md` — both arms containerized or the run is unpublishable.
> Metric functions are container-agnostic (`working/harness/metrics_shared.py`); the CPU
> sampler is pluggable — psutil tree source natively, Leela's `cgroup_sampler.py` pattern
> in-container (`series_from_cgroup_jsonl`, same downstream math).
> **The Docker sequence that replaces §3/§6/§7 is §12 at the bottom of this file.**

**Ansh · 2026-08-14.** Target: `i-0775f33f3dc16f6af`, c7i.8xlarge, 32 vCPU / 61 GB, Ubuntu, x86-64.
Paste each block, check the stated expectation, move on. **Do not debug on the box** — if a check
fails, §9 has the fix; if §9 does not have it, stop the box and come back to the laptop.

**This supersedes `BUILD_ON_EC2.md` for today.** That file builds Docker images; nothing in it has
ever run, and the RocketRide image has never existed anywhere. This one runs the engine **natively
from the release tarball**, which is the shortest path to a completed smoke. Container build is a
follow-up. Rationale and the two-line dissent test: §10.

### Execution-status key

| mark | meaning |
| --- | --- |
| ✅ | executed successfully somewhere, by us or by a teammate — cited |
| ⚠️ | executed by a teammate on a *different* stack; our variant is untried |
| 🆕 | **never executed anywhere.** Surprises live here |

Running total: **7 of the 24 numbered steps are 🆕.** They cluster in §3 (engine first boot) and
§6 (RocketRide arm at 32 threads on Linux).

---

## 0. Before you start the box — 60 seconds on the laptop ✅

```bash
cd ~/RocketRide/Benchmarking/benchmark-A && git status --short && git push
curl -sI https://github.com/2001anshkaushik/parity-bench | head -1   # 200 = public, 404 = private
```

The box's only inbound channel is `git clone`. **Anything uncommitted does not exist on the box.**
(Leela lost time to exactly this; her `RUN_LOG_20260814` §2.)

**The clone must be HTTPS, not SSH.** Our `origin` is
`git@github.com:2001anshkaushik/parity-bench.git`, and the box has **no SSH keys** — SSM gives an
interactive shell and nothing else. `BUILD_ON_EC2.md` §1 gets this wrong and would fail on the
first command. **The repo is public, so HTTPS needs no token** [VERIFIED — unauthenticated
`curl -sI` returns 200]; the check stays in the runbook because visibility can change.

---

## 1. Start and connect ✅

```bash
export AWS_PROFILE=rocketride AWS_DEFAULT_REGION=us-east-1
aws sso login
aws ec2 start-instances --instance-ids i-0775f33f3dc16f6af
aws ec2 wait instance-running --instance-ids i-0775f33f3dc16f6af
aws ssm start-session --target i-0775f33f3dc16f6af
```

`AWS_PROFILE` is a **laptop-side** setting for these four commands only. **On the box, never set
it** — the box authenticates with its instance role and a stray profile makes every `aws` call
fail with a config error.

### 1a. Keep-alive — start this FIRST, in a second SSM session ⚠️

```bash
nohup sh -c 'while true; do for i in 1 2 3 4 5 6 7 8; do timeout 55 md5sum /dev/zero >/dev/null 2>&1 & done; wait; done' > /dev/null 2>&1 < /dev/null &
```

**Eight cores, not one.** Our `STATE.md` recorded the auto-stop threshold as *1 % CPU for an hour*;
Shashi's runbook, written after the boxes were provisioned, records **< 20 % instance CPU for 60
minutes** — and on 32 vCPU that is **6.4 cores**, with a measured idle floor of 12.7 %. The two
disagree and only one of us can be right. A one-core keep-alive is ~3 % and would **not** save the
box under the 20 % rule, whereas eight cores costs nothing during the long low-CPU stretches
(pip install, corpus download, model download) that are the actual risk. Assume the stricter rule.
**Open item: confirm the real threshold with Dmitrii.** [UNVERIFIED — two conflicting documents,
no measurement]

SSM's shell is `sh`, not bash: `disown` is unavailable, and stdout, stderr **and stdin** must all
be detached or the job suspends with `Stopped (tty output)` looking launched but frozen.

---

## 2. Preflight — every line must pass ⚠️

```bash
uname -m                                  # MUST be x86_64
ldd --version | head -1                   # MUST be >= 2.35
. /etc/os-release && echo "$VERSION_ID"   # 22.04 -> §2a applies; 24.04 -> skip §2a
nproc && free -g | head -2
stat -fc %T /sys/fs/cgroup                # MUST be cgroup2fs
df -h / | tail -1                         # need >= 25 GB free
python3 --version
```

**glibc 2.35 is not a comfortable minimum, it is the exact one.** The engine binary's highest
referenced symbol version is `GLIBC_2.35`, so 22.04 works with **zero** headroom and anything older
(20.04 = 2.31) fails at `ld.so` before `main`. [VERIFIED — DT_NEEDED + `.gnu.version_r` parsed
directly from the linux-x64 `engine` binary on the laptop, cross-checked against a string scan]

### 2a. Python 3.12 — do this before anything else if `VERSION_ID` is 22.04 ⚠️

```bash
sudo apt-get update -qq
sudo apt-get install -y software-properties-common
sudo add-apt-repository -y ppa:deadsnakes/ppa
sudo apt-get update -qq
sudo apt-get install -y python3.12 python3.12-venv
python3.12 --version                      # EXPECT Python 3.12.x
```

**Why this is not optional.** Ubuntu 22.04's system Python is **3.10**, and two pinned
requirements have **no cp310 wheel on PyPI**:

| package | cp310 linux x86_64 wheel | cp312 |
| --- | --- | --- |
| `numpy==2.5.1` | **absent** (sdist only) | present |
| `scikit-learn==1.9.0` | **absent** (sdist only) | present |

On 3.10, `pip install -r requirements.txt` would try to **compile numpy and scikit-learn from
source** — a C/Fortran/Cython toolchain build that takes tens of minutes and usually fails on a
minimal AMI. It fails *late*, after torch has already downloaded. [VERIFIED — PyPI JSON API queried
per package, 2026-08-14; `torch==2.13.0` and `aiohttp` do ship cp310, the other twelve are
`py3-none-any` or sdist-only]

Shashi hit the same wall from the other side — his commit `43be41a` "Fix Linux provisioning: engine
dropped by strip-components + **Python 3.11**".

### 2b. System packages ⚠️

```bash
sudo apt-get install -y libc++1 libc++abi1 libunwind8 lsof curl ca-certificates awscli
```

That is the **complete** hard-dependency set. The engine's real `DT_NEEDED` list is `libc.so.6`,
`ld-linux-x86-64.so.2`, `libm.so.6`, `libgcc_s.so.1`, `libjvm.so`, `libc++.so.1`, `libc++abi.so.1`,
`libunwind.so.1` — the JVM resolves from the bundle's own JRE via
`DT_RUNPATH=$ORIGIN/lib:$ORIGIN/java/jre/lib/server`. `libnuma` and `libcrypto` appear as strings in
the binary but are **not** DT_NEEDED — they are runtime `dlopen` probes and their absence is at
worst a log line. Do not add them. [VERIFIED — DT_NEEDED parsed from the ELF dynamic section, two
methods]

`unzip` is **not needed anywhere**: `fetch_govdocs.py` uses Python's `zipfile`, and the AWS CLI
comes from apt rather than the zip installer. If `apt-get install awscli` has no candidate, use the
no-sudo fallback `working/scripts/install_awscli_userdir.sh` (adopted from Leela's, which has
actually run on a box).

```bash
aws sts get-caller-identity      # EXPECT an assumed-role ARN. Do NOT set AWS_PROFILE.
```

---

## 3. Engine 3.3.1, native ✅ clone · 🆕 everything after

```bash
cd ~ && git clone https://github.com/2001anshkaushik/parity-bench.git && cd parity-bench
git log --oneline -1        # must match what you pushed in §0
mkdir -p engine && cd engine
curl -fsSL -o engine.tar.gz \
  https://github.com/rocketride-org/rocketride-server/releases/download/server-v3.3.1/rocketride-server-v3.3.1-linux-x64.tar.gz
echo "d8dad45bd084c65443ddb5907965ee1c8424f82fa5dcd5b11476ed66ce0281d8  engine.tar.gz" | sha256sum -c -
tar -xzf engine.tar.gz            # FLAT — never --strip-components
rm engine.tar.gz && chmod +x engine
echo "95768e2640df2d34dd6dfea2e456f36da03ad80b091f9d057c116dfe748d9747  engine" | sha256sum -c -
ls                                # EXPECT: ai engine include java lib nodes pip rocketride static
cd ..
```

Both hashes are **VERIFIED**, and by two independent parties: the tarball digest matches the pin in
our own `BUILD_ON_EC2.md`, and the extracted-binary digest matches the `ENGINE_SHA256` in Leela's
`rocketride/Dockerfile`, which she derived from her own download on a different machine. They
describe **different objects** — tarball vs extracted binary — so quote them with that label
attached or the next person will think one of them is wrong.

### 3a. 🆕 THE FIRST-BOOT BLOCKER — patch before you ever start the engine

```bash
grep -rl "onnxruntime-gpu==1.20.1" engine --include="*.txt" | tee /tmp/onnx_patched.txt | wc -l
#   EXPECT 5
grep -rl "onnxruntime-gpu==1.20.1" engine --include="*.txt" \
  | xargs sed -i "s/onnxruntime-gpu==1.20.1/onnxruntime-gpu==1.20.2/"
! grep -rq "onnxruntime-gpu==1.20.1" engine --include="*.txt" && echo "PATCH OK"
```

**Engine 3.3.1 cannot cold-boot on Linux unpatched.** It pins `onnxruntime-gpu==1.20.1`, which was
removed from PyPI; `depends.py` concatenates *every* requirements file and compiles one global
constraints set all-or-nothing, so the daemon dies before serving even though the measured path
never imports onnxruntime. Shashi found and filed this
(`ENGINE-ISSUE-3.3.1-onnxruntime-pin-2026-08-13.md`).

Two things I checked rather than inherited:

* **PyPI, queried today:** `onnxruntime-gpu` 1.20.0 and 1.20.2 are served, **1.20.1 is absent**
  (9 files on 1.20.2). The workaround target exists. [VERIFIED]
* **The pin is in five files, not three.** Shashi's write-up names `nodes/anonymize`,
  `nodes/audio_transcribe` and `ai/common/models/vision/requirements_pose.txt`; the tarball also
  carries it in `ai/common/models/gliner/requirements_gliner.txt` and
  `ai/common/models/audio/requirements_whisper.txt`. `REQUIREMENTS_GLOBS` is
  `['requirement*.txt', 'nodes/**/requirement*.txt', 'ai/**/requirement*.txt']`, recursive — so all
  five are compiled and all five must be patched. **His Dockerfile is fine** (it greps recursively
  and catches all five); only the prose undercounts. The `tee` above exists so you can prove the
  count was 5 rather than 3. [VERIFIED — grep over the extracted tarball]

### 3b. 🆕 Custom nodes — copy now, before first boot

```bash
cp -R working/nodes/* engine/nodes/
ls engine/nodes | head
```

Order matters. `depends.py` keys its dependency cache on **file mtime + size** across the same
globs, so copying nodes after a successful boot invalidates the cache and pays the whole
constraints compile again. Our probe nodes carry **no** `requirements*.txt`, so they add no new
pins and cannot reintroduce a resolution failure. [VERIFIED — `find working/nodes -name
'requirement*'` is empty]

The 200-doc smoke itself uses only stock nodes (`product_pdf.pipe` is
webhook → parse → preprocessor_langchain → embedding_transformer → response_documents); the copy is
for `setup_probe.py`.

### 3c. 🆕 First boot — the highest-uncertainty moment in this document

```bash
bash working/scripts/start_engine.sh
```

Expect **10–30 minutes** and near-zero CPU: the engine bootstraps its embedded Python (pip, uv,
constraint compile, wheel installs) before it binds. `start_engine.sh` already handles this — a
900 s default deadline, a progress line every 30 s, and it distinguishes "still bootstrapping" from
"process exited". It also avoids the `curl -w '%{http_code}' || echo 000` trap that makes a dead
server report healthy. Raise the deadline if needed:

```bash
RR_START_TIMEOUT=2400 bash working/scripts/start_engine.sh
curl -s http://127.0.0.1:5565/version
#   EXPECT {"status":"OK","data":{"version":"3.3.1.35","hash":"a0817cc6",...}}
```

**This whole low-CPU stretch is prime auto-stop territory.** §1a must already be running.

---

## 4. Corpus — 200 documents ✅ fetcher · ⚠️ on Linux

```bash
../.venv/bin/python working/scripts/fetch_govdocs.py 200
../.venv/bin/python working/scripts/verify_corpus_manifest.py --subset
#   EXPECT: files on disk 200 / extra 0 / changed 0 / verified 200/10000 / VERDICT: MATCH
```

(Create the venv first if you have not — §5.)

**200 documents is exactly govdocs1 zip `000`.** The archive contributes precisely 200 PDFs, so
`fetch_govdocs.py 200` pulls one ~350 MB zip and stops on a natural boundary. Under the same
`sorted(*.pdf)[:N]` rule Leela's box uses, the first ten are
`000009, 000010, 000011, 000012, 000013, 000015, 000016, 000018, 000019, 000020` — **name-for-name
what her box selected** (her `RUN_LOG_20260814` §3). One archive, one rule, same documents.
[VERIFIED — null control: `sorted(*.pdf)[:200]` and `sorted(000_*.pdf)[:200]` return identical
lists, and all 200 match the committed sha256 manifest]

`--subset` is the same gate scoped to the files present: changed and extra still hard-fail, and an
empty directory is refused rather than passing vacuously. It does **not** check completeness — the
10,000-document run must use the default mode.

Kick the rest off in the background for the follow-up run, once the smoke is safely underway:

```bash
nohup ../.venv/bin/python working/scripts/fetch_govdocs.py 10000 > ~/corpus.log 2>&1 < /dev/null &
```

---

## 5. Python environment ⚠️

```bash
cd ~ && python3.12 -m venv .venv
./.venv/bin/pip install -q --upgrade pip
./.venv/bin/pip install torch==2.13.0 --index-url https://download.pytorch.org/whl/cpu
./.venv/bin/pip install -r parity-bench/requirements.txt
cd parity-bench && ../.venv/bin/python working/scripts/regression_selftest.py
#   EXPECT: 12 passed, 0 failed, 1 xfail (nul_truncation)
```

The venv lives **one level above** the clone — `run_service.sh` resolves `$ROOT/../../.venv` and
dies with "interpreter not found" otherwise.

**Install torch from the CPU index first, deliberately.** The default PyPI `torch` wheel drags in
the full nvidia CUDA stack — several GB and several minutes on a box with no GPU. `2.13.0+cpu`
cp312 manylinux x86_64 exists on that index and satisfies the `==2.13.0` pin (PEP 440 ignores the
local segment). Installing it first means the requirements pass finds torch already satisfied.
[VERIFIED — index listing fetched 2026-08-14] **Record this as a deviation** in the run notes: it
is a different wheel from the one every macOS number came from. That comparison was already void
across arm64→x86-64, but say so rather than let a reader assume.

---

## 6. The LlamaIndex arm ⚠️ pattern · 🆕 at 32 workers

```bash
cd ~/parity-bench
WS1_DEVICE=cpu WS1_WORKERS=32 bash working/ws1/run_service.sh > logs/ws1.out 2>&1 &
until [ "$(grep -c 'warm in' logs/ws1.out)" -ge 32 ]; do sleep 3; done; echo "32 workers warm"
```

**Gate on the `warm in` line count, never on `/health`.** `/health` is answered by whichever single
worker the kernel hands the connection to, so it returns 200 while 31 workers are still loading
models. The line count is the only honest readiness signal. `ws1_service.wait_warm()` does the same
thing properly (distinct worker PIDs), and that is what the smoke uses internally.

First run downloads `multi-qa-MiniLM-L6-cos-v1`; after that `HF_HOME` is warm.

**Memory:** ~580 MB/worker measured × 32 ≈ 18.6 GB, against 61 GB. Fits, but it is the largest
single allocation of the day — watch it the first time.

**Why 32.** Shashi's harness pins `RR_THREADS == HS_WORKERS` on both arms as the answer to the
recorded exec objection that "our throughput edge came partly from more worker threads"
(`SHARED-PIPELINE-NOTES` §7). 32 = host cores. Leela's arms are capped at 12 CPU by a compose
envelope she has already flagged in her own run log as Mac-tuned and due for recomputation, so hers
is the number in motion, not the one to copy.

---

## 7. The 200-document smoke — both arms, five gates 🆕 at this scale

```bash
cd ~/parity-bench
export RR_NODE_MARK='engine/ai/node.py'          # the clone is not named benchmark-A
SMOKE_WORKERS=32 SMOKE_THREADS=1 SMOKE_BLAST_C=32 SMOKE_CORPUS_GLOB='000_*.pdf' \
  ../.venv/bin/python working/scripts/setup_probe.py
#   EXPECT exit 0: env manifest, in-process thread parity, 10-doc pass, determinism re-run

SMOKE_WORKERS=32 SMOKE_THREADS=1 SMOKE_BLAST_C=32 SMOKE_CORPUS_GLOB='000_*.pdf' \
  ../.venv/bin/python working/scripts/smoke50_parser_in.py 200 2>&1 | tee logs/smoke200.log
```

`SMOKE_THREADS=1` pins OMP/MKL/OpenBLAS/VECLIB per worker. With 32 worker processes, letting each
start one BLAS thread per core is ~1,000 threads and measures thread thrash. Both Shashi
(`OMP_NUM_THREADS` pinned both sides) and Leela (`TORCH_THREADS=1`) pin it to 1. The script
**reads back** what each worker actually got and prints it — declared ≠ measured is how a
10,000-document comparison once ran 1-thread against 10-thread undetected.

**`SMOKE_THREADS` does not reach torch's inter-op pool, and that is deliberate.** The read-back line
prints `torch(intra,interop)` — locally `[(10, 14)]`, on the box expect `[(1, 32)]`. Leela pins both
(`TORCH_THREADS=1`, `TORCH_INTEROP_THREADS=1`); we do not, because our own **VERIFIED** result is
that pinning inter-op is *harmful* — −14.3 % at concurrency 8 (`anchor_b_interop.json`). Today's
smoke takes no throughput number, so it does not bite. **Record the difference; do not "fix" it** —
changing it would contradict a result we have already published.

The verdict table prints per arm:

```
llamaindex_http_pdf / rocketride_pdf
  LEELA  census      offered 200 = successful N + expected N + unexpected N   -> PASS/FAIL
  LEELA  structure   N failure(s)                                             -> PASS/FAIL
  LEELA  determinism N drifted                                                -> PASS/FAIL
  OURS   independent-reference hash: N FAIL
  OURS   content-suspect documents : N
CROSS-ARM (reported, NOT gated)
  chunk-count delta (RR - LI) / char ratio (RR / LI)
```

Plus, new today and needed for cross-site comparison, a header carrying `pipe sha256 raw` +
`canonical`, and the ordered corpus digest. The result JSON lands in `working/results/` with a
`pipeline` / `corpus` / `pinned` provenance block matching the keys Shashi exports.

**Expect chunk duplication to show up.** `BUG_CHUNK_DUPLICATION` fires above ~239.8k extracted
chars, 5.34 % of the full corpus. Census, structure and determinism all **pass** on a doubled
document — only the independent-reference gate catches it. A non-zero `independent-reference` count
is the known bug, not a broken run.

---

## 8. Ship the results ✅ contract · 🆕 our script

```bash
bash working/scripts/exfil_s3.sh working/results logs/smoke200.log logs/ws1.out logs/engine.log
#   -> s3://rocketride-benchmark-data/ansh/<UTC stamp>/
```

Raw records go up, not just the verdict — every metric must stay re-derivable, and a report alone
cannot be recomputed or re-gated (Leela's checklist 4.2). The script proves the role works *before*
copying, then prints S3's own object count and byte total as the completeness check.

Then, from the laptop, close the loop the way Leela did — download and re-derive:

```bash
aws s3 cp s3://rocketride-benchmark-data/ansh/<stamp>/ ./run --recursive --profile rocketride
```

### 8a. Stop the box ✅

```bash
aws ec2 stop-instances --instance-ids i-0775f33f3dc16f6af --region us-east-1
```

Do not rely on auto-stop. Budget was at 93 % with ~$130 left for the month when the three boxes
landed; left running they are $3,127/month each.

---

## 9. What will go wrong, and the fix

Ordered by expected cost. The Linux-vs-macOS column is the one to read twice: **loud** failures are
cheap, **silent** ones corrupt results.

| # | Failure | Loud or silent | Fix |
| --- | --- | --- | --- |
| 1 | Engine exits during first boot, `Failed to compile constraints` | **loud** | §3a, and confirm the patch count was **5**. This is the single most likely blocker. |
| 2 | `pip` tries to build numpy/scikit-learn from source, dies after torch downloaded | **loud, late** | §2a — you are on Python 3.10. Nothing else fixes it. |
| 3 | Box auto-stops mid-run | **loud, expensive** | §1a with **eight** cores. Threshold is disputed; assume 20 %. |
| 4 | `ws://127.0.0.1:5565` refuses the WebSocket upgrade | **loud** | Leela hit this through Docker's port proxy. Native has no proxy, so it should not occur — if it does, do not debug it, run the driver with the engine's own interpreter. |
| 5 | `run_service.sh` exits 127, "interpreter not found" | **loud** | venv must be at `~/.venv`, one level above the clone (§5). |
| 6 | Service looks ready, 31 workers still loading | **SILENT — biases the first block** | Gate on `grep -c 'warm in' >= 32`. Never `/health`. |
| 7 | `curl -w '%{http_code}' \|\| echo 000` reports a dead engine healthy | **SILENT** | Already fixed in `start_engine.sh`; do not hand-roll a health check. |
| 8 | Second engine on an occupied port; the benchmark measures whichever answered | **SILENT** | `start_engine.sh` is idempotent and refuses. Do not launch `./engine` by hand. |
| 9 | `RR_NODE_MARK` unset → engine-node matching returns 0 and a gate passes vacuously | **loud** (`node_mark_fails_loudly` covers it) | `export RR_NODE_MARK='engine/ai/node.py'` — the clone is not named `benchmark-A`. |
| 10 | Nodes copied *after* first boot → full constraints recompile | slow, not wrong | §3b ordering. |
| 11 | `--strip-components` on the tarball → engine binary vanishes | **loud** | Extract flat. Shashi's `43be41a` is this exact bug. |
| 12 | Memory gate logic inherited from macOS | **SILENT** | macOS compression does not exist on Linux; that invalidation reason is gone and the cgroups v2 `memory.stat` path replaces it. **No memory number is in today's smoke** — do not let one in. |
| 13 | `setrlimit(RLIMIT_NPROC)` behaves differently | silent on macOS, fine here | The permanent-clamp trap was macOS-only. Not a Linux risk. |
| 14 | `lsof` absent → all PID-by-socket resolution fails | **loud** | Installed in §2b. |
| 15 | Backgrounded job freezes as `Stopped (tty output)` | looks launched, is frozen | Detach all three streams: `> log 2>&1 < /dev/null &`. |
| 16 | Embeddings differ in low bits vs macOS | **SILENT if unexamined** | Expected — different BLAS. **Chunk hashes must still match**; that is the cross-site check. Leela's nine shared documents produced byte-identical chunk hashes across native x86 and emulated ARM. |

---

## 10. Native rather than Docker — the two lines, and the dissent

Native. The RocketRide image has never existed on our side, a first x86-64 build is unbounded work,
and the tarball's only external needs are three apt packages that resolve on a stock 22.04.

The honest counter-argument, since it got stronger while I was checking: **Leela now has a working
RocketRide Dockerfile** (`rocketride/Dockerfile`, engine 3.3.1, pinned to the same binary digest we
verified), and Shashi's `engine.Dockerfile` carries the onnxruntime patch already. So "no image
exists anywhere" is no longer true — it is only true of *ours*. If today's native run stalls in §3,
pulling Leela's Dockerfile is a better second move than debugging our own. It is not the first move
because it adds a 20–30 minute image build plus a container networking surface — including the
WebSocket-upgrade-through-the-port-proxy failure she already hit — in front of a run that is
supposed to finish today.

---

## 11. Known non-comparabilities — record them, do not fix them today

* **Shashi's corpus is arXiv, ours and Leela's is GovDocs1.** 24 sha256-pinned arXiv cs.LG PDFs,
  hardlink-replicated up to N. Not a variant of the same corpus — a different one, and replication
  means his "10,000 documents" is 24 unique files seen ~417 times each, with page-cache and parser
  behaviour to match. **His docs/s and ours cannot be put in one table.** Escalate; do not paper
  over it.
* **The raw pipe hashes disagree three ways and it is a false alarm.** All three files are
  byte-identical apart from `project_id` and whitespace. Canonical digest (key-sorted, `project_id`
  stripped) is `f61165f7cf7ab1db…` on all three. Propose the canonical hash as the gate.
* **Warm-up is unsettled**: Leela 25, Shashi `max(4, 2 × threads)` = 64 at 32 threads, ours
  PROVISIONAL at 100. Today's smoke takes no throughput number, so it does not bite — but nothing
  timed can be published until it is one value.
* **Send mode**: Shashi measures blast *and* sequential; Leela measures sequential closed-loop and
  has just added blast; our smoke measures sequential and uses blast only to drive determinism.

---

## 12. DOCKER SEQUENCE — replaces §3, §6 and §7 🆕

Both arms in containers, `--network host`, identical CPU/memory envelope, identical thread pins.
Never one arm native and one containerised: `MATCHED_LAYERS.md` documents that exact confound
producing two opposite memory verdicts.

**Thread decision (settled 2026-08-15):** 32 workers × **1 BLAS thread** each on both arms;
`TORCH_INTEROP_THREADS` left **unset** on both. Matches Shashi (`compose.yml:37-39,63-65,90`) and
Leela (`docker-compose.yml:71`). Both teammates already run BLAS=1 — this adopts their setting.

### 12a. Build (§2a Python-3.12 preflight still applies to the host venv)

```bash
docker build -f docker/Dockerfile.rocketride --build-arg EXPECT_ARCH=x86_64 -t rr-engine:3.3.1 .
docker build -f docker/Dockerfile.llamaindex --build-arg EXPECT_ARCH=x86_64 -t ws1-llamaindex:x86_64 .
```

`Dockerfile.llamaindex` serves `ws1.service:app` on `0.0.0.0:8801`. Its `ENTRYPOINT` used to be
`ladder.py`, which calls the pipeline **in-process** — no server, no socket. That would have
reintroduced the topology confound, and its arch assert refuses x86-64 besides. `ladder.py` is
still in the image and is simply not used.

### 12b. Start both arms

```bash
docker run -d --name rr --network host --cpus 32 --memory 58g \
  -e RR_HOST=127.0.0.1 -e RR_PORT=5565 \
  -e OMP_NUM_THREADS=1 -e MKL_NUM_THREADS=1 -e OPENBLAS_NUM_THREADS=1 \
  -e VECLIB_MAXIMUM_THREADS=1 -e NUMEXPR_NUM_THREADS=1 -e TORCH_NUM_THREADS=1 \
  rr-engine:3.3.1

docker run -d --name li --network host --cpus 32 --memory 58g \
  -e WS1_WORKERS=32 -e WS1_PORT=8801 -e WS1_DEVICE=cpu \
  -e OMP_NUM_THREADS=1 -e MKL_NUM_THREADS=1 -e OPENBLAS_NUM_THREADS=1 \
  -e VECLIB_MAXIMUM_THREADS=1 -e NUMEXPR_NUM_THREADS=1 -e TORCH_NUM_THREADS=1 \
  ws1-llamaindex:x86_64
```

`--network host` means no published ports, so Leela's WebSocket-through-the-port-proxy question
(`CONTEXT_SNAPSHOT` 4.6, which her `a33c75b` suggests was a missing `--host` flag) cannot arise.
First engine boot is 10–30 min at near-zero CPU — §1a's keep-alive must already be running.

```bash
curl -s http://127.0.0.1:5565/version     # EXPECT version 3.3.1.35, hash a0817cc6
```

### 12c. Corpus — fetch it before the preflight

```bash
../.venv/bin/python working/scripts/fetch_govdocs.py 200          # = govdocs1 zip 000 exactly
../.venv/bin/python working/scripts/verify_corpus_manifest.py --subset
```

Network-bound (~350 MB), so start it while the images build. It is listed before the preflight
because the smoke driver validates the corpus first and exits 2 on a short one.

**The preflight itself no longer needs a corpus** — it sends no documents — so if you want the
thread gate answered before the download finishes, run 12d now and come back. Earlier revisions
of this file sequenced the gate first and the driver exited 2 if you followed it.

### 12d. Copy `env_probe` into the engine container — required before the preflight

The RocketRide thread read-back runs our `env_probe` node. The container ships **stock nodes
only**, so without this the probe fails with
`RuntimeError: Component work references a provider with no registered service definition`.

```bash
docker cp working/nodes/env_probe rr:/opt/rocketride/engine/nodes/
docker restart rr
until curl -sf http://127.0.0.1:5565/version >/dev/null; do sleep 3; done
curl -s http://127.0.0.1:5565/version      # EXPECT 3.3.1.35
```

**This does not modify the image** — `docker cp` writes to the container's writable layer. It is
also lost on `docker rm`, so re-copy after recreating the container.

**The restart does NOT re-pay the constraints compile.** `depends.py:708-748` keys the cache on
`_compute_hash(_find_requirement_files())`, and `_find_requirement_files()` globs only
`requirement*.txt`, `nodes/**/requirement*.txt`, `ai/**/requirement*.txt`. **`env_probe` contains
no requirements file at all** (`find working/nodes -name 'requirement*'` → 0), so the file set,
sizes and mtimes are unchanged, `current_hash == stored_hash`, and `ensure_constraints()` returns
at *"Constraints are up to date"*. Restart is seconds, not the 10–30 minute first boot.

⚠️ **Only `env_probe`, and only for the probe.** The measured pipe is five stock providers
(`webhook`, `parse`, `preprocessor_langchain`, `embedding_transformer`, `response_documents`) —
canonical digest `f61165f7cf7ab1db…`, unchanged. Do not copy the other five custom nodes; they are
not on the measured path and every one added is another `nodes/**` directory the engine scans.

### 12e. PREFLIGHT — prove thread propagation BEFORE any measured run

```bash
SMOKE_EXTERNAL=1 SMOKE_PREFLIGHT=1 SMOKE_WORKERS=32 SMOKE_THREADS=1 SMOKE_PORT=8801 \
RR_NODE_MARK='engine/ai/node.py' \
  ../.venv/bin/python working/scripts/smoke50_parser_in.py
```

Prints `pinned.torch_threads_measured` for both arms and exits **0 = PASS / 4 = FAIL**. It sends
no documents. Read-back is in-process on both sides: LlamaIndex from `/health` on each live
uvicorn worker, RocketRide from the `env_probe` node inside the engine's **task** process on a
separate one-shot pipe, so the shared 5-node measured pipe stays byte-identical.

**This gate exists because of a measured failure, not caution.** On the macOS native engine the
task process inherited **none** of the six thread variables and torch chose 10 intra / 14 interop
on its own. `docker run -e` reaching the container does not prove it reached the worker, and torch
caches its thread count at import, so a variable set after import has no effect at all. If either
arm reports anything other than intra=1, **stop** — cost numbers from mismatched arms are not
comparable, and nothing downstream would say so.

### 12f. The 200-document smoke

```bash
SMOKE_EXTERNAL=1 SMOKE_WORKERS=32 SMOKE_THREADS=1 SMOKE_BLAST_C=32 \
SMOKE_CORPUS_GLOB='000_*.pdf' SMOKE_PORT=8801 SMOKE_WARM_N=64 \
RR_NODE_MARK='engine/ai/node.py' \
  ../.venv/bin/python working/scripts/smoke50_parser_in.py 200 2>&1 | tee logs/smoke200.log
```

`SMOKE_EXTERNAL=1` is what stops the driver starting its own service. Without it the driver would
launch a second LlamaIndex on 8801 and the run would measure whichever process won the port —
the `start_engine.sh` idempotency trap in a new place. In external mode an unreachable arm is a
hard failure with a named reason, never a silent fallback.

### 12g. Tika reference — the engine tarball must also be on the HOST

The independent-reference check shells out to the engine's OWN Tika, from
`engine/java/jre/bin/java` + `engine/java/lib` + `engine/java/tika-config.xml`. In Docker mode
nothing extracts the tarball on the host, so those paths do not exist and the check silently did
not run. Extract it host-side (§3 of the native plan, extract only — do not start it):

```bash
mkdir -p engine && cd engine
curl -fsSL -o engine.tar.gz \
  https://github.com/rocketride-org/rocketride-server/releases/download/server-v3.3.1/rocketride-server-v3.3.1-linux-x64.tar.gz
echo "d8dad45bd084c65443ddb5907965ee1c8424f82fa5dcd5b11476ed66ce0281d8  engine.tar.gz" | sha256sum -c -
tar -xzf engine.tar.gz && rm engine.tar.gz && cd ..
ls engine/java/jre/bin/java engine/java/tika-config.xml working/tika/TikaExtract.class
```

`TikaExtract.class` is committed, so extraction is the only missing piece — the bundle ships a
JRE with no `javac`, so nothing needs compiling on the box. Same tarball as the container, so the
reference is the engine's own Tika 3.2.3 with the engine's own config.

Set `SMOKE_REQUIRE_TIKA=1` to make a missing reference fatal instead of reported.

### 12h. Ship it

```bash
bash working/scripts/exfil_s3.sh working/results logs/smoke200.log
docker logs rr > logs/engine.log 2>&1; docker logs li > logs/ws1.log 2>&1
bash working/scripts/exfil_s3.sh logs/engine.log logs/ws1.log
docker rm -f rr li
aws ec2 stop-instances --instance-ids i-0775f33f3dc16f6af --region us-east-1
```
