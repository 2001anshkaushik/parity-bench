# benchmark-A — Pinned Environment

Every run manifest references this file. If anything here changes, prior results are not
comparable and must be re-run or explicitly annotated.

Captured: 2026-08-04 · machine-readable copy: `working/results/engine_gate.json`

---

## Engine (pinned)

| Field | Value |
| --- | --- |
| Release tag | `server-v3.3.1` |
| Published | 2026-07-07 |
| Version reported by running process | **3.3.1.35** |
| Build hash | `a0817cc6` |
| Build stamp | `2026-07-07T04:45:25Z` |
| Platform asset | `darwin-arm64` |
| Tarball URL | `https://github.com/rocketride-org/rocketride-server/releases/download/server-v3.3.1/rocketride-server-v3.3.1-darwin-arm64.tar.gz` |
| **SHA256** | `846df27ae8b52cd3ed4975124f76462f0cac3ba2e1677a012508247efde6a836` |
| Download size | 179,915,223 bytes (171.6 MiB) |
| Install path | `benchmark-A/engine/` |
| Binary architecture | `Mach-O 64-bit executable arm64` (verified with `file`, not assumed) |
| Licence | MIT (Aparavi Software AG) |

Re-verify the artifact at any time:

```bash
shasum -a 256 /tmp/rr-3.3.1.tar.gz
```

### Archive layout note

The tarball extracts **flat** — `engine`, `ai/`, `working/nodes/`, `lib/`, `static/` are all at the
archive root, with no wrapping directory. Krish's `provision.sh` passes
`tar --strip-components=1`, which is correct for a differently-shaped archive but would destroy
this one (it would strip `ai/`, `working/nodes/` etc. and scatter their contents). We extract with no
`--strip-components`.

## Version resolution — evidence, not assumption

All releases carrying a `darwin-arm64` asset:

| Tag | Published | Prerelease | Bundled client |
| --- | --- | --- | --- |
| `server-v3.3.0-prerelease` | 2026-08-04 | **yes** | — |
| `server-v3.3.0-hackathon` | 2026-08-03 | **yes** | — |
| **`server-v3.3.1`** | **2026-07-07** | no | **1.3.0** |
| `server-v3.3.0` | 2026-07-07 | no | 1.3.0 |
| `server-v3.2.2` | 2026-06-11 | no | 1.2.0 |
| `server-v3.2.1` | 2026-05-29 | no | 1.1.1 |
| `server-v3.2.0` | 2026-05-22 | no | 1.1.0 |
| `server-v3.1.2` | 2026-03-29 | no | — |
| `server-v3.1.0` | 2026-03-05 | no | — |
| `server-v1.0.3` / `v1.0.2` | 2026-02-26 | no | — |

**Choice: `server-v3.3.1`.** Newest *stable* darwin-arm64 release, and its manifest bundles
client `rocketride-1.3.0.tgz` — exactly the SDK version we standardised on.

Two dated-later tags were rejected: `3.3.0-prerelease` (2026-08-04) and `3.3.0-hackathon`
(2026-08-03) are both flagged prerelease on GitHub and carry a *lower* version number than 3.3.1
despite later dates. Publishing benchmark results measured on a prerelease build would not be
defensible.

### SDK compatibility verdict — VERIFIED (by co-release pairing)

Server releases bundle a client tarball, giving a direct pairing: 3.2.0→1.1.0, 3.2.1→1.1.1,
3.2.2→1.2.0, 3.3.0→1.3.0, **3.3.1→1.3.0**. The Python and TypeScript clients are versioned in
lockstep in the monorepo — `packages/client-python/pyproject.toml` and
`packages/client-typescript/package.json` both read `1.3.0` — so the manifest's TypeScript
evidence carries to the Python SDK.

**Mechanism caveat (UNVERIFIED):** the SDK contains no `min_server_version`, no protocol-version
constant, and no compatibility handshake. Nothing *enforces* the pairing at runtime; a mismatched
pair would fail late and unclearly rather than refusing to connect. Compatibility here is
established by co-release evidence, not by a guarantee.

### Consequence for the team's existing repos

- Krish pins engine **3.2.1** but `rocketride==1.2.0` in `requirements.txt`. Per the table, 3.2.1
  ships client 1.1.1 and 1.2.0 belongs with 3.2.2 — that repo is already running a mismatched
  pair.
- Leela measured against a **source build** (commit `1ec7454`) reporting 3.3.0, not a release
  tarball, so those results are not reproducible from any published artifact.

## Host

| Field | Value |
| --- | --- |
| Machine | Apple M4 Pro |
| Logical CPUs | 14 (10 performance + 4 efficiency) |
| RAM | 51,539,607,552 bytes (48.0 GiB) |
| macOS | 26.6 (build 25G72) |
| Darwin | 25.6.0 |
| Architecture | arm64 (native, no Rosetta) |
| **Power source** | **AC** |
| Python (benchmark venv) | 3.12.13 |
| `ulimit -n` soft, **measured inside Python** | **1,048,576** |
| `ulimit -n` hard, measured inside Python | 9,223,372,036,854,775,807 (unlimited) |
| `RLIMIT_NPROC` (soft, hard) | 8,000 / 12,000 |

The fd limit is read with `resource.getrlimit()` from inside the benchmark interpreter, not from
the shell — the shell's limit is not necessarily inherited, and at 10k concurrency an fd ceiling
produces failures indistinguishable from a framework defect.

**`RLIMIT_NPROC` = 8,000 is the real ceiling to watch here**, not fds. A process-per-task engine
or an over-sized process pool will hit it well before the fd limit, and the resulting failure
would be a host limit misread as a framework limit.

Power source is recorded because Apple Silicon changes CPU frequency policy on battery; a run on
battery is not comparable to one on mains.

## Runtime configuration

| Setting | Value |
| --- | --- |
| Bind address | `127.0.0.1:5565` — loopback only, never `0.0.0.0` |
| `ROCKETRIDE_URI` | `http://127.0.0.1:5565` |
| `ROCKETRIDE_APIKEY` | `MYAPIKEY` (engine's built-in dev key) |
| Log | `benchmark-A/logs/engine.log` |
| Pidfile | `benchmark-A/logs/engine.pid` |
| Cold start (first launch) | ~1 min — bootstraps the embedded Python (pip, wheel, setuptools, uv, constraint compilation) before binding |
| Warm start | ~1 s |

```bash
bash working/scripts/start_engine.sh && ../.venv/bin/python working/scripts/verify_engine.py
```

## SDK defects found while building the gate

Both are the "accepted and silently ignored" shape — the same class as the `_filter_kwargs_for`
splitter bug in Leela's `findings/stage1_findings.md`.

1. **`get_server_info()` cannot work against an engine that requires auth.** It builds
   `RocketRideClient(..., public=True)`, but `_public` is written at `client.py:242` and never
   read anywhere else in the SDK. `connect()` sets `_desired_state='authenticated'` and calls
   `_internal_login()` unconditionally, sending `auth: ''`; the engine answers
   `AuthenticationException: No authorization provided`.
2. **`rrext_public_probe` returns no `version` field**, though the docstring promises
   `version, capabilities, platform, apps`. Observed body: `platform`, `capabilities`, `apps`
   only. Protocol-reported version is therefore **UNVERIFIED**.

Version is instead taken from `GET /version`, which is unauthenticated, returns 200, and matches
the binary's own `--version` exactly. `/ping` is a poor readiness probe — it requires auth and
answers 401, proving only that something holds the port.

## Open environment risks

1. **Docker VM is capped at 8.32 GB** against a 48 GB host. Not used for the engine (we run it
   natively) and must not be introduced for one side of a memory comparison.
2. **macOS ≠ Linux for OOM** — memory compression and jetsam instead of a Linux OOM killer.
   Stability numbers here are indicative; publishable claims need a Linux confirmation run.
3. **Ambient load.** The host is a working laptop, not a cleanroom. `env_capture.py` records the
   top CPU consumers and load average with every run.
4. **Thermal throttling** under sustained load on Apple Silicon; thermal state is captured before
   and after every run.
