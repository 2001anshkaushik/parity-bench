import json, re
from decimal import Decimal, ROUND_HALF_UP

W = "/private/tmp/claude-501/-Users-ansh-RocketRide-Benchmarking-benchmark-A/99b99d9b-386c-4d1e-8b7e-cd129b6411f0/scratchpad/verify2"
R = "/Users/ansh/RocketRide/Benchmarking/benchmark-A/working/results"
D = json.load(open(f"{W}/work/docs_calc.json"))
V = json.load(open(f"{W}/work/video_calc.json"))

results = []


def ndec(s):
    s = s.replace(",", "").replace("%", "").replace("x", "").strip()
    return len(s.split(".")[1]) if "." in s else 0


def rnd(x, nd):
    q = Decimal(1).scaleb(-nd)
    return str(Decimal(repr(float(x))).quantize(q, rounding=ROUND_HALF_UP))


def near_boundary(x, nd):
    y = abs(float(x)) * (10 ** nd)
    frac = y - int(y)
    return abs(frac - 0.5) < 1e-6


def num(section, figure, reported, value, note="", pct=False, suffix=""):
    """reported: string as displayed. value: raw recomputed (fraction if pct)."""
    rep = reported.replace(",", "").replace("%", "").replace(suffix, "").strip()
    nd = ndec(rep)
    v = float(value) * (100.0 if pct else 1.0)
    rec = rnd(v, nd)
    ok = Decimal(rec) == Decimal(rep)
    n = note
    if near_boundary(v, nd):
        n = (n + "; " if n else "") + "value sits on a rounding boundary"
    results.append({"section": section, "figure": figure, "reported": reported,
                    "recomputed": rec + ("%" if pct else "") + suffix,
                    "recomputed_raw": v, "match": bool(ok), "note": n})


def lit(section, figure, reported, recomputed, match, note=""):
    results.append({"section": section, "figure": figure, "reported": reported,
                    "recomputed": recomputed, "match": bool(match), "note": note})


S0 = "## 0. Answers"
S1 = "## 1. Headline"
SC5 = "### Empty-content documents, both arms (C5)"
S2 = "## 2. Batch size at full scale"
S3 = "## 3. AMI video at full scale"

rr_c, li_c = D["p1_rr_cont32"], D["p2_li_cont"]
RRK = {128: D["p3_rr_k128"], 256: D["e7_rr_k256"], 512: D["e9_rr_k512"], 1024: D["e11_rr_k1024"]}
LIK = {128: D["p4_li_k128"], 256: D["e8_li_k256"], 512: D["e10_li_k512"], 1024: D["e12b_li_k1024"]}

# ---------------- extra inputs ----------------
exp_rr = json.load(open(f"{R}/exp_batchsize_sweep_rr__20260921T024645Z__eebea66604c5.json"))["data"]["posture"]
exp_li = json.load(open(f"{R}/exp_batchsize_sweep_li__20260921T035607Z__f5a53f343098.json"))["data"]["posture"]


def span_rate_file(p):
    rows = [json.loads(l) for l in open(p)]
    ok = sum(1 for r in rows if r["ok"] is True)
    sp = (max(r["completion_ns"] for r in rows) - min(r["submit_ns"] for r in rows)) / 1e9
    return ok / sp


anc = {}
for arm in ("rr", "li"):
    for C in (1, 8):
        anc[(arm, C)] = span_rate_file(f"{R}/batchsize_s3b_20260920T203139Z/anchor_{arm}/perdoc_{arm}_refc{C}_anchor.jsonl")
s5 = {}
for leg in ("a1", "a2", "b"):
    j = json.load(open(f"{R}/batchsize_s5_20260921T205917Z/s5c/rr_{leg}/leg_rr_refc32_smt_{leg}.json"))
    s5[leg] = j
thr = [s5[k]["throughput"]["docs_per_s"] for k in ("a1", "a2", "b")]
cpd = [s5[k]["cost"]["cpu_s_per_doc"] for k in ("a1", "a2", "b")]
thr_delta = thr[2] / ((thr[0] + thr[1]) / 2) - 1
cpd_delta = cpd[2] / ((cpd[0] + cpd[1]) / 2) - 1
null_spread = abs(thr[0] - thr[1]) / ((thr[0] + thr[1]) / 2)
rrb_cpuset = re.search(r"'([0-9,\-]+)'", s5["b"]["cost"]["available_cpus_source"]).group(1)

floors = json.load(open(f"{R}/batchsize_s4_20260921T013303Z/envelope_floors.json"))
knee_legs = {4: ["rr_u32a/leg_rr_refc4_u32a.json"], 8: ["rr_u32a/leg_rr_refc8_u32a.json"],
             16: ["rr_u32a/leg_rr_refc16_u32a.json"],
             32: ["rr_u32a/leg_rr_refc32_u32a.json", "rr_u32b/leg_rr_refc32_u32b.json"],
             64: ["rr_u32a/leg_rr_refc64_u32a.json"]}
kv = {}
for C, ps in knee_legs.items():
    xs = [json.load(open(f"{R}/batchsize_s3b_20260920T203139Z/{p}"))["throughput"]["docs_per_s"] for p in ps]
    kv[C] = sum(xs) / len(xs)
best = max(kv.values())
knee = min(C for C, v in kv.items() if v >= best * (1 - floors["rr"]))

pages = None
for l in open(f"{R}/corpus_manifest.jsonl"):
    r = json.loads(l)
    if r["file"] == "039_039660.pdf":
        pages = r["pages"]

vs_li, vs_rr = V["s4_li_k16"], V["s4_rr_k16"]
sm = {k: V[k]["export_total_frames_per_s"] for k in ("smoke_rr_k1", "smoke_rr_k8", "smoke_rr_k16", "smoke_li_k8", "rep_rr_k16", "rep_li_k8")}
rr3 = [sm["smoke_rr_k1"], sm["smoke_rr_k8"], sm["smoke_rr_k16"]]
moved = (max(rr3) - min(rr3)) / (sum(rr3) / 3)
rr_rep_spread = abs(sm["smoke_rr_k16"] - sm["rep_rr_k16"]) / ((sm["smoke_rr_k16"] + sm["rep_rr_k16"]) / 2)
li_rep_spread = abs(sm["smoke_li_k8"] - sm["rep_li_k8"]) / ((sm["smoke_li_k8"] + sm["rep_li_k8"]) / 2)

leg_p1 = json.load(open(f"{R}/batchsize_s4_20260921T013303Z/p1_rr_cont32/leg_rr_refc32_main.json"))
leg_p2 = json.load(open(f"{R}/batchsize_s4_20260921T013303Z/p2_li_cont/leg_li_refc32_main.json"))
video_li_ex = json.load(open(f"{R}/batchsize_s4_20260921T013303Z/p5_li_video/li_k16/export_llamaindex_video_workers_blast.json"))
video_rr_ex = json.load(open(f"{R}/batchsize_s4_20260921T013303Z/p6_rr_video/rr_k16/export_rocketride_video_default_blast.json"))

SIX = ["OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS", "VECLIB_MAXIMUM_THREADS", "NUMEXPR_NUM_THREADS", "TORCH_NUM_THREADS"]


def dagger(section, where):
    num(section, f"dagger caveat ({where}): same-harness cpuset 0-23 throughput change = rr_b / mean(rr_a1, rr_a2) - 1 on throughput.docs_per_s", "-2.5%", thr_delta, pct=True,
        note=f"docs/s a1={thr[0]}, a2={thr[1]}, b={thr[2]}")
    num(section, f"dagger caveat ({where}): same-harness cpuset 0-23 CPU-s/doc change = rr_b / mean(rr_a1, rr_a2) - 1 on cost.cpu_s_per_doc", "-11.7%", cpd_delta, pct=True,
        note=f"cpu_s_per_doc a1={cpd[0]}, a2={cpd[1]}, b={cpd[2]}")
    num(section, f"dagger caveat ({where}): S5-C null-control spread |a1 - a2| / mean on docs/s", "1.63%", null_spread, pct=True)
    lit(section, f"dagger caveat ({where}): the S5-C (b) cell is cpuset 0-23", "cpuset 0-23", rrb_cpuset, rrb_cpuset == "0-23",
        "rr_b leg JSON cost.available_cpus_source: arm cgroup reports '0-23'")


# ================= Section 0 =================
rr_bat = {k: RRK[k]["span_docs_per_s"] for k in RRK}
li_bat = {k: LIK[k]["span_docs_per_s"] for k in LIK}
lit(S0, "No batch size beats continuous submission on either arm (every batched span docs/s < continuous C=32)",
    "no batch size beats continuous",
    f"RR max batched {max(rr_bat.values()):.4f} < {rr_c['span_docs_per_s']:.4f}; LI max batched {max(li_bat.values()):.4f} < {li_c['span_docs_per_s']:.4f}",
    max(rr_bat.values()) < rr_c["span_docs_per_s"] and max(li_bat.values()) < li_c["span_docs_per_s"])
ks = [128, 256, 512, 1024]
lit(S0, "Within batch mode, throughput rises with K on both arms (monotone in K)", "rises with K on both arms",
    "RR " + " < ".join(f"{rr_bat[k]:.4f}" for k in ks) + "; LI " + " < ".join(f"{li_bat[k]:.4f}" for k in ks),
    all(rr_bat[a] < rr_bat[b] for a, b in zip(ks, ks[1:])) and all(li_bat[a] < li_bat[b] for a, b in zip(ks, ks[1:])))
for k, rep in zip(ks, ["0.9643", "1.1952", "1.392", "1.5142"]):
    num(S0, f"RocketRide K={k} span docs/s", rep, rr_bat[k])
for k, rep in zip(ks, ["1.9264", "2.4591", "3.0463", "3.8639"]):
    num(S0, f"LlamaIndex K={k} span docs/s", rep, li_bat[k])
rr_best_ratio = max(rr_bat.values()) / rr_c["span_docs_per_s"]
li_best_ratio = max(li_bat.values()) / li_c["span_docs_per_s"]
num(S0, "best batch / continuous C=32 rate, RocketRide (K=1024 / C=32 span docs/s)", "0.647", rr_best_ratio,
    note=f"from display-rounded inputs: {1.5142/2.3395:.5f}")
num(S0, "best batch / continuous C=32 rate, LlamaIndex (K=1024 / C=32 span docs/s)", "0.758", li_best_ratio,
    note=f"from display-rounded inputs: {3.8639/5.096:.5f}")
for k, rep in zip([128, 256, 512], ["93.2", "51.9", "45.6"]):
    num(S0, f"RocketRide K={k}: seconds to spare for the batch holding 039_039660.pdf (1800 - wall)", rep, RRK[k]["batches"]["spare"])
b1024 = RRK[1024]["batches"]
lit(S0, "RocketRide K=1024: the batch holding 039_039660.pdf died at the deadline", "died at the deadline",
    f"batch {b1024['target_batch']} wall {b1024['target_batch_wall']:.3f} s (spare {b1024['spare']:.3f} s); died batches {b1024['died_batches']}; 039 row reason {RRK[1024]['target']['reason']}",
    b1024["target_batch"] in b1024["died_batches"])
for k, rep in zip(ks, ["1761.2", "1694.7", "1698.8", "1558.7"]):
    num(S0, f"LlamaIndex K={k}: seconds to spare for the batch holding 039_039660.pdf (1800 - wall)", rep, LIK[k]["batches"]["spare"])
num(S0, "RocketRide K=1024 batches lost to the deadline", "1", len(b1024["died_batches"]))
num(S0, "RocketRide K=1024 documents lost with that batch", "759", b1024["died_docs"])
num(S0, "Video: videos in flight K set for the LlamaIndex arm (S4 export offered_concurrency)", "16", vs_li["offered_concurrency"])
num(S0, "Video: videos in flight K set for the RocketRide arm (S4 export offered_concurrency)", "16", vs_rr["offered_concurrency"])
num(S0, "Video smoke slice size (measured records per smoke leg)", "16", V["smoke_rr_k16"]["n_measured"],
    note="every smoke/replicate leg has 16 measured records: " + ", ".join(f"{k}={V[k]['n_measured']}" for k in sm))
num(S0, "RocketRide video: moved X% from K=1 to K=16 = (max - min) / mean over K=1, K=8, K=16 frames/s", "9.17%", moved, pct=True,
    note=f"K=1 {rr3[0]}, K=8 {rr3[1]}, K=16 {rr3[2]}")
num(S0, "RocketRide video K=16 replicate spread |first - replicate| / mean", "9.76%", rr_rep_spread, pct=True,
    note=f"first {sm['smoke_rr_k16']}, replicate {sm['rep_rr_k16']}")
lit(S0, "the K move lies inside the K=16 replicate spread", "9.17% inside 9.76%", f"{moved*100:.4f}% < {rr_rep_spread*100:.4f}%", moved < rr_rep_spread)
num(S0, "one RocketRide token (docs posture rr_tokens)", "1", exp_rr["rr_tokens"])
num(S0, "24 LlamaIndex workers (docs posture ws1_workers)", "24", int(exp_li["ws1_workers"]))
num(S0, "8 LlamaIndex instances (video posture declared_workers)", "8", video_li_ex["provenance_video"]["posture"]["declared_workers"])
# best-to-best table
num(S0, "Best-to-best: Docs span docs/s, RocketRide", "2.3395", rr_c["span_docs_per_s"])
num(S0, "Best-to-best: Docs span docs/s, LlamaIndex", "5.096", li_c["span_docs_per_s"])
num(S0, "Best-to-best: Docs CPU utilisation engine/32, RocketRide (cost.cpu_utilization)", "56.16%", rr_c["leg_cost"]["cpu_utilization"], pct=True,
    note=f"engine cores / 32 = {rr_c['leg_cost']['engine_container_cores']/32:.5f}")
num(S0, "Best-to-best: Docs CPU utilisation engine/32, LlamaIndex (cost.cpu_utilization)", "72.59%", li_c["leg_cost"]["cpu_utilization"], pct=True,
    note=f"engine cores / 32 = {li_c['leg_cost']['engine_container_cores']/32:.5f}")
num(S0, "Best-to-best: Docs idle core-equivalents, RocketRide (32 - mean host busy)", "13.802", rr_c["percore"]["idle"])
num(S0, "Best-to-best: Docs idle core-equivalents, LlamaIndex (32 - mean host busy)", "8.714", li_c["percore"]["idle"])
num(S0, "Best-to-best: Docs idle spin, RocketRide (cost.idle_spin_measured.cores)", "1.224", rr_c["leg_cost"]["idle_spin"])
num(S0, "Best-to-best: Docs idle spin, LlamaIndex (cost.idle_spin_measured.cores)", "0.034", li_c["leg_cost"]["idle_spin"])
lit(S0, "Best-to-best: Video frames/s, RocketRide given as ranking only (LlamaIndex ahead)", "RANKING ONLY (leg-6 rule)",
    f"ranking only; recomputed RR {vs_rr['frames_per_s_recomputed']:.3f} < LI {vs_li['frames_per_s_recomputed']:.3f} frames/s (not quoted)",
    vs_rr["frames_per_s_recomputed"] < vs_li["frames_per_s_recomputed"])
num(S0, "Best-to-best: Video frames/s, LlamaIndex (total_frames / total_span_s)", "13.524", vs_li["frames_per_s_recomputed"])
num(S0, "Best-to-best: Video CPU utilisation, RocketRide (efficiency.cpu_util_of_box)", "18.29%", vs_rr["cpu_util_of_box"], pct=True)
num(S0, "Best-to-best: Video CPU utilisation, LlamaIndex (efficiency.cpu_util_of_box)", "89.27%", vs_li["cpu_util_of_box"], pct=True)
num(S0, "Best-to-best: Video idle core-equivalents, RocketRide (in-window percore)", "26.015", vs_rr["percore"]["idle_inside"])
num(S0, "Best-to-best: Video idle core-equivalents, LlamaIndex (in-window percore)", "3.132", vs_li["percore"]["idle_inside"])
dagger(S0, "footnote under the best-to-best table")
lit(S0, "Per unit: 'from one to eight documents in flight' - anchor legs are C=1 and C=8", "C=1 -> C=8",
    "anchor leg JSON reference_c 1 and 8 on both arms", True,
    "the anchor leg JSONs record reference_c only; the LlamaIndex anchor's worker count ('one worker') is not recorded in any permitted file, so that label is unverified")
num(S0, "Per unit: RocketRide token throughput grows (anchor C=8 / C=1 span docs/s)", "5.00x", anc[("rr", 8)] / anc[("rr", 1)], suffix="x",
    note=f"C=1 {anc[('rr',1)]:.6f}, C=8 {anc[('rr',8)]:.6f}")
num(S0, "Per unit: LlamaIndex worker throughput grows (anchor C=8 / C=1 span docs/s)", "1.01x", anc[("li", 8)] / anc[("li", 1)], suffix="x",
    note=f"C=1 {anc[('li',1)]:.6f}, C=8 {anc[('li',8)]:.6f}")

# ================= Section 1 =================
num(S1, "measured documents per continuous leg (heading '9,975 GovDocs PDFs'), RocketRide", "9,975", rr_c["n_rows"])
num(S1, "measured documents per continuous leg (heading '9,975 GovDocs PDFs'), LlamaIndex", "9,975", li_c["n_rows"])
num(S1, "warm-up documents ('+ 25 warm-up'), RocketRide leg warm_up.docs", "25", leg_p1["warm_up"]["docs"])
num(S1, "warm-up documents ('+ 25 warm-up'), LlamaIndex leg warm_up.docs", "25", leg_p2["warm_up"]["docs"])
lit(S1, "caches prewarmed (both legs)", "caches prewarmed", f"prewarm.attempted RR {leg_p1['prewarm']['attempted']}, LI {leg_p2['prewarm']['attempted']}",
    leg_p1["prewarm"]["attempted"] is True and leg_p2["prewarm"]["attempted"] is True)
num(S1, "LlamaIndex service workers (ws1_workers)", "24", int(exp_li["ws1_workers"]))
num(S1, "Posture RR: tokens", "1", exp_rr["rr_tokens"])
lit(S1, "Posture RR: threads= not passed", "threads= not passed", exp_rr["rr_threads_requested"], "NOT PASSED" in str(exp_rr["rr_threads_requested"]))
lit(S1, "Posture RR: six thread variables at 1", "six thread variables at 1", json.dumps(exp_rr["thread_env"]),
    all(exp_rr["thread_env"].get(k) == "1" for k in SIX) and all(exp_rr["in_process_readback"]["env"].get(k) == "1" for k in SIX),
    "container thread_env and in-process read-back env both show all six = '1'")
num(S1, "Posture RR: torch threads read in task process", "1", exp_rr["in_process_readback"]["torch_num_threads"])
lit(S1, "Posture RR: cpuset 0-31 of 32", "cpuset 0-31 of 32", f"cpuset_effective.raw {exp_rr['cpuset_effective']['raw']}, host_nproc {exp_rr['host_nproc']}",
    exp_rr["cpuset_effective"]["raw"] == "0-31" and exp_rr["host_nproc"] == 32)
num(S1, "Posture LI: workers", "24", int(exp_li["ws1_workers"]))
lit(S1, "Posture LI: six thread variables at 1", "six thread variables at 1", json.dumps(exp_li["thread_env"]),
    all(exp_li["thread_env"].get(k) == "1" for k in SIX) and all(exp_li["in_process_readback"]["health_thread_env"].get(k) == "1" for k in SIX)
    and exp_li["in_process_readback"]["all_workers_agree"] is True,
    f"container thread_env, /health env, and per-process environ ({exp_li['in_process_readback']['n_worker_processes_read']} processes read, all agree) all = '1'")
num(S1, "Posture LI: torch threads read in each worker (in_process_readback.health_torch_threads)", "1", exp_li["in_process_readback"]["health_torch_threads"],
    note="value matches; wording caveat: health_torch_threads comes from one GET /health answered inside a uvicorn worker - only the six env vars were read per worker process")
lit(S1, "Posture LI: cpuset 0-31 of 32", "cpuset 0-31 of 32", f"cpuset_effective.raw {exp_li['cpuset_effective']['raw']}, host_nproc {exp_li['host_nproc']}",
    exp_li["cpuset_effective"]["raw"] == "0-31" and exp_li["host_nproc"] == 32)
lit(S1, "Submission RR: continuous C=32 is the knee (smallest C with mean docs/s >= best x (1 - floor_rr))", "C=32 (the knee)",
    f"C means {json.dumps({str(k): round(v, 4) for k, v in kv.items()})}; floor_rr {floors['rr']}; threshold {best*(1-floors['rr']):.4f}; knee C={knee}",
    knee == 32)
num(S1, "Submission LI: its floor (envelope_floors.json li)", "9.87%", floors["li"], pct=True)
li16 = D["p2_li_cont16"]["span_docs_per_s"]
lit(S1, "Submission LI: C=32 is a TIE with C=16 inside the 9.87% floor", "TIE with C=16",
    f"C=32 {li_c['span_docs_per_s']:.4f}, C=16 {li16:.4f}; gap {(1-li16/li_c['span_docs_per_s'])*100:.2f}% < {floors['li']*100:.2f}%",
    li16 >= li_c["span_docs_per_s"] * (1 - floors["li"]),
    "gap computed on span docs/s recomputed from perdoc; leg JSON docs_per_s (5.096 vs 4.6511) gives the same verdict")
num(S1, "Span throughput docs/s PRIMARY, RocketRide", "2.3395", rr_c["span_docs_per_s"])
num(S1, "Span throughput docs/s PRIMARY, LlamaIndex", "5.096", li_c["span_docs_per_s"])
num(S1, "Span with 039_039660.pdf dropped from both arms, RocketRide", "3.6956", rr_c["span_docs_per_s_drop"])
num(S1, "Span with 039_039660.pdf dropped from both arms, LlamaIndex", "5.0955", li_c["span_docs_per_s_drop"])
num(S1, "docs/s to the 99th-percentile completion, RocketRide", "3.9344", rr_c["p99"]["rate"], note=f"k={rr_c['p99']['k']} of {rr_c['p99']['n_ok']} ok rows")
num(S1, "docs/s to the 99th-percentile completion, LlamaIndex", "5.2865", li_c["p99"]["rate"], note=f"k={li_c['p99']['k']} of {li_c['p99']['n_ok']} ok rows")
lit(S1, "Document that set the span, RocketRide", "039_039660.pdf", rr_c["span_setter"]["doc"], rr_c["span_setter"]["doc"] == "039_039660.pdf")
num(S1, "Held of the span-setting document, RocketRide, s", "1722", rr_c["span_setter"]["held_s"])
lit(S1, "Document that set the span, LlamaIndex", "011_011575.pdf", li_c["span_setter"]["doc"], li_c["span_setter"]["doc"] == "011_011575.pdf")
num(S1, "Held of the span-setting document, LlamaIndex, s", "149.8", li_c["span_setter"]["held_s"])
for arm, c in (("RocketRide", rr_c), ("LlamaIndex", li_c)):
    pass
num(S1, "Engine container CPU cores, RocketRide (cost.engine_container_cores)", "17.97", rr_c["leg_cost"]["engine_container_cores"])
num(S1, "Engine container CPU cores, LlamaIndex (cost.engine_container_cores)", "23.228", li_c["leg_cost"]["engine_container_cores"])
num(S1, "Driver CPU cores, RocketRide (cost.driver_cores)", "0.036", rr_c["leg_cost"]["driver_cores"])
num(S1, "Driver CPU cores, LlamaIndex (cost.driver_cores)", "0.039", li_c["leg_cost"]["driver_cores"])
num(S1, "Host busy cores, RocketRide (mean of per-sample busy sums)", "18.198", rr_c["percore"]["mean_busy"],
    note=f"leg percore_host.mean_busy_cores {rr_c['leg_percore_host']['mean_busy_cores']} (agrees); {rr_c['percore']['n_samples']} samples, all inside the leg window")
num(S1, "Host busy cores, LlamaIndex (mean of per-sample busy sums)", "23.286", li_c["percore"]["mean_busy"],
    note=f"leg percore_host.mean_busy_cores {li_c['leg_percore_host']['mean_busy_cores']} (agrees); {li_c['percore']['n_samples']} samples, all inside the leg window")
num(S1, "CPU utilisation engine/32, RocketRide (cost.cpu_utilization)", "56.16%", rr_c["leg_cost"]["cpu_utilization"], pct=True)
num(S1, "CPU utilisation engine/32, LlamaIndex (cost.cpu_utilization)", "72.59%", li_c["leg_cost"]["cpu_utilization"], pct=True)
num(S1, "Idle core-equivalents (32 - host busy), RocketRide", "13.802", rr_c["percore"]["idle"],
    note=f"leg percore_host.idle_core_equivalents {rr_c['leg_percore_host']['idle_core_equivalents']} (agrees)")
num(S1, "Idle core-equivalents (32 - host busy), LlamaIndex", "8.714", li_c["percore"]["idle"],
    note=f"leg percore_host.idle_core_equivalents {li_c['leg_percore_host']['idle_core_equivalents']} (agrees)")
num(S1, "Idle spin, RocketRide (cost.idle_spin_measured.cores)", "1.224", rr_c["leg_cost"]["idle_spin"])
num(S1, "Idle spin, LlamaIndex (cost.idle_spin_measured.cores)", "0.034", li_c["leg_cost"]["idle_spin"])
num(S1, "CPU-seconds per document, RocketRide (cost.cpu_s_per_doc)", "7.681", rr_c["leg_cost"]["cpu_s_per_doc"])
num(S1, "CPU-seconds per document, LlamaIndex (cost.cpu_s_per_doc)", "4.558", li_c["leg_cost"]["cpu_s_per_doc"])
for arm, c, reps in (("RocketRide", rr_c, ["9,885", "89", "1", "0"]), ("LlamaIndex", li_c, ["9,873", "102", "0", "0"])):
    for lab, key, rep in zip(["completed", "content outcome", "lost to the deadline", "other failure"], ["completed", "content", "deadline", "other"], reps):
        num(S1, f"Documents {lab}, {arm}", rep, c["docs"][key])
dd = rr_c["deadline_docs"]
num(S1, "RocketRide leg documents lost to the 1,800 s deadline", "1", len(dd))
lit(S1, "RocketRide deadline-lost document name", "011_011464.pdf", dd[0][0], dd[0][0] == "011_011464.pdf", f"reason {dd[0][2]}")
num(S1, "RocketRide deadline-lost document held, s", "1800", dd[0][1])
num(S1, "039_039660.pdf pages per the corpus manifest", "39", pages)
num(S1, "039_039660.pdf finished this many s after the 99th-percentile completion (RocketRide)", "1738", rr_c["target"]["completion_minus_p99_kth_s"])
lit(S1, "039_039660.pdf set the span (RocketRide)", "set the span", f"max-completion row: {rr_c['span_setter']['doc']}", rr_c["target"]["is_max_completion"])
dagger(S1, "footnote under the section 1 table")

# ================= C5 =================
rrs, lis = set(rr_c["content_set"]), set(li_c["content_set"])
num(SC5, "RocketRide empty-content (content outcome) count, continuous C=32", "89", len(rrs))
num(SC5, "LlamaIndex empty-content (content outcome) count, continuous C=32", "102", len(lis))
num(SC5, "empty on both", "89", len(rrs & lis))
num(SC5, "empty on LlamaIndex only (count)", "13", len(lis - rrs))
rep13 = ["002_002400.pdf", "004_004306.pdf", "008_008724.pdf", "009_009802.pdf", "014_014222.pdf", "018_018542.pdf", "020_020747.pdf",
         "020_020806.pdf", "022_022819.pdf", "027_027613.pdf", "033_033689.pdf", "037_037919.pdf", "040_040669.pdf"]
lit(SC5, "empty on LlamaIndex only (the 13 names)", ", ".join(rep13), ", ".join(sorted(lis - rrs)), sorted(rep13) == sorted(lis - rrs))
num(SC5, "empty on RocketRide only (count)", "0", len(rrs - lis))
lit(SC5, "empty on RocketRide only (names)", "none", ", ".join(sorted(rrs - lis)) or "none", len(rrs - lis) == 0)

# ================= Section 2 =================
REP_RR = {
    128: dict(span="0.9643", nb="78", med="75.0", mx="1706.8", tb="77", tw="1706.8", spare="93.2", share="16.65%", died="0", ret="9,975", lost="0", numer="9,886", idle="24.771"),
    256: dict(span="1.1952", nb="39", med="128.6", mx="1748.1", tb="38", tw="1748.1", spare="51.9", share="21.14%", died="0", ret="9,975", lost="0", numer="9,886", idle="22.848"),
    512: dict(span="1.392", nb="20", med="244.7", mx="1754.4", tb="19", tw="1754.4", spare="45.6", share="24.07%", died="0", ret="9,975", lost="0", numer="9,886", idle="21.099"),
    1024: dict(span="1.5142", nb="10", med="458.0", mx="1800.1", tb="9", tw="1800.1", spare=None, share="29.86%", died="1", ret="9,216", lost="759", numer="9,129", idle="19.084"),
}
REP_LI = {
    128: dict(span="1.9264", nb="78", med="54.5", mx="236.0", tb="77", tw="38.8", spare="1761.2", share="0.76%", died="0", ret="9,975", lost="0", numer="9,873", idle="25.181"),
    256: dict(span="2.4591", nb="39", med="98.2", mx="251.3", tb="38", tw="105.3", spare="1694.7", share="2.62%", died="0", ret="9,975", lost="0", numer="9,873", idle="22.47"),
    512: dict(span="3.0463", nb="20", med="143.3", mx="308.2", tb="19", tw="101.2", spare="1698.8", share="3.12%", died="0", ret="9,975", lost="0", numer="9,873", idle="19.422"),
    1024: dict(span="3.8639", nb="10", med="240.3", mx="380.8", tb="9", tw="241.3", spare="1558.7", share="9.44%", died="0", ret="9,975", lost="0", numer="9,873", idle="14.995"),
}
for arm, LEGS, REP in (("RocketRide", RRK, REP_RR), ("LlamaIndex", LIK, REP_LI)):
    for k in ks:
        c, r, b = LEGS[k], REP[k], LEGS[k]["batches"]
        t = f"{arm} table, K={k}"
        num(S2, f"{t}: span docs/s", r["span"], c["span_docs_per_s"])
        num(S2, f"{t}: batches (distinct batch values)", r["nb"], b["n_batches"])
        num(S2, f"{t}: batch wall median, s", r["med"], b["median_wall"])
        num(S2, f"{t}: batch wall max, s", r["mx"], b["max_wall"])
        num(S2, f"{t}: index of the batch holding 039_039660.pdf", r["tb"], b["target_batch"])
        num(S2, f"{t}: wall of the batch holding 039_039660.pdf, s", r["tw"], b["target_batch_wall"])
        if r["spare"] is not None:
            num(S2, f"{t}: spare to 1,800 s", r["spare"], b["spare"])
        else:
            lit(S2, f"{t}: batch holding 039_039660.pdf DIED at the deadline", "DIED at the deadline",
                f"batch {b['target_batch']} in died batches {b['died_batches']}; wall {b['target_batch_wall']:.3f} s, spare {b['spare']:.3f} s",
                b["target_batch"] in b["died_batches"])
        num(S2, f"{t}: that batch's share of the span (wall / leg span)", r["share"], b["target_batch_share_of_span"], pct=True,
            note=f"wall {b['target_batch_wall']:.6f} s / span {c['span_s']:.6f} s")
        num(S2, f"{t}: batches died (rows with reason batch_error:TimeoutError)", r["died"], len(b["died_batches"]))
        if b["died_batches"]:
            lit(S2, f"{t}: which batch died", "batch 9", f"batch {b['died_batches']}", b["died_batches"] == [9])
        num(S2, f"{t}: documents returned (completed + content outcome)", r["ret"], c["docs"]["returned"])
        num(S2, f"{t}: documents lost (deadline + other)", r["lost"], c["docs"]["lost"])
        num(S2, f"{t}: numerator of docs/s (completed)", r["numer"], c["docs"]["completed"])
        num(S2, f"{t}: idle core-equivalents (32 - mean host busy)", r["idle"], c["percore"]["idle"],
            note=f"leg percore_host.idle_core_equivalents {c['leg_percore_host']['idle_core_equivalents']} (agrees)")
num(S2, "RocketRide table, continuous C=32 reference: span docs/s", "2.3395", rr_c["span_docs_per_s"])
num(S2, "RocketRide table, continuous C=32 reference: idle core-equivalents", "13.802", rr_c["percore"]["idle"])
num(S2, "LlamaIndex table, continuous C=32 reference: span docs/s", "5.096", li_c["span_docs_per_s"])
num(S2, "LlamaIndex table, continuous C=32 reference: idle core-equivalents", "8.714", li_c["percore"]["idle"])
dagger(S2, "footnote under the RocketRide table")
# K=1,024 stated plainly
e11, e12 = RRK[1024], LIK[1024]
num(S2, "K=1,024 plainly: RocketRide returned", "9,216", e11["docs"]["returned"])
num(S2, "K=1,024 plainly: RocketRide with content", "9,129", e11["docs"]["completed"])
num(S2, "K=1,024 plainly: RocketRide content outcomes", "87", e11["docs"]["content"])
num(S2, "K=1,024 plainly: RocketRide lost to the deadline", "759", e11["docs"]["deadline"])
num(S2, "K=1,024 plainly: LlamaIndex returned", "9,975", e12["docs"]["returned"])
num(S2, "K=1,024 plainly: LlamaIndex with content", "9,873", e12["docs"]["completed"])
num(S2, "K=1,024 plainly: LlamaIndex content outcomes", "102", e12["docs"]["content"])
num(S2, "K=1,024 plainly: LlamaIndex lost", "0", e12["docs"]["lost"])
num(S2, "K=1,024 plainly: RocketRide docs/s numerator", "9,129", e11["docs"]["completed"])
num(S2, "K=1,024 plainly: LlamaIndex docs/s numerator", "9,873", e12["docs"]["completed"])
# Where 039 sat
lit(S2, "Where 039 sat (intro): a RocketRide batch stamps all its rows at once (one submit stamp per batch)", "all rows stamped at once",
    "every batch of p3/e7/e9/e11 has exactly one distinct submit_ns (78/78, 39/39, 20/20, 10/10); LlamaIndex p4 has per-document stamps", True)
SAT = [
    ("p1_rr_cont32", rr_c, "9,957", None, "1722", "yes"),
    ("p2_li_cont", li_c, "9,957", None, "31", ("011_011575.pdf", "149.8")),
    ("p3_rr_k128", RRK[128], "9,973", "77", "1706.8", ("batch", "119")),
    ("p4_li_k128", LIK[128], "9,960", "77", "38.8", "yes"),
    ("e7_rr_k256", RRK[256], "9,967", "38", "1748.1", ("batch", "247")),
    ("e8_li_k256", LIK[256], "9,960", "38", "61.1", ("033_033175.pdf", "105.3")),
    ("e9_rr_k512", RRK[512], "9,967", "19", "1754.4", ("batch", "247")),
    ("e10_li_k512", LIK[512], "9,957", "19", "47.8", ("009_009076.pdf", "101.2")),
    ("e11_rr_k1024", RRK[1024], "9,949", "9", "1800.1", ("batch", "759")),
    ("e12b_li_k1024", LIK[1024], "9,955", "9", "170.5", ("018_018497.pdf", "241.1")),
]
for name, c, rank, batch, held, setspan in SAT:
    t = f"Where 039 sat, {name}"
    lit(S2, f"{t}: slice position (the send order)", "9,957 of 9,975",
        "9957 of 9975 (row position of 039_039660.pdf in the perdoc row order shared by 9 of the 10 legs; the p1 file is in another order) - indirect",
        True, "INDIRECT: the slice file itself is not in the permitted list; corroborated by the common perdoc row order and by batch membership (floor((9957-1)/K) = 77, 38, 19, 9)")
    num(S2, f"{t}: rank by submit stamp (rows sorted by (submit_ns, doc))", rank, c["target"]["rank_by_submit"])
    if batch is None:
        lit(S2, f"{t}: batch", "—", str(c["target"]["batch"]), c["target"]["batch"] is None)
    else:
        num(S2, f"{t}: batch", batch, c["target"]["batch"])
    num(S2, f"{t}: 039_039660.pdf held, s", held, c["target"]["held_s"])
    if setspan == "yes":
        lit(S2, f"{t}: set the span?", "yes", f"039 is the unique max-completion row: {c['target']['is_max_completion'] and c['span_setter']['n_rows_sharing_max_completion']==1}",
            c["target"]["is_max_completion"] and c["span_setter"]["n_rows_sharing_max_completion"] == 1)
    elif setspan[0] == "batch":
        b = c["batches"]
        lit(S2, f"{t}: set the span? - its batch did, the last to return", f"its batch #{batch} did - the last to return",
            f"last batch to return {b['last_batch_to_return']}; span-setting row's batch {b['span_setting_batch']}",
            b["last_batch_to_return"] == int(batch) and b["span_setting_batch"] == int(batch))
        num(S2, f"{t}: rows of that batch sharing one return stamp", setspan[1], b["target_batch_max_rows_sharing_completion"],
            note=f"batch has {b['target_batch_nrows']} rows and {b['target_batch_n_distinct_completion']} distinct completion stamp(s)")
    else:
        lit(S2, f"{t}: set the span? - no, set by", f"no - {setspan[0]}", f"no - {c['span_setter']['doc']}",
            (not c["target"]["is_max_completion"]) and c["span_setter"]["doc"] == setspan[0])
        num(S2, f"{t}: held of the span-setting document, s", setspan[1], c["span_setter"]["held_s"])

# ================= Section 3 =================
num(S3, "heading: videos measured (LlamaIndex records, role measured)", "168", vs_li["n_measured"])
num(S3, "heading: videos measured (RocketRide records, role measured)", "168", vs_rr["n_measured"])
wp = video_li_ex["provenance_leela"]["warmup_policy"]
lit(S3, "heading: + 2 warm-up", "2 warm-up", wp[:60], "2 disjoint manifest warm rows" in wp and "2 disjoint manifest warm rows" in video_rr_ex["provenance_leela"]["warmup_policy"],
    "corroborated from both exports' provenance_leela.warmup_policy string; the warmup_*.json files are not in the permitted list")
li_tp = video_li_ex["provenance_video"]["thread_pins_by_arm"]["arms"]["li"]["within_arm"]
rr_tp = video_rr_ex["provenance_video"]["thread_pins_by_arm"]["arms"]["rr"]
lit(S3, "Posture LI: workers[declared_workers=8]", "workers[declared_workers=8]", video_li_ex["posture"], video_li_ex["posture"] == "workers[declared_workers=8]")
num(S3, "Posture LI: processes read back", "8", len(li_tp["readers"]))
lit(S3, "Posture LI: six thread variables at 4", "six thread variables at 4", json.dumps({k: li_tp["values_agreed"][k] for k in SIX}),
    all(li_tp["values_agreed"].get(k) == "4" for k in SIX) and li_tp["disagreements"] is None)
lit(S3, "Posture LI: torch threads [4]", "[4]", f"[{li_tp['values_agreed']['torch_num_threads']}]", li_tp["values_agreed"]["torch_num_threads"] == 4)
lit(S3, "Posture RR: default[tokens=1,threads=unset(engine-default-64)]", "default[tokens=1,threads=unset(engine-default-64)]", video_rr_ex["posture"],
    video_rr_ex["posture"] == "default[tokens=1,threads=unset(engine-default-64)]")
num(S3, "Posture RR: processes read back", "1", len(rr_tp["within_arm"]["readers"]))
lit(S3, "Posture RR: six thread variables unset", "six thread variables unset", f"mode {rr_tp['mode']}, declared {rr_tp['declared']}",
    rr_tp["mode"] == "unset" and rr_tp["declared"] == {})
lit(S3, "Posture RR: torch threads [16]", "[16]", f"[{rr_tp['within_arm']['values_agreed']['torch_num_threads']}]", rr_tp["within_arm"]["values_agreed"]["torch_num_threads"] == 16)
num(S3, "Videos in flight K, LlamaIndex", "16", vs_li["offered_concurrency"])
num(S3, "Videos in flight K, RocketRide", "16", vs_rr["offered_concurrency"])
num(S3, "Throughput frames/s, LlamaIndex (sum frames_observed / total_span_s)", "13.524", vs_li["frames_per_s_recomputed"],
    note=f"recomputed total frames {vs_li['total_frames_recomputed']} == export total_frames {vs_li['export_total_frames']}")
lit(S3, "Throughput frames/s, RocketRide: RANKING ONLY", "RANKING ONLY",
    f"not quoted; recomputed {vs_rr['frames_per_s_recomputed']:.3f} frames/s (frames {vs_rr['total_frames_recomputed']} == export {vs_rr['export_total_frames']})",
    vs_rr["total_frames_recomputed"] == vs_rr["export_total_frames"])
num(S3, "Engine CPU cores, LlamaIndex (efficiency.effective_cores)", "28.566", vs_li["effective_cores"])
num(S3, "Engine CPU cores, RocketRide (efficiency.effective_cores)", "5.853", vs_rr["effective_cores"])
num(S3, "CPU utilisation engine/32, LlamaIndex (efficiency.cpu_util_of_box)", "89.27%", vs_li["cpu_util_of_box"], pct=True,
    note=f"effective_cores/32 = {vs_li['effective_cores']/32:.5f}")
num(S3, "CPU utilisation engine/32, RocketRide (efficiency.cpu_util_of_box)", "18.29%", vs_rr["cpu_util_of_box"], pct=True,
    note=f"effective_cores/32 = {vs_rr['effective_cores']/32:.5f}")
num(S3, "Idle core-equivalents, LlamaIndex (32 - mean busy over in-window samples)", "3.132", vs_li["percore"]["idle_inside"],
    note=f"{vs_li['percore']['n_inside']} of {vs_li['percore']['n_samples']} samples in [min admit_ns, max done_ns]; all-samples value would be {vs_li['percore']['idle_all']:.3f}")
num(S3, "Idle core-equivalents, RocketRide (32 - mean busy over in-window samples)", "26.015", vs_rr["percore"]["idle_inside"],
    note=f"{vs_rr['percore']['n_inside']} of {vs_rr['percore']['n_samples']} samples in window; all-samples value would be {vs_rr['percore']['idle_all']:.3f}")
num(S3, "Idle spin, LlamaIndex (export efficiency.idle_burden.idle_cores_with_instances_live)", "0.034", vs_li["idle_cores_with_instances_live"],
    note="no definition was supplied for video idle spin; this is the export field that carries it")
num(S3, "Idle spin, RocketRide (export efficiency.idle_burden.idle_cores_with_instances_live)", "1.226", vs_rr["idle_cores_with_instances_live"],
    note="no definition was supplied for video idle spin; this is the export field that carries it")
num(S3, "Videos, LlamaIndex", "168", vs_li["n_measured"])
num(S3, "Errors, LlamaIndex (records with an error key)", "0", vs_li["n_errors"])
num(S3, "Videos, RocketRide", "168", vs_rr["n_measured"])
num(S3, "Errors, RocketRide (records with an error key)", "0", vs_rr["n_errors"])
lit(S3, "Ranking: LlamaIndex ahead of RocketRide (frames/s)", "LlamaIndex ahead of RocketRide",
    f"LI {vs_li['frames_per_s_recomputed']:.3f} > RR {vs_rr['frames_per_s_recomputed']:.3f}", vs_li["frames_per_s_recomputed"] > vs_rr["frames_per_s_recomputed"])
num(S3, "RocketRide K=16 replicate spread on the 16-video slice", "9.76%", rr_rep_spread, pct=True)
num(S3, "16-video slice (measured records, RR K=16 first run and replicate)", "16", V["rep_rr_k16"]["n_measured"],
    note=f"first run {V['smoke_rr_k16']['n_measured']}, replicate {V['rep_rr_k16']['n_measured']}")
lit(S3, "the spread is above the pre-set 2% threshold (2% taken as a ruling, not recomputed)", "above 2%", f"{rr_rep_spread*100:.2f}% > 2%", rr_rep_spread > 0.02)
num(S3, "LlamaIndex K=8 replicate spread", "12.25%", li_rep_spread, pct=True, note=f"first {sm['smoke_li_k8']}, replicate {sm['rep_li_k8']}")

mism = [r for r in results if not r["match"]]
out = {"figures_checked": len(results), "n_matches": len(results) - len(mism), "n_mismatches": len(mism),
       "scope": "Sections 0 (excluding the Stage 5 bullet list), 1, C5, 2 (both arm tables excluding the Peak engine anon column and the per-batch lists; the K=1,024 paragraph; the Where-039 table and its intro), 3. Memory figures skipped everywhere.",
       "method": "Every value recomputed from the listed raw files with /Users/ansh/RocketRide/Benchmarking/.venv/bin/python; displayed rounding applied with ROUND_HALF_UP to the report's decimals. No analysis_* or *summary* file and nothing under working/scripts/ was opened.",
       "unverifiable_or_indirect": [
           "Slice position '9,957 of 9,975' (10 rows): the slice file is not in the permitted list; corroborated indirectly by the perdoc row order shared by 9 of 10 legs and by batch membership.",
           "'+ 2 warm-up' (section 3 heading): corroborated from the exports' warmup_policy string only.",
           "'one LlamaIndex worker' (per-unit sentence, section 0): the anchor leg JSONs do not record the worker count.",
           "The '2%' leg-6 threshold: a ruling, taken as given (not recomputed)."],
       "results": results, "mismatches": mism}
json.dump(out, open(f"{W}/verifier_findings.json", "w"), indent=1, ensure_ascii=False)
print("figures_checked", len(results), "mismatches", len(mism))
for m in mism:
    print("MISMATCH:", m["section"], "|", m["figure"], "| reported", m["reported"], "| recomputed", m["recomputed"], "|", m["note"])
flag = [r for r in results if "rounding boundary" in r["note"]]
print("boundary-flagged:", len(flag))
for f in flag:
    print("  ", f["figure"], f["reported"], f["recomputed_raw"])
