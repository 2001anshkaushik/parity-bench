# TICKET DRAFT: launch task processes without the debugger by default, and set MALLOC_ARENA_MAX=2 in the engine image

> **DRAFT — NOT FILED.** Written by an autonomous benchmark run. It has not been filed, posted or sent anywhere (campaign
> rule: nothing reaches a person from an autonomous run). Ansh decides whether and where it goes.

## Summary

Every task process the engine starts runs with the Python debugger (debugpy/pydevd) attached and listening on a TCP
port, unless the execute request carries `noDebug`. The SDK's `use()` has no way to pass that flag. That costs work on
every Python call in the task, and it leaves a debug listener open in production. Separately, setting
`MALLOC_ARENA_MAX=2` for the task process roughly halved its anonymous memory in the benchmark's video workload, with
identical output. Proposal: make `noDebug` the default, keep debugging as an explicit opt-in, and set
`MALLOC_ARENA_MAX=2` in the engine image.

## What the source does (engine bundle 3.3.1.35)

- `engine/ai/modules/task/task_engine.py:296` — `self._noDebug = launch_args.get('noDebug', False)`: debugging is
  **on** unless the launch arguments say otherwise.
- `task_engine.py:1497-1507` — when `noDebug` is false, the engine assigns a debug port and starts the task with
  `--debug_port=<port> --debug_host=localhost`. In the benchmark's legs the port read back was **20000**; it appears in
  the task command line recorded in P2-B's export.
- `engine/ai/node.py:79-97` — the task calls `debugpy.listen((debug_host, debug_port), in_process_debug_adapter=True)`
  and then `debugpy.debug_this_thread()`.
- **Read back in the task process** (P2-B, env_probe on the measured token): `pydevd_loaded: true`, and
  `sys.monitoring` tool 0 is `pydevd`, so the debugger is registered as a monitoring tool over all Python in the task.
  With `noDebug` both disappear (`pydevd_loaded: false`, no monitoring tool).

## Why it matters

- **Security.** A debug adapter listening on `localhost:20000` accepts an attach from any process that can reach that
  address. That includes other containers on a shared network namespace; the benchmark's video legs run the engine with
  `--network host`, which puts the listener on the host's loopback. Attaching a debugger to a task process gives
  arbitrary code execution inside it. The listener is not needed outside development.
- **Cost.** pydevd is a `sys.monitoring` tool over every Python call in the task process. How much that costs was
  **not isolated** (see the evidence below).

## Evidence (benchmark campaign; committed artifacts, one box session each)

P2-B (`working/results/parity_p2_20260924T160106Z/`, `analysis_p2b.json`) ran the RocketRide video leg (16 videos, K=16,
T=4) as baseline versus COMBINED (`noDebug` + `MALLOC_ARENA_MAX=2`), ABAB, two runs each:

- **Output identical:** COMBINED was chunk-identical to baseline, chunk hashes **and** frame scores, on **16/16 videos in
  both pairs**.
- **Memory:** the sampled anonymous-memory peak of the task's container fell from 5,209 / 5,585 MB (baseline) to
  2,428 / 2,401 MB (COMBINED), roughly half. The change was joint, so which knob caused the drop was **not decomposed**.
  glibc's per-thread malloc arenas are the likely mechanism for `MALLOC_ARENA_MAX`, but that is an inference, not a
  measurement.
- **Speed — NOT a readable claim.** Pair a gained +13.95%, but pair b gained only **+3.42%, inside the replicate
  spreads of about 5%** (baseline 5.04%, COMBINED 4.65%). P2-B's pre-registered cell-mean rule cleared its bar
  (+8.55% against 5.04%) only because of pair a. This ticket does **not** rest on a speed gain.
- **Not the cause of the idle burn:** the task container's idle burn with the instance live and nothing submitted was
  1.232 cores at baseline and 1.234 / 1.238 cores with `noDebug`. The debugger is not what spins.

## Proposed change

1. **`task_engine.py:296`:** default `noDebug` to **true**. Debugging becomes an explicit opt-in: an execute argument
   `debug: true`, an engine flag, or an environment variable such as `ROCKETRIDE_TASK_DEBUG=1`, and it should be refused
   or warned about in production mode.
2. **`node.py`:** unchanged. It already listens only when `--debug_port` / `--debug_host` are passed.
3. **Engine image (`docker/Dockerfile.rocketride` in the benchmark's recipe, and the product's own image):**
   `ENV MALLOC_ARENA_MAX=2`, inherited by task processes. Read it back from `/proc/<task pid>/environ`, as P2-B did.
4. **SDK:** optionally expose the opt-in on `use()`, so clients stop adding the field to the execute call by hand (the
   benchmark drivers do this today: `exp_batchsize_sweep.py` BSZ_NODEBUG, `driver_video.py` P2_NODEBUG).

## Tests

- **Default is off:** start a task with no flags. The task command line has no `--debug_port`, nothing listens on the
  debug port (`ss -ltn` inside the container), and `pydevd` is neither imported nor a `sys.monitoring` tool (the
  benchmark's env_probe reads all three).
- **Opt-in works:** with the explicit opt-in, the port listens and a debugger can attach, as today.
- **Output identity:** the docs pipeline (`product_pdf.pipe`) and the video pipeline are chunk-identical with the
  change on and off. P2-B did this for video on 16 videos; docs would reuse the P1-B identity harness.
- **Memory:** the task container's sampled anonymous peak on a fixed video workload does not increase, and the value
  is recorded. `MALLOC_ARENA_MAX` is read back in the task process's environment.
- **Null control:** run the default-off check against today's image. It must fail (the listener is there), or the
  check proves nothing.

## Out of scope

- The video throughput gap. P2-B found the configuration closes only about a quarter of it, and P3-B investigates the
  rest.
- Any change to model code.
