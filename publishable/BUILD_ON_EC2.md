# BUILD_ON_EC2 — first contact is executing a plan, not debugging one

**Ansh · 2026-08-14.** Target: Ubuntu 22.04 x86-64, ≥32 vCPU, 64 GB, gp3, Docker + cgroups v2
(the amended spec). Every step is copy-paste; each has a check that must pass before the next.
**Nothing below has run on x86-64 — that is the point of this file.** What cannot be verified
without the box is listed at the end, honestly.

## 0. Preflight (5 min)

```bash
uname -m                          # MUST print x86_64
ldd --version | head -1           # glibc MUST be >= 2.35 (22.04 ships 2.35)
stat -fc %T /sys/fs/cgroup        # MUST print cgroup2fs
docker info --format '{{.Architecture}} {{.MemTotal}}'   # x86_64, >= ~63e9
free -h | grep -i swap            # swap SHOULD be 0 (we asked for it disabled)
which lsof || sudo apt-get install -y lsof   # HARD dep: all PID resolution is by listening socket
```
Any failure here → stop and fix the box, not the plan.

## 1. Repo + venv (10 min)

```bash
git clone git@github.com:2001anshkaushik/parity-bench.git && cd parity-bench
cd .. && python3.12 -m venv .venv && ./.venv/bin/pip install -r parity-bench/requirements.txt
cd parity-bench && ../.venv/bin/python working/scripts/regression_selftest.py
# EXPECT: 12 passed, 1 xfail. Engine-dependent tests SKIP (engine not up yet) — that is correct.
```

## 2. Corpus (network-bound; start it early, it can run during step 3)

```bash
../.venv/bin/python working/scripts/fetch_govdocs.py 10000    # zips 000..040, ~5.9 GB
# verify against the committed manifest — this is the per-file sha256 gate:
../.venv/bin/python working/scripts/verify_corpus_manifest.py
# EXPECT: 10000/10000 sha256 match, 0 missing, 0 extra
```

## 3. Build both images (30–45 min, mostly torch download)

```bash
docker build -f docker/Dockerfile.rocketride --build-arg EXPECT_ARCH=x86_64 \
    -t rr-engine:3.3.1-x64 .
docker build -f docker/Dockerfile.llamaindex --build-arg EXPECT_ARCH=x86_64 \
    -t ws1-llamaindex:x64 .
```
Both Dockerfiles hard-fail on the wrong arch — an assert firing means the build host is not what
step 0 said. The engine tarball is fetched **pinned by sha256**
(`d8dad45b…ce0281d8`); a mismatch means the release asset changed and everything stops.

## 4. First engine boot — the highest-uncertainty moment

```bash
docker run -d --name rr --cpus 12 --memory 10g -p 5565:5565 rr-engine:3.3.1-x64
sleep 60 && curl -s http://127.0.0.1:5565/version
# EXPECT: {"status":"OK","data":{"version":"3.3.1.35","hash":"a0817cc6",...}}
docker exec rr ./engine/java/jre/bin/java -version   # Temurin 17.0.19 from the BUNDLE, not apt
```
**Known landmine (Leela §4.6):** the engine rejects WebSocket upgrades through Docker's port
proxy — `ws://localhost:5565` from the host may fail while in-container works. If it does, run
drivers inside the container (her pattern) or with `--network host`; do not burn time on the proxy.

## 5. Gates before any number

```bash
export RR_NODE_MARK='engine/ai/node.py'         # clone is not named benchmark-A
../.venv/bin/python working/scripts/setup_probe.py       # env manifest incl. engine binary sha256,
                                                         # in-process thread parity, 10-doc pass,
                                                         # determinism re-run. MUST exit 0.
../.venv/bin/python working/scripts/smoke50_parser_in.py 50
# EXPECT: census closes both arms, structure 0 fail, determinism 50/50,
#         independent-reference and content-sanity columns reported
```

## 6. Only then: re-baseline

Warm-up re-measurement (the 100-doc figure is PROVISIONAL from one macOS fixture) → pool-width
re-measurement (17.24 is a macOS number; the 32-ladder depends on it) → matched-layer primary →
sweep. In that order; each gates the next.

## CANNOT be verified without the box — the honest list

| item | why local verification is impossible |
| --- | --- |
| the engine binary **runs at all** on x86-64 | zero linux-arm64 assets; never executed by us anywhere |
| `Dockerfile.rocketride` end-to-end | FROM ubuntu:22.04 amd64; arch assert correctly refuses to build here |
| embedded-interpreter pypdf step | layout check needs the extracted linux bundle running |
| glibc/libc++ resolution at load | ELF analysis says 2.35 + libc++1/libc++abi1/libunwind8 suffice; only `ld.so` proves it |
| x86-64 numeric behaviour (chunk hashes should be identical; embeddings may differ in low bits across BLAS) | needs the box; the determinism gate + cross-site chunk-hash comparison will answer it in step 5 |
| WS-through-docker-proxy behaviour | Leela observed it on her stack; ours untested |
| cgroups v2 memory accounting path | replaces the macOS compressor gate; Linux-only |
