#!/usr/bin/env python3
"""!! DEPRECATED HARNESS — ARCHIVED, DO NOT RUN !!

ASCENDING cold sweep; all four RocketRide saturation points it produced were withdrawn in session 11

Archived 2026-08-09. Preserved because the correction history is an asset: this script is the
evidence for how the corresponding number was produced and why it was withdrawn. It is NOT a
working instrument and its output must not be used.

Replacement, if you need this measurement: see publishable/STATE.md and publishable/README.md.
"""
import sys

sys.stderr.write(__doc__ + "\n")
sys.stderr.write("REFUSING TO RUN: this harness is deprecated and its results were withdrawn.\n")
sys.exit(2)

# ----------------------------------------------------------------------------------
# ORIGINAL SOURCE PRESERVED BELOW THIS LINE, UNREACHABLE. Do not remove the guard above.
# ----------------------------------------------------------------------------------

# #!/usr/bin/env python3
# """PHASE 1 — ISOLATED SATURATION PROFILE: RocketRide. The missing half.

# `isolated_profile.py` characterised the LlamaIndex service standing alone and found it saturates
# at concurrency 4. The engine has never had the equivalent, so every shared concurrency we have
# ever picked was picked blind — which is precisely the error sessions 6-8 made by comparing at
# c=8/16/32, all past LlamaIndex's saturation.

# Same harness, same statistics, same window/rep structure as the LlamaIndex profile so the two are
# directly readable side by side. NO COMPARISON is computed here; that is STEP 2's job and it has to
# happen in one interleaved session, not across two scripts.

# TUNED AND UNTUNED, both measured. Session 8 showed thread pinning helps above concurrency ~4 and
# hurts below it, so the saturation point itself may move with the setting. If it does, that is the
# finding: "RocketRide saturates at N" would be an incomplete statement without naming the config.

# PIPELINE: `embed_probe.pipe`, the 4-NODE pipeline built from SHIPPED components. This is the
# canonical choice (see FAIRNESS_BASIS.md) for two independent reasons — it is what a user actually
# deploys, and it returns the full embedding payload, matching what the LlamaIndex service returns.
# The 1-node `split_embed` variant is a benchmark-only workaround we wrote because the engine
# silently drops splitter kwargs; it also returns a 159-byte summary instead of vectors. Using it
# here would compare a stripped payload against a full one.

# ESCALATION BOUNDED at concurrency 64 spread over 4 driver processes = 16 per driver, far below the
# ~150-concurrent-pipeline livelock (finding 16) that hung a 300 s task creation in session 9.
# """
# from __future__ import annotations

# import asyncio
# import json
# import multiprocessing as mp
# import os
# import statistics
# import subprocess
# import sys
# import threading
# import time
# import uuid
# from pathlib import Path

# ROOT = Path(__file__).resolve().parent.parent
# sys.path.insert(0, str(ROOT))
# os.chdir(ROOT)

# from harness import engine_ops as eo   # noqa: E402

# OUT = ROOT / "results" / "isolated_profile_rocketride.json"
# UNIT = "The quick brown fox jumps over the lazy dog. "
# CONCS = [1, 2, 4, 8, 16, 32, 64]
# WINDOW = 4.0
# REPS = 5
# WARMUP = 1
# MAXDRV = 4
# THREAD_KEYS = ["OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS",
#                "VECLIB_MAXIMUM_THREADS", "NUMEXPR_NUM_THREADS", "TORCH_NUM_THREADS"]

# _BARRIER = None


# def _init(b):
#     global _BARRIER
#     _BARRIER = b


# def layout(conc):
#     d = min(MAXDRV, conc)
#     return d, max(1, conc // d)


# def _driver(args):
#     tag, doc, conc = args
#     barrier = _BARRIER

#     async def go():
#         from rocketride import RocketRideClient
#         base = json.loads((ROOT / "pipes" / "embed_probe.pipe").read_text())
#         base["project_id"] = str(uuid.uuid5(uuid.NAMESPACE_DNS, f"iprr-{tag}"))
#         p = ROOT / "pipes" / "generated" / f"iprr_{tag}.pipe"
#         p.parent.mkdir(parents=True, exist_ok=True)
#         p.write_text(json.dumps(base))
#         c = RocketRideClient()
#         await c.connect(timeout=30000)
#         r = await c.use(filepath=str(p.relative_to(ROOT)))
#         tok = r["token"]
#         await asyncio.wait_for(c.send(tok, doc, mimetype="text/plain"), timeout=600)

#         out = []
#         for w in range(REPS + WARMUP):
#             try:
#                 barrier.wait(timeout=240)
#             except Exception:
#                 pass
#             ok = fail = 0
#             lat = []
#             stop = time.time() + WINDOW
#             t0 = time.time()

#             async def worker():
#                 nonlocal ok, fail
#                 while time.time() < stop:
#                     st = time.perf_counter()
#                     try:
#                         await asyncio.wait_for(
#                             c.send(tok, doc, mimetype="text/plain"), timeout=600)
#                         lat.append(time.perf_counter() - st)
#                         ok += 1
#                     except Exception:
#                         fail += 1
#             await asyncio.gather(*(worker() for _ in range(conc)))
#             if w >= WARMUP:
#                 out.append({"ok": ok, "fail": fail, "elapsed": time.time() - t0, "lat": lat})
#         try:
#             await asyncio.wait_for(c.terminate(tok), timeout=120)
#         except Exception:
#             pass
#         try:
#             await c.disconnect()
#         except Exception:
#             pass
#         return out
#     return asyncio.run(go())


# def pct(vals, q):
#     if not vals:
#         return None
#     v = sorted(vals)
#     return round(v[min(len(v) - 1, int(len(v) * q))] * 1000, 2)


# class RSS(threading.Thread):
#     """Engine-tree peak RSS, sampled from OUTSIDE the driver processes."""

#     def __init__(self):
#         super().__init__(daemon=True)
#         self.peak, self.stop_flag = 0.0, False

#     def run(self):
#         import psutil
#         while not self.stop_flag:
#             tot, seen = 0.0, set()
#             for r in psutil.process_iter(["pid", "name"]):
#                 if (r.info["name"] or "").lower() != "engine":
#                     continue
#                 try:
#                     for p in [r] + r.children(recursive=True):
#                         if p.pid in seen:
#                             continue
#                         seen.add(p.pid)
#                         tot += p.memory_info().rss / 1e6
#                 except Exception:
#                     pass
#             self.peak = max(self.peak, tot)
#             time.sleep(0.25)


# def restart(tuned: bool) -> int:
#     subprocess.run(["bash", str(ROOT / "scripts" / "stop_engine.sh")], capture_output=True)
#     time.sleep(3)
#     env = dict(os.environ)
#     env["CPU_PROBE_ITERS"] = "235000"
#     env.pop("SE_INTEROP_THREADS", None)      # session 9: pinning inter-op is harmful
#     env["SE_REPORT_THREADS"] = "0"
#     for k in THREAD_KEYS:
#         env.pop(k, None)
#     if tuned:
#         for k in THREAD_KEYS:
#             env[k] = "1"
#     r = subprocess.run(["bash", str(ROOT / "scripts" / "start_engine.sh")],
#                        capture_output=True, env=env, text=True)
#     if "healthy" not in r.stdout:
#         raise RuntimeError(f"engine did not start: {r.stdout[-300:]}")
#     time.sleep(2)
#     # DECLARED != MEASURED — ask the task process what it actually got
#     p = subprocess.run([str(ROOT.parent / ".venv" / "bin" / "python"),
#                         str(ROOT / "scripts" / "probe_env.py"),
#                         f"ip{'T' if tuned else 'U'}{int(time.time())}"],
#                        capture_output=True, text=True, cwd=str(ROOT))
#     got = json.loads(p.stdout).get("torch_num_threads")
#     want = 1 if tuned else 10
#     if got != want:
#         raise RuntimeError(f"thread gate failed: wanted {want}, task process reports {got}")
#     print(f"    [env verified] torch_num_threads={got}", flush=True)
#     return got


# def profile(tokens: int) -> list[dict]:
#     doc = UNIT * max(1, tokens // 10)
#     rows = []
#     for conc in CONCS:
#         d, per = layout(conc)
#         ctx = mp.get_context("spawn")
#         barrier = ctx.Barrier(d)
#         sampler = RSS()
#         sampler.start()
#         with ctx.Pool(d, initializer=_init, initargs=(barrier,)) as pool:
#             res = pool.map(_driver, [(f"{tokens}_{conc}_{i}", doc, per) for i in range(d)])
#         sampler.stop_flag = True
#         sampler.join(timeout=5)

#         rates, all_lat, fails, total = [], [], 0, 0
#         for w in range(REPS):
#             ok = sum(r[w]["ok"] for r in res)
#             f = sum(r[w]["fail"] for r in res)
#             el = max(r[w]["elapsed"] for r in res)
#             rates.append(ok / el if el else 0.0)
#             fails += f
#             total += ok + f
#             for r in res:
#                 all_lat += r[w]["lat"]
#         med = statistics.median(rates)
#         sp = (max(rates) - min(rates)) / max(rates) if max(rates) else 0
#         row = {"conc": conc, "throughput": round(med, 2), "rates": [round(x, 2) for x in rates],
#                "spread": round(sp, 4), "gate": sp <= 0.10,
#                "p50": pct(all_lat, .50), "p95": pct(all_lat, .95),
#                "p99": pct(all_lat, .99), "p999": pct(all_lat, .999),
#                "peak_rss_mb": round(sampler.peak, 1),
#                "error_rate": round(fails / total, 5) if total else 0.0}
#         rows.append(row)
#         print(f"    c={conc:3d} {row['throughput']:8.2f}/s sp={sp * 100:5.1f}% "
#               f"{'OK  ' if row['gate'] else 'GATE'} P50={row['p50']:8.2f} P95={row['p95']:8.2f} "
#               f"P99={row['p99']:9.2f} P99.9={row['p999']:9.2f} rss={row['peak_rss_mb']:7.1f}MB "
#               f"err={row['error_rate']:.4f}", flush=True)
#     return rows


# def saturation(rows: list[dict]) -> dict:
#     """Lowest concurrency reaching 95% of peak throughput.

#     The automated 'knee' rule (last doubling buying >=15%) was shown unreliable on non-monotonic
#     data in session 9 — it reported c=32 from what was noise recovery. Saturation is reported
#     instead, and the full curve is printed so a reader can see the shape rather than trust a rule.
#     """
#     best = max(r["throughput"] for r in rows)
#     sat = next(r["conc"] for r in rows if r["throughput"] >= best * 0.95)
#     return {"saturation": sat, "peak_throughput": best,
#             "peak_at_conc": next(r["conc"] for r in rows if r["throughput"] == best),
#             "rule": "lowest concurrency reaching 95% of peak throughput"}


# def main() -> int:
#     eo.preflight("isolated-profile-rr")
#     print("=" * 118)
#     print("PHASE 1 — ISOLATED SATURATION PROFILE: RocketRide (4-node pipeline, shipped components)")
#     print("  NO COMPARISON. This characterises one service standing alone.")
#     print("=" * 118)
#     out = {"service": "rocketride-engine", "pipeline": "embed_probe.pipe (4-node)",
#            "profiles": {}}
#     try:
#         for tuned in (True, False):
#             label = "tuned" if tuned else "untuned"
#             print(f"\n{'=' * 60}\nengine {label.upper()}\n{'=' * 60}")
#             restart(tuned)
#             for tokens in (400, 1600):
#                 print(f"\n  {tokens} tokens/doc  [{label}]")
#                 rows = profile(tokens)
#                 out["profiles"][f"{label}|{tokens}"] = {
#                     "rows": rows, "derived": saturation(rows)}
#     finally:
#         eo.postflight("isolated-profile-rr")
#         OUT.write_text(json.dumps(out, indent=1))

#     print("\n" + "=" * 118)
#     print("SATURATION POINTS")
#     print("=" * 118)
#     for k, v in out["profiles"].items():
#         d = v["derived"]
#         print(f"  {k:16s}  SATURATION=c{d['saturation']:<3d} peak {d['peak_throughput']:8.2f}/s "
#               f"at c{d['peak_at_conc']}")
#     print("\n  (LlamaIndex reference, session 9: saturation c4, peak 74.71/s @400tok, "
#           "29.11/s @1600tok)")
#     print(f"\n  written -> {OUT}")
#     return 0


# if __name__ == "__main__":
#     sys.exit(main())
