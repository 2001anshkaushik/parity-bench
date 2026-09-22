import json, collections, glob, os

R = "/Users/ansh/RocketRide/Benchmarking/benchmark-A/working/results"
OUT = "/private/tmp/claude-501/-Users-ansh-RocketRide-Benchmarking-benchmark-A/99b99d9b-386c-4d1e-8b7e-cd129b6411f0/scratchpad/verify2/work/video_calc.json"

DIRS = {
    "s4_li_k16": f"{R}/batchsize_s4_20260921T013303Z/p5_li_video/li_k16",
    "s4_rr_k16": f"{R}/batchsize_s4_20260921T013303Z/p6_rr_video/rr_k16",
    "smoke_rr_k1": f"{R}/batchsize_smoke_20260920T113000Z/video_n16/rr_k1",
    "smoke_rr_k8": f"{R}/batchsize_smoke_20260920T113000Z/video_n16/rr_k8",
    "smoke_rr_k16": f"{R}/batchsize_smoke_20260920T113000Z/video_n16/rr_k16",
    "smoke_li_k8": f"{R}/batchsize_smoke_20260920T113000Z/video_n16/li_k8",
    "rep_rr_k16": f"{R}/batchsize_s3b_20260920T203139Z/video/rep/rr_k16_rep",
    "rep_li_k8": f"{R}/batchsize_s3b_20260920T203139Z/video/rep/li_k8_rep",
}

res = {}
for key, d in DIRS.items():
    ex_files = glob.glob(f"{d}/export_*.json")
    rec_files = glob.glob(f"{d}/records_*.jsonl")
    assert len(ex_files) == 1 and len(rec_files) == 1, (key, ex_files, rec_files)
    ex = json.load(open(ex_files[0]))
    recs = [json.loads(l) for l in open(rec_files[0])]
    meas = [r for r in recs if r.get("role") == "measured"]
    meas_ok = [r for r in meas if "error" not in r]
    total_frames = sum(r["frames_observed"] for r in meas_ok)
    th = ex["throughput"]
    eff = ex["efficiency"]
    out = {
        "n_records": len(recs), "roles": dict(collections.Counter(r.get("role") for r in recs)),
        "n_measured": len(meas), "n_errors": sum(1 for r in recs if "error" in r),
        "n_errors_measured": sum(1 for r in meas if "error" in r),
        "total_frames_recomputed": total_frames,
        "export_total_frames": th.get("total_frames"),
        "export_total_span_s": th.get("total_span_s"),
        "export_total_frames_per_s": th.get("total_frames_per_s"),
        "frames_per_s_recomputed": total_frames / th["total_span_s"],
        "effective_cores": eff.get("effective_cores"),
        "cpu_util_of_box": eff.get("cpu_util_of_box"),
        "idle_cores_with_instances_live": (eff.get("idle_burden") or {}).get("idle_cores_with_instances_live"),
        "idle_burden_instances": (eff.get("idle_burden") or {}).get("instances"),
        "export_n_errors": ex.get("n_errors"), "export_n_records": ex.get("n_records"), "export_n_offered": ex.get("n_offered"),
        "posture": ex.get("posture"),
        "offered_concurrency": (ex.get("provenance_leela") or {}).get("offered_concurrency"),
    }
    # percore within [min admit_ns, max done_ns] of measured records
    w0 = min(r["admit_ns"] for r in meas)
    w1 = max(r["done_ns"] for r in meas)
    pcf = f"{d}/percore.jsonl"
    if os.path.exists(pcf):
        samples = [json.loads(l) for l in open(pcf)]
        ins = [s for s in samples if w0 <= s["mono_ns"] <= w1]
        sums = [sum(s["busy"].values()) for s in ins]
        allsums = [sum(s["busy"].values()) for s in samples]
        out["percore"] = {"n_samples": len(samples), "n_inside": len(ins),
                          "ncores": dict(collections.Counter(len(s["busy"]) for s in ins)),
                          "mean_busy_inside": sum(sums) / len(sums), "idle_inside": 32 - sum(sums) / len(sums),
                          "mean_busy_all": sum(allsums) / len(allsums), "idle_all": 32 - sum(allsums) / len(allsums),
                          "w0_ns": w0, "w1_ns": w1, "window_s": (w1 - w0) / 1e9,
                          "first_mono": samples[0]["mono_ns"], "last_mono": samples[-1]["mono_ns"]}
    res[key] = out

json.dump(res, open(OUT, "w"), indent=1, default=str)
for k, v in res.items():
    print("=====", k)
    for kk, vv in v.items():
        print("  ", kk, "=", vv)
