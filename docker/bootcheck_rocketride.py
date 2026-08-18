#!/usr/bin/env python3
"""Build-time boot assertion: the image must START THE ENGINE before the build may go green.

WHY. Both Phase-2 images built green and then crash-looped on the box — the engine compiles
every requirements file in its tree at boot, and an unsatisfiable pin (onnxruntime-gpu==1.20.1,
never published to PyPI) killed it before the port ever opened. Nothing in the build had ever
executed the one artifact the image exists to run. This script closes that gap: it boots the
engine exactly as the entrypoint will (same binary, same --host/--port flags), waits for the
listener, attempts a real WebSocket connect through the SDK, and fails the build with the boot
log if any of that does not happen.

WHAT IT PROVES AND WHAT IT DOES NOT — the boundary, stated rather than implied:
  proves      the engine binary loads (glibc/libc++/JRE resolution), boots, survives the
              constraints compile, binds the flagged interface, accepts a WebSocket handshake
  does NOT    prove a task can spawn: use() + send() load models and spawn the task process,
              which is minutes of work and network — that is smoke_phase2.py's job on the box.

It runs in a THROWAWAY build stage, so boot residue (logs, caches, lock files) never ships in
the runtime layers. Deliberate cost: the constraints cache compiled during this boot is
discarded with the stage, so the first boot on the box recompiles it — which has been true of
every boot to date, and needs network exactly as this build step does.
"""
import os
import socket
import subprocess
import sys
import time

ENGINE_DIR = os.environ.get("RR_ENGINE_DIR", "/opt/rocketride/engine")
PORT = int(os.environ.get("RR_PORT", "5565"))
TIMEOUT_S = int(os.environ.get("RR_BOOT_TIMEOUT_S", "600"))
LOG = "/tmp/engine_boot.log"
MARKER = "/tmp/boot-ok"


def log_tail(n: int = 80) -> str:
    try:
        with open(LOG, errors="replace") as fh:
            return "".join(fh.readlines()[-n:]) or "(log empty)"
    except OSError:
        return "(no log)"


def port_open() -> bool:
    s = socket.socket()
    s.settimeout(2)
    try:
        s.connect(("127.0.0.1", PORT))
        return True
    except OSError:
        return False
    finally:
        s.close()


def main() -> int:
    print(f"[bootcheck] starting engine (timeout {TIMEOUT_S}s) ...", flush=True)
    with open(LOG, "w") as lg:
        # The SAME flags the runtime entrypoint passes — a check that boots a different
        # configuration proves a different image.
        proc = subprocess.Popen(
            ["./engine", "ai/eaas.py", "--host=0.0.0.0", f"--port={PORT}"],
            cwd=ENGINE_DIR, stdout=lg, stderr=subprocess.STDOUT)
    t0 = time.time()
    up = False
    while time.time() - t0 < TIMEOUT_S:
        if proc.poll() is not None:
            print(f"[bootcheck] BOOT FAILED: engine exited rc={proc.returncode} "
                  f"after {time.time() - t0:.0f}s. Log tail:\n{log_tail()}", flush=True)
            return 1
        if port_open():
            up = True
            break
        time.sleep(2)
    if not up:
        print(f"[bootcheck] BOOT FAILED: port {PORT} not open within {TIMEOUT_S}s "
              f"(engine still running — likely wedged in constraints compile or model "
              f"resolution). Log tail:\n{log_tail()}", flush=True)
        proc.kill()
        return 1
    boot_s = time.time() - t0
    print(f"[bootcheck] port {PORT} open after {boot_s:.0f}s", flush=True)

    # A real handshake, not just a listener. Degrades honestly: if the SDK cannot even be
    # imported the port-open result stands as the gate and the marker RECORDS the degradation
    # — printed and persisted, never silent. A failed handshake with a working import is a
    # broken engine and fails the build.
    sdk_state = "not-attempted"
    try:
        import asyncio
        from rocketride import RocketRideClient

        async def go():
            c = RocketRideClient(uri=f"ws://127.0.0.1:{PORT}/task/service",
                                 auth=os.environ.get("ROCKETRIDE_APIKEY", "local-dev"))
            await c.connect(timeout=60000)
            await c.disconnect()

        asyncio.run(go())
        sdk_state = "connected"
        print("[bootcheck] SDK websocket connect: OK", flush=True)
    except ImportError as e:
        sdk_state = f"sdk-unavailable ({e})"
        print(f"[bootcheck] SDK connect SKIPPED: {e} — port-open remains the gate; "
              "recorded in the marker, not hidden", flush=True)
    except Exception as e:
        print(f"[bootcheck] BOOT FAILED: port open but the SDK handshake failed: "
              f"{type(e).__name__}: {e}. Log tail:\n{log_tail()}", flush=True)
        proc.terminate()
        return 1

    proc.terminate()
    try:
        proc.wait(timeout=30)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait()
    with open(MARKER, "w") as fh:
        fh.write(f"boot-check PASSED: port open in {boot_s:.0f}s; sdk={sdk_state}\n")
    print("[bootcheck] PASSED", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
