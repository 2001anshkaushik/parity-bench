#!/usr/bin/env python3
"""P7 laptop test of the driver's opt-in detection capture (--keep-detections) and of the P7-B tier classifier, with null
controls. Through the driver's real run_leg: with capture OFF no capture file is written and no record carries the private
key; with capture ON every measured video gets one capture row (label, score, box per detection) and the records are
identical to the OFF run's except the timing fields. G_detcap passes on a clean capture and fails on a mutated one (null
controls: a changed score, a dropped frame, no capture file). The tier classifier returns each pre-registered reading on
synthetic legs built with the driver's own record_from_rr, including a BOX-ONLY difference (visible only in the capture).

    p7_detcap_test.py  -> exit 0 iff every check passes
"""
from __future__ import annotations

import asyncio
import copy
import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "working" / "video"))
sys.path.insert(0, str(ROOT / "working" / "scripts"))
import driver_video as drv  # noqa: E402
from harness.jsonl_stream import JsonlWriter  # noqa: E402

FAILS = []
TIMING = {"enqueue_ns", "admit_ns", "done_ns", "wall_s", "read_s"}


def check(name, ok, detail=""):
    if not ok:
        FAILS.append(name)
    print(f"  {'ok  ' if ok else 'FAIL'} {name}" + (f"  {detail}" if not ok else ""))


def det(label, score, x1, y1, x2, y2):
    return {"label": label, "score": score, "box": {"x1": x1, "y1": y1, "x2": x2, "y2": y2},
            "centroid": {"x": (x1 + x2) / 2, "y": (y1 + y2) / 2}}


def video_frames(seed):
    return [[det("person", 0.9 - 0.01 * seed - 0.001 * f, 10.0 + f, 20.0, 110.0, 220.0), det("chair", 0.45, 5.0, 6.0, 7.0, 8.0 + seed)]
            for f in range(4)]


def result_of(frames):
    text = "\n".join(json.dumps(fr) for fr in frames)
    return {"documents": [{"page_content": text, "metadata": {"chunkId": 0}, "embedding": [0.1, 0.2, 0.3]}]}


class FakeArm:
    name = "rocketride_video"

    def __init__(self, vids):
        self.vids = vids

    async def process(self, path, name):
        await asyncio.sleep(0.001)
        return drv.record_from_rr(result_of(self.vids[name]))


def leg_run(tmp, vids, capture):
    d = tmp / ("on" if capture else "off")
    d.mkdir()
    corpus = tmp / "corpus"
    corpus.mkdir(exist_ok=True)
    rows = []
    for v in vids:
        (corpus / v).write_bytes(v.encode() * 10)
        rows.append({"file": v, "role": "measured", "expected_frames_measured": 4, "video_s": 60.0})
    drv.DETCAP_PATH = (d / "detections_test.jsonl") if capture else None
    try:
        with JsonlWriter(d / "records_test.jsonl") as w:
            asyncio.run(drv.run_leg(FakeArm(vids), rows, "blast", 2, corpus, w, set(), 15))
    finally:
        drv.DETCAP_PATH = None
    return d


def make_leg(base, name, vids, capture=True):
    """A leg dir the P0/P7 readers accept: records (from record_from_rr), a minimal export, and the capture."""
    d = base / name
    d.mkdir()
    drv.DETCAP_PATH = (d / "detections_x.jsonl") if capture else None
    try:
        total = 0
        with open(d / "records_x.jsonl", "w") as f:
            for v, frames in vids.items():
                rec = {"video": v, "role": "measured", "admit_ns": 1, "done_ns": 2}
                rec.update(drv.record_from_rr(result_of(frames)))
                total += rec["frames_observed"]
                drv._detcap_take(rec)
                f.write(json.dumps(rec) + "\n")
    finally:
        drv.DETCAP_PATH = None
    (d / "export_x.json").write_text(json.dumps({"throughput": {"total_frames": total, "total_span_s": 10.0}, "efficiency": {}}))
    return d


def main() -> int:
    import p7_gates  # noqa: E402
    import p7_analyse as pa  # noqa: E402
    vids = {"a.avi": video_frames(1), "b.avi": video_frames(2), "c.avi": video_frames(3)}
    with tempfile.TemporaryDirectory() as t:
        tmp = Path(t)
        print("driver capture through run_leg")
        off, on = leg_run(tmp, vids, False), leg_run(tmp, vids, True)
        check("capture OFF writes no capture file (null control)", not list(off.glob("detections_*")))
        r_off = [json.loads(x) for x in (off / "records_test.jsonl").read_text().splitlines()]
        r_on = [json.loads(x) for x in (on / "records_test.jsonl").read_text().splitlines()]
        check("no record carries the private key", all("_detections" not in r for r in r_off + r_on))
        strip = lambda rs: sorted((json.dumps({k: v for k, v in r.items() if k not in TIMING}, sort_keys=True) for r in rs))  # noqa: E731
        check("records identical ON vs OFF (timing fields aside)", strip(r_off) == strip(r_on))
        caps = [json.loads(x) for x in (on / "detections_test.jsonl").read_text().splitlines()]
        check("one capture row per measured video", sorted(c["video"] for c in caps) == sorted(vids) and all(c["role"] == "measured" for c in caps))
        check("capture holds the node's detections with boxes", all(c["frames"] == vids[c["video"]] for c in caps))
        check("record scores are the capture's scores", all([[d["score"] for d in f] for f in c["frames"]] ==
                                                            next(r for r in r_on if r["video"] == c["video"])["frame_scores"] for c in caps))
        p = subprocess.run([sys.executable, str(ROOT / "working" / "video" / "driver_video.py"), "--arm", "llamaindex", "--leg", "blast",
                            "--keep-detections"], capture_output=True, text=True)
        check("--keep-detections refused on the LlamaIndex arm", "--keep-detections is the rocketride arm only" in (p.stdout + p.stderr),
              (p.stdout + p.stderr)[-300:])

        print("G_detcap")
        camp = tmp / "camp"
        camp.mkdir()
        make_leg(camp, "good", vids)
        check("G_detcap positive: a clean capture PASSES", p7_gates.detcap(camp, "good") == 0)
        g = make_leg(camp, "badscore", vids)
        cf = g / "detections_x.jsonl"
        rows = [json.loads(x) for x in cf.read_text().splitlines()]
        rows[0]["frames"][1][0]["score"] += 1e-9
        cf.write_text("".join(json.dumps(r) + "\n" for r in rows))
        check("G_detcap null: one score changed by 1e-9 FAILS", p7_gates.detcap(camp, "badscore") == 1)
        g = make_leg(camp, "dropframe", vids)
        cf = g / "detections_x.jsonl"
        rows = [json.loads(x) for x in cf.read_text().splitlines()]
        rows[1]["frames"].pop()
        cf.write_text("".join(json.dumps(r) + "\n" for r in rows))
        check("G_detcap null: one frame dropped FAILS", p7_gates.detcap(camp, "dropframe") == 1)
        make_leg(camp, "nocap", vids, capture=False)
        check("G_detcap null: no capture file is EVIDENCE MISSING", p7_gates.detcap(camp, "nocap") == 2)

        print("P7-B tier classifier (synthetic legs; named frames a.avi#1, b.avi#0; control c.avi)")
        fr, ctl = {"a.avi": 1, "b.avi": 0}, "c.avi"

        def boxshift(v, frames_to_move, dx=0.01):
            out = copy.deepcopy(v)
            for vid, i in frames_to_move:
                out[vid][i][0]["box"]["x1"] += dx
            return out

        def scenario(name, s1, s2, p1, p2, ref=None):
            base = tmp / f"t1_{name}"
            base.mkdir()
            for n, v in (("s1", s1), ("s2", s2), ("p1", p1), ("p2", p2)):
                make_leg(base, n, v)
            r = make_leg(base, "ref", ref or s1, capture=False)
            return pa.tier1(base, legs={"stock": ("s1", "s2"), "p5": ("p1", "p2")}, frames=fr, control=ctl, ref=r)["reading"]
        both, one = [("a.avi", 1), ("b.avi", 0)], [("a.avi", 1)]
        check("all four agree -> CONDITION-DEPENDENT", scenario("cd", vids, vids, vids, vids) == "CONDITION-DEPENDENT")
        shifted = boxshift(vids, both)
        check("prototype box-only shift on both frames -> PROTOTYPE SHIFTS", scenario("ps", vids, vids, shifted, shifted) == "PROTOTYPE SHIFTS")
        s1f = boxshift(vids, one)
        check("prototype on one frame -> PROTOTYPE SHIFTS ON ONE FRAME", scenario("ps1", vids, vids, s1f, s1f) == "PROTOTYPE SHIFTS ON ONE FRAME")
        check("stock differs from itself (box only) -> STOCK VARIES", scenario("sv", vids, boxshift(vids, one), vids, vids) == "STOCK VARIES")
        check("control differs in one run -> UNREADABLE", scenario("ur", vids, vids, vids, boxshift(vids, [("c.avi", 2)])) == "UNREADABLE")
        check("prototype unstable -> UNCLASSIFIED", scenario("uc", vids, vids, shifted, vids) == "UNCLASSIFIED")
        other = copy.deepcopy(vids)
        other["a.avi"][1][0]["score"] -= 0.002
        check("stock stable but not the banked output, prototype shifts -> UNCLASSIFIED (not PROTOTYPE SHIFTS)",
              scenario("uref", vids, vids, shifted, shifted, ref=other) == "UNCLASSIFIED")
        d = pa.deltas(pa.frame(pa.run_of(tmp / "t1_ps" / "p1"), "a.avi", 1), pa.frame(pa.run_of(tmp / "t1_ps" / "s1"), "a.avi", 1))
        check("S5-B Tier 2 comparator runs on the captures and sees the 0.01 px box shift",
              abs(d["s5b_tier2"]["max_box_delta_px"] - 0.01) < 1e-9 and d["s5b_tier2"]["ok"] is False, json.dumps(d)[:300])
    print(f"p7_detcap_test: {'PASS' if not FAILS else 'FAIL ' + ', '.join(FAILS)}")
    return 0 if not FAILS else 1


if __name__ == "__main__":
    sys.exit(main())
