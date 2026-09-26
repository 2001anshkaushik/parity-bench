#!/usr/bin/env python3
"""P7 GATE CONTROLS: before launch, every gate the P7 chain decides from runs WHOLE, in its real runtime (the box's ~/.venv
Python; docker for G_alone), against a known-good target that must PASS (rc 0) and a known-bad target that must FAIL
(rc != 0). For G_tier2 each control must also produce its expected READING. The chain's 'run' stage refuses unless the
latest record says all_pass. Targets: COMMITTED legs (P0, P3, P5, P6, batch-size smoke; linked, never written; a mutated
target is a COPY in the scratch base) and the control stage's real leg p7ctl_cap.

    ~/.venv/bin/python working/scripts/p7_gate_controls.py <campaign_dir_abs>        (P7_CTL_NO_DOCKER=1: laptop dry run)
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PY = sys.executable
GATES = ROOT / "working" / "scripts" / "p7_gates.py"
RES = ROOT / "working" / "results"
P0, P3, P5 = RES / "parity_p0_20260923T083031Z", RES / "parity_p3_20260925T035027Z", RES / "parity_p5_20260925T141647Z"
P6 = RES / "parity_p6_20260925T175225Z"
BS = RES / "batchsize_smoke_20260920T113000Z" / "video_n16"
FMAN = P3 / "p3b_frames_manifest.json"
RESULTS: list = []
N = [0]
LIGHT = shutil.ignore_patterns("percore.jsonl", "fsstream_*", "collector_*", "*_stamps.jsonl", "memstat.jsonl", "dockerlog_*")


def run(args):
    return subprocess.run(args, capture_output=True, text=True)


def last(p):
    s = ((p.stdout or "") + (p.stderr or "")).strip().splitlines()
    return s[-1] if s else ""


def ctl(gate, kind, want, rc, detail="", reading_want=None, reading_got=None):
    ok = ((rc == 0) == want) and (reading_want is None or reading_want == reading_got)
    RESULTS.append({"gate": gate, "control": kind, "expect": ("PASS (rc 0)" if want else "FAIL (rc != 0)") + (f", reading {reading_want}" if reading_want else ""),
                    "got": f"{'PASS' if rc == 0 else 'FAIL'} (rc {rc})" + (f", reading {reading_got}" if reading_want else ""), "pass": ok, "detail": detail[:600]})
    print(f"  {'ok  ' if ok else 'BAD '}  {gate} [{kind}] expect {'PASS' if want else 'FAIL'}{' / ' + reading_want if reading_want else ''}, got rc {rc}"
          f"{' / ' + str(reading_got) if reading_want else ''}  {detail[:120]}")


def space(base, links):
    N[0] += 1
    c = base / f"c{N[0]:02d}"
    c.mkdir()
    for name, src in links.items():
        (c / name).symlink_to(src, target_is_directory=True)
    return c


def gate(*a):
    return run([PY, str(GATES), *[str(x) for x in a]])


def imgid(tag):
    return run(["docker", "image", "inspect", "-f", "{{.Id}}", tag]).stdout.strip()


def mutate_records(src: Path, dst: Path, changes):
    """Copy a leg (light) and change frame_scores[i][0] of the named videos in its records by +0.001 (a real, visible shift)."""
    shutil.copytree(src, dst, ignore=LIGHT)
    rf = sorted(dst.glob("records_*.jsonl"))[0]
    out = []
    for line in rf.read_text().splitlines():
        if line.strip():
            r = json.loads(line)
            for v, i in changes:
                if r.get("video") == v and r.get("role") == "measured" and r.get("frame_scores"):
                    r["frame_scores"][i][0] += 0.001
            out.append(json.dumps(r))
    rf.write_text("\n".join(out) + "\n")


def reading_of(space_dir: Path):
    f = space_dir / "gates" / "G_tier2.json"
    return json.loads(f.read_text()).get("reading") if f.exists() else None


def main() -> int:
    camp = Path(sys.argv[1])
    dry = os.environ.get("P7_CTL_NO_DOCKER") == "1"
    n = 1 + len(list(camp.glob("gate_controls.json"))) + len(list(camp.glob("gate_controls_run*.json")))
    base = Path(os.environ.get("P7_CTL_BASE", str(Path.home()))) / (f"p7_gate_controls_{camp.name}" + ("" if n == 1 else f"_run{n}"))
    if base.exists():
        print(f"REFUSED: {base} exists"); return 2
    base.mkdir(parents=True)
    CAP = camp / "p7ctl_cap"
    T16, L16, WRR, WLI = P6 / "p6ctl_p5t16", P6 / "p6ctl_lit16", P6 / "p6ctl_warm_rr", P6 / "p6ctl_warm_li"
    ids = {} if dry else {t: imgid(t) for t in ("rr:patched-video", "rr:p5-infer", "li:video")}
    I = lambda t: ids.get(t, "DRY")  # noqa: E731
    t0 = time.time()

    print("G_memstat")
    ctl("G_memstat", "positive: P5 p5a_stock16_1", True, gate("memstat", space(base, {"L": P5 / "p5a_stock16_1"}), "L").returncode)
    ctl("G_memstat", "null: batchsize_smoke rr_k16 (no memory sampler)", False, gate("memstat", space(base, {"L": BS / "rr_k16"}), "L").returncode)

    print("G_d0")
    for arm, kind, tgt, want in (("rr", "positive: P5 p5a_p5k16_1", P5 / "p5a_p5k16_1", True),
                                 ("rr", "positive: P6's control leg p6ctl_p5t16 (out of box)", T16, True),
                                 ("rr", "positive: the control leg p7ctl_cap (stock, capture on)", CAP, True),
                                 ("rr", "null: batchsize_smoke rr_k16 (no on-token D0: absence)", BS / "rr_k16", False),
                                 ("li", "positive: P5 p5a_li16_1", P5 / "p5a_li16_1", True), ("li", "positive: P6's control leg p6ctl_lit16", L16, True),
                                 ("li", "null: batchsize_smoke li_k16 (eight LlamaIndex containers)", BS / "li_k16", False)):
        p = gate("d0", space(base, {"L": tgt}), "L", arm); ctl(f"G_d0 {arm}", kind, want, p.returncode, last(p))
    c = space(base, {}); shutil.copytree(P5 / "p5a_p5k16_1", c / "L", ignore=shutil.ignore_patterns("percore.jsonl", "fsstream_*", "collector_*"))
    ef = sorted((c / "L").glob("export_*.json"))[0]; j = json.loads(ef.read_text())
    p0 = j.get("p0") or j["provenance_video"]["p0"]
    for k in p0["d0_post"]["root_modules_with_params"]:
        if "LWDETR" in k:
            p0["d0_post"]["root_modules_with_params"][k]["count"] = 2
    ef.write_text(json.dumps(j))
    p = gate("d0", c, "L", "rr"); ctl("G_d0 rr", "null: a copy of p5a_p5k16_1 whose post-leg D0 counts TWO LWDETR instances", False, p.returncode, last(p))

    print("G_cell")
    for label, tgt, fl, k, t, nn, tag, env, want, kind in (
            ("p5 T=4", P5 / "p5a_p5k16_1", "p5", 16, 4, 16, "rr:p5-infer", "set", True, "positive: P5 p5a_p5k16_1"),
            ("p5 T=4", T16, "p5", 2, 4, 2, "rr:p5-infer", "set", False, "null: p6ctl_p5t16 against T=4 (torch 16, the six vars unset)"),
            ("p5 T=16 unset", T16, "p5", 2, 16, 2, "rr:p5-infer", "unset", True, "positive: P6's control leg p6ctl_p5t16"),
            ("p5 T=16 unset", P5 / "p5a_p5k16_1", "p5", 16, 16, 16, "rr:p5-infer", "unset", False, "null: P5 p5a_p5k16_1 against T=16 unset (torch 4, vars set)"),
            ("li T=16", L16, "li", 2, 16, 2, "li:video", "set", True, "positive: P6's control leg p6ctl_lit16"),
            ("li T=16", P5 / "p5a_li16_1", "li", 16, 16, 16, "li:video", "set", False, "null: P5 p5a_li16_1 against T=16 (torch 4)"),
            ("stock T=4", P5 / "p5a_stock16_1", "stock", 16, 4, 16, "rr:patched-video", "set", True, "positive: P5 p5a_stock16_1"),
            ("stock T=4", P5 / "p5a_p5k16_1", "stock", 16, 4, 16, "rr:patched-video", "set", False, "null: P5 p5a_p5k16_1 against the stock spec (image, stamps)"),
            ("stock T=4 K=1", CAP, "stock", 1, 4, 1, "rr:patched-video", "set", True, "positive: the control leg p7ctl_cap"),
            ("stock T=4 K=1", CAP, "p5", 1, 4, 1, "rr:p5-infer", "set", False, "null: p7ctl_cap against the P5 spec (image, stamps)"),
            ("li T=4", P5 / "p5a_li16_1", "li", 16, 4, 16, "li:video", "set", True, "positive: P5 p5a_li16_1"),
            ("li T=4", BS / "li_k16", "li", 16, 4, 16, "li:video", "set", False, "null: batchsize_smoke li_k16 (no read-back)")):
        p = gate("cell", space(base, {"L": tgt}), "L", fl, k, t, nn, I(tag), env); ctl(f"G_cell {label}", kind, want, p.returncode, last(p))

    print("G_warm")
    for kind, tgt, s, cc, want in (("positive: P6's control leg p6ctl_warm_rr (2 at 2)", WRR, 2, 2, True),
                                   ("positive: P6's control leg p6ctl_warm_li (2 at 2)", WLI, 2, 2, True),
                                   ("positive: P6-B p6b_rr_startwarm (16 at 16)", P6 / "p6b_rr_startwarm", 16, 16, True),
                                   ("null: P5 p5a_p5k16_1 (the default warm policy, nothing declared)", P5 / "p5a_p5k16_1", 2, 2, False),
                                   ("null: p6ctl_warm_rr against 16 at 16", WRR, 16, 16, False)):
        p = gate("warm", space(base, {"L": tgt}), "L", s, cc); ctl("G_warm", kind, want, p.returncode, last(p))

    print("G_canary")
    for kind, tgt, want in (("positive: P5 p5c_can_1 (committed canary)", P5 / "p5c_can_1", True),
                            ("null: P3 p3b_a_1 (the same bench over all three videos)", P3 / "p3b_a_1", False)):
        p = gate("canary", space(base, {"L": tgt}), "L", FMAN, "v00_EN2001a"); ctl("G_canary", kind, want, p.returncode, last(p))

    print("G_correct")
    for kind, a, b, want in (("positive: P0 v1_rr_t4_a vs v1_rr_t4_b (identical 16/16)", P0 / "v1_rr_t4_a", P0 / "v1_rr_t4_b", True),
                             ("positive (the P7-C reference form, an absolute path): P0 v1_rr_def_b vs v1_rr_def_a (identical 16/16)", P0 / "v1_rr_def_b", None, True),
                             ("null: P0 v1_rr_def_a vs v1_rr_t4_a (T=16 vs T=4: differs on 16/16)", P0 / "v1_rr_def_a", P0 / "v1_rr_t4_a", False),
                             ("null: P3 p3b_c_1 vs p3b_c_2 (identical but 3 videos)", P3 / "p3b_c_1", P3 / "p3b_c_2", False)):
        if b is None:
            p = gate("correct", space(base, {"A": a}), "G_correct", "A", str(P0 / "v1_rr_def_a"))
        else:
            p = gate("correct", space(base, {"A": a, "B": b}), "G_correct", "A", "B")
        ctl("G_correct", kind, want, p.returncode, last(p))

    print("G_detcap")
    p = gate("detcap", space(base, {"L": CAP}), "L"); ctl("G_detcap", "positive: the control leg p7ctl_cap (capture on)", True, p.returncode, last(p))
    p = gate("detcap", space(base, {"L": P6 / "p6a_stock16_1"}), "L"); ctl("G_detcap", "null: P6 p6a_stock16_1 (no capture file)", False, p.returncode, last(p))
    if CAP.is_dir():
        c = space(base, {}); shutil.copytree(CAP, c / "L", ignore=LIGHT)
        cf = sorted((c / "L").glob("detections_*.jsonl"))[0]
        rows = [json.loads(x) for x in cf.read_text().splitlines() if x.strip()]
        fi = next(i for i, f in enumerate(rows[0]["frames"]) if f)
        rows[0]["frames"][fi][0]["score"] += 1e-9
        cf.write_text("".join(json.dumps(r) + "\n" for r in rows))
        p = gate("detcap", c, "L"); ctl("G_detcap", "null: a copy of p7ctl_cap with one captured score changed by 1e-9", False, p.returncode, last(p))
    else:
        ctl("G_detcap", "null: a mutated copy of p7ctl_cap", False, 0, "the control leg p7ctl_cap is absent — NOT RUN, counted as not as expected")

    print("G_tier2 (the Tier 1 reading) on P6-A's committed legs as the four Tier 1 runs")
    vids = sorted({json.loads(x)["video"] for x in sorted((P6 / "p6a_stock16_1").glob("records_*.jsonl"))[0].read_text().splitlines()
                   if x.strip() and json.loads(x).get("role") == "measured"})
    va, vb, vc = vids[0], vids[1], vids[2]
    fr = f"{va}:1,{vb}:0"
    legs = {"s1": P6 / "p6a_stock16_1", "s2": P6 / "p6a_stock16_2", "p1": P6 / "p6a_p5k16_1", "p2": P6 / "p6a_p5k16_2"}
    ref = str(P6 / "p6a_stock16_1")

    def tier_ctl(kind, mut, want_reading):
        links = {k: v for k, v in legs.items() if k not in mut}
        c = space(base, links)
        for k, changes in mut.items():
            mutate_records(legs[k], c / k, changes)
        p = gate("tier", c, "s1", "s2", "p1", "p2", fr, vc, ref)
        ctl("G_tier2", kind, want_reading == "CONDITION-DEPENDENT", p.returncode, last(p), want_reading, reading_of(c))
    tier_ctl(f"positive: all four identical (named frames {fr}, control {vc})", {}, "CONDITION-DEPENDENT")
    tier_ctl("null: one stock run shifted on a named frame", {"s2": [(va, 1)]}, "STOCK VARIES")
    tier_ctl("null: both prototype runs shifted on both named frames", {"p1": [(va, 1), (vb, 0)], "p2": [(va, 1), (vb, 0)]}, "PROTOTYPE SHIFTS")
    tier_ctl("null: the control video shifted in one prototype run", {"p2": [(vc, 2)]}, "UNREADABLE")

    if dry:
        print("NO_DOCKER dry run: G_alone skipped; all_pass forced false")
    else:
        print("G_alone")
        p = gate("alone"); ctl("G_alone", "positive: no container on the box", True, p.returncode, last(p))
        mk = run(["docker", "create", "--name", "p7_ctl_dummy", "--entrypoint", "true", "li:video"])
        p = gate("alone"); run(["docker", "rm", "p7_ctl_dummy"])
        ctl("G_alone", "null: one created container present", False, p.returncode, (last(p) + " " + mk.stderr.strip())[:300])

    targets = all(x.is_dir() for x in (CAP, T16, L16, WRR, WLI))
    all_pass = all(x["pass"] for x in RESULTS) and targets and not dry
    rec = {"label": "P7 gate controls: every gate run whole in its real runtime against a positive control (must PASS) and a null control (must FAIL), before launch; G_tier2's controls must also give their expected reading",
           "run": n, "run_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
           "boot_id": Path("/proc/sys/kernel/random/boot_id").read_text().strip() if Path("/proc/sys/kernel/random/boot_id").exists() else None,
           "python": PY, "dry_run_no_docker": dry, "seconds": round(time.time() - t0, 1), "control_targets_present": targets, "image_ids": ids,
           "controls": RESULTS, "n": len(RESULTS), "n_pass": sum(x["pass"] for x in RESULTS), "all_pass": all_pass}
    out = camp / ("gate_controls_DRYRUN.json" if dry else ("gate_controls.json" if n == 1 else f"gate_controls_run{n}.json"))
    if dry:
        print(json.dumps({k: rec[k] for k in ("n", "n_pass", "all_pass")}))
        return 0 if rec["n_pass"] == rec["n"] else 1
    with open(out, "x") as f:
        json.dump(rec, f, indent=1); f.write("\n")
    print(f"\ngate controls: {rec['n_pass']} of {rec['n']} as expected -> all_pass={all_pass} ({out.name})")
    return 0 if all_pass else 1


if __name__ == "__main__":
    sys.exit(main())
