import json, collections, statistics, os, sys

BASE = "/Users/ansh/RocketRide/Benchmarking/benchmark-A/working/results/batchsize_s4_20260921T013303Z"
OUT = "/private/tmp/claude-501/-Users-ansh-RocketRide-Benchmarking-benchmark-A/99b99d9b-386c-4d1e-8b7e-cd129b6411f0/scratchpad/verify2/work/docs_calc.json"
TARGET = "039_039660.pdf"
CONTENT = {"no_documents", "empty_extraction", "parse_failed"}

LEGS = {
    "p1_rr_cont32": ("p1_rr_cont32", "rr", "refc32_main"),
    "p2_li_cont": ("p2_li_cont", "li", "refc32_main"),
    "p2_li_cont16": ("p2_li_cont", "li", "refc16_main"),
    "p3_rr_k128": ("p3_rr_k128", "rr", "k128_main"),
    "p4_li_k128": ("p4_li_k128", "li", "k128_main"),
    "e7_rr_k256": ("e7_rr_k256", "rr", "k256_env"),
    "e8_li_k256": ("e8_li_k256", "li", "k256_env"),
    "e9_rr_k512": ("e9_rr_k512", "rr", "k512_env"),
    "e10_li_k512": ("e10_li_k512", "li", "k512_env"),
    "e11_rr_k1024": ("e11_rr_k1024", "rr", "k1024_env"),
    "e12b_li_k1024": ("e12b_li_k1024", "li", "k1024_env"),
}


def span_rate(rows):
    ok = sum(1 for r in rows if r["ok"] is True)
    span_ns = max(r["completion_ns"] for r in rows) - min(r["submit_ns"] for r in rows)
    return ok, span_ns / 1e9, ok / (span_ns / 1e9)


def p99_rate(rows):
    okrows = sorted((r for r in rows if r["ok"] is True), key=lambda r: r["completion_ns"])
    n = len(okrows)
    k = int(0.99 * n)
    t0 = min(r["submit_ns"] for r in rows)
    tk = okrows[k - 1]["completion_ns"]
    return {"n_ok": n, "k": k, "t_k_s": (tk - t0) / 1e9, "rate": k / ((tk - t0) / 1e9),
            "kth_completion_ns": tk}


def categorize(r):
    if r["ok"] is True:
        return "completed"
    reason = r.get("reason") or ""
    if reason in CONTENT:
        return "content"
    if reason.endswith("TimeoutError"):
        return "deadline"
    return "other"


res = {}
for key, (d, arm, L) in LEGS.items():
    rows = [json.loads(l) for l in open(f"{BASE}/{d}/perdoc_{arm}_{L}.jsonl")]
    leg = json.load(open(f"{BASE}/{d}/leg_{arm}_{L}.json"))
    out = {"n_rows": len(rows)}
    ok, span_s, rate = span_rate(rows)
    out.update({"ok": ok, "span_s": span_s, "span_docs_per_s": rate})
    rows_drop = [r for r in rows if r["doc"] != TARGET]
    out["n_rows_drop"] = len(rows_drop)
    ok_d, span_d, rate_d = span_rate(rows_drop)
    out.update({"ok_drop": ok_d, "span_s_drop": span_d, "span_docs_per_s_drop": rate_d})
    out["p99"] = p99_rate(rows)
    # span setter
    last = max(rows, key=lambda r: r["completion_ns"])
    maxc = last["completion_ns"]
    n_at_max = sum(1 for r in rows if r["completion_ns"] == maxc)
    out["span_setter"] = {"doc": last["doc"], "held_s": (last["completion_ns"] - last["submit_ns"]) / 1e9,
                          "n_rows_sharing_max_completion": n_at_max}
    # target row
    tr = [r for r in rows if r["doc"] == TARGET]
    assert len(tr) == 1, (key, len(tr))
    tr = tr[0]
    out["target"] = {"held_s": (tr["completion_ns"] - tr["submit_ns"]) / 1e9, "batch": tr["batch"],
                     "ok": tr["ok"], "reason": tr["reason"],
                     "is_max_completion": tr["completion_ns"] == maxc,
                     "completion_minus_p99_kth_s": (tr["completion_ns"] - out["p99"]["kth_completion_ns"]) / 1e9}
    # rank by (submit_ns, doc)
    order = sorted(rows, key=lambda r: (r["submit_ns"], r["doc"]))
    rank = [i for i, r in enumerate(order, 1) if r["doc"] == TARGET][0]
    out["target"]["rank_by_submit"] = rank
    # documents
    cat = collections.Counter(categorize(r) for r in rows)
    out["docs"] = {"completed": cat["completed"], "content": cat["content"], "deadline": cat["deadline"],
                   "other": cat["other"], "returned": cat["completed"] + cat["content"],
                   "lost": cat["deadline"] + cat["other"]}
    out["deadline_docs"] = [(r["doc"], (r["completion_ns"] - r["submit_ns"]) / 1e9, r["reason"]) for r in rows if categorize(r) == "deadline"][:5]
    out["content_set"] = sorted(r["doc"] for r in rows if categorize(r) == "content")
    # percore
    samples = [json.loads(l) for l in open(f"{BASE}/{d}/percore_{arm}_{L}.jsonl")]
    sums = [sum(s["busy"].values()) for s in samples]
    ncores = collections.Counter(len(s["busy"]) for s in samples)
    busy = sum(sums) / len(sums)
    t_list = [s["t"] for s in samples]
    out["percore"] = {"n_samples": len(samples), "ncores_per_sample": dict(ncores),
                      "mean_busy": busy, "idle": 32 - busy,
                      "t_first": min(t_list), "t_last": max(t_list),
                      "window_t0_s": leg["window"]["t0_ns"] / 1e9, "window_t1_s": leg["window"]["t1_ns"] / 1e9}
    # also samples strictly inside window (check)
    w0, w1 = leg["window"]["t0_ns"] / 1e9, leg["window"]["t1_ns"] / 1e9
    ins = [sum(s["busy"].values()) for s in samples if w0 <= s["t"] <= w1]
    out["percore"]["n_inside_window"] = len(ins)
    out["percore"]["mean_busy_inside_window"] = sum(ins) / len(ins) if ins else None
    out["leg_percore_host"] = {k: leg["percore_host"].get(k) for k in ("n_intervals", "mean_busy_cores", "idle_core_equivalents")}
    c = leg["cost"]
    out["leg_cost"] = {"engine_container_cores": c.get("engine_container_cores"), "effective_cores": c.get("effective_cores"),
                       "driver_cores": c.get("driver_cores"), "cpu_utilization": c.get("cpu_utilization"),
                       "idle_spin": c.get("idle_spin_measured", {}).get("cores"), "cpu_s_per_doc": c.get("cpu_s_per_doc"),
                       "host_total_cores": c.get("host_total_cores")}
    out["leg_documents"] = leg.get("documents")
    out["leg_throughput"] = leg.get("throughput")
    # batches
    if any(r["batch"] is not None for r in rows):
        bb = collections.defaultdict(list)
        for r in rows:
            bb[r["batch"]].append(r)
        walls = {b: (max(r["completion_ns"] for r in rs) - min(r["submit_ns"] for r in rs)) / 1e9 for b, rs in bb.items()}
        wl = [walls[b] for b in sorted(walls)]
        died = sorted(b for b, rs in bb.items() if any(r.get("reason") == "batch_error:TimeoutError" for r in rs))
        died_docs = sum(1 for r in rows if r.get("reason") == "batch_error:TimeoutError")
        tb = tr["batch"]
        tw = walls[tb]
        # rows sharing one return stamp in target batch
        tb_rows = bb[tb]
        comp_counter = collections.Counter(r["completion_ns"] for r in tb_rows)
        # batch that set the span
        span_batch = last["batch"]
        # is target batch the last to return?
        batch_last_completion = {b: max(r["completion_ns"] for r in rs) for b, rs in bb.items()}
        last_batch = max(batch_last_completion, key=batch_last_completion.get)
        out["batches"] = {"n_batches": len(bb), "sizes": dict(collections.Counter(len(rs) for rs in bb.values())),
                          "median_wall": statistics.median(wl), "max_wall": max(wl),
                          "walls": {str(b): walls[b] for b in sorted(walls)},
                          "target_batch": tb, "target_batch_wall": tw, "spare": 1800 - tw,
                          "target_batch_share_of_span": tw / span_s,
                          "died_batches": died, "died_docs": died_docs,
                          "target_batch_nrows": len(tb_rows),
                          "target_batch_n_distinct_completion": len(comp_counter),
                          "target_batch_max_rows_sharing_completion": max(comp_counter.values()),
                          "span_setting_batch": span_batch, "last_batch_to_return": last_batch,
                          "n_distinct_submit_in_target_batch": len(set(r["submit_ns"] for r in tb_rows))}
    res[key] = out
    print(key, "done", file=sys.stderr)

json.dump(res, open(OUT, "w"), indent=1, default=str)
print("written", OUT)
