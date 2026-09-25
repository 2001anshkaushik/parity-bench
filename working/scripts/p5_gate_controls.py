#!/usr/bin/env python3
"""P5 GATE CONTROLS: before launch, every gate runs WHOLE, in its real runtime (the box's ~/.venv Python for the chain gates;
the engine's own Python inside each image for the in-image check; docker for G_alone), against a known-good target that
must PASS (rc 0) and a known-bad target that must FAIL (rc != 0). The chain's 'run' stage refuses unless the latest record
says all_pass. Targets are COMMITTED legs (linked, never written) and the control-stage legs p5ctl_p5, p5ctl_stock,
p5ctl_li and p5ctl_canary (real legs through the chain's own leg() and canary()).

    ~/.venv/bin/python working/scripts/p5_gate_controls.py <campaign_dir_abs>        (P5_CTL_NO_DOCKER=1: laptop dry run)
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PY = sys.executable
GATES = ROOT / "working" / "scripts" / "p5_gates.py"
RES = ROOT / "working" / "results"
P0, P2, P3, P4 = (RES / "parity_p0_20260923T083031Z", RES / "parity_p2_20260924T160106Z",
                  RES / "parity_p3_20260925T035027Z", RES / "parity_p4_20260925T092942Z")
BS = RES / "batchsize_smoke_20260920T113000Z" / "video_n16"
FMAN = P3 / "p3b_frames_manifest.json"
SRC = ROOT / "working" / "nodes" / "p5_infer_src"
FRAME = Path.home() / "p3b_frames_parity_p3_20260925T035027Z" / "v00_EN2001a" / "f_000001.png"
RESULTS: list = []
N = [0]


def run(args):
    return subprocess.run(args, capture_output=True, text=True)


def last(p):
    s = ((p.stdout or "") + (p.stderr or "")).strip().splitlines()
    return s[-1] if s else ""


def ctl(gate, kind, want_pass, rc, detail=""):
    ok = (rc == 0) == want_pass
    RESULTS.append({"gate": gate, "control": kind, "expect": "PASS (rc 0)" if want_pass else "FAIL (rc != 0)",
                    "got": f"{'PASS' if rc == 0 else 'FAIL'} (rc {rc})", "pass": ok, "detail": detail[:600]})
    print(f"  {'ok  ' if ok else 'BAD '}  {gate} [{kind}] expect {'PASS' if want_pass else 'FAIL'}, got rc {rc}  {detail[:140]}")


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


def p5_fixture(dst: Path, src: Path):
    """A committed P4 RR leg re-expressed as a P5 leg: its P1 stamps written in the P5 stamp schema (the gate code reads
    only the schema; the leg's records and export are the committed ones)."""
    shutil.copytree(src, dst, ignore=shutil.ignore_patterns("percore.jsonl", "fsstream_*", "collector_*"))
    rows = [json.loads(x) for x in (src / "p1_stamps.jsonl").read_text().splitlines() if x.strip()]
    with open(dst / "p5_stamps.jsonl", "w") as f:
        for r in rows:
            f.write(json.dumps(dict(r, kind="frame", queue_wait=r.get("lock_wait"), infer_held=r.get("lock_held"), handoff=0.0,
                                    qdepth=0, infer_tid=1)) + "\n")


def main() -> int:
    camp = Path(sys.argv[1])
    dry = os.environ.get("P5_CTL_NO_DOCKER") == "1"
    n = 1 + len(list(camp.glob("gate_controls.json"))) + len(list(camp.glob("gate_controls_run*.json")))
    base = Path(os.environ.get("P5_CTL_BASE", str(Path.home()))) / (f"p5_gate_controls_{camp.name}" + ("" if n == 1 else f"_run{n}"))
    if base.exists():
        print(f"REFUSED: {base} exists"); return 2
    base.mkdir(parents=True)
    CP5, CST, CLI, CCAN = camp / "p5ctl_p5", camp / "p5ctl_stock", camp / "p5ctl_li", camp / "p5ctl_canary"
    ids = {} if dry else {t: imgid(t) for t in ("rr:patched-video", "rr:p5-infer", "li:video")}
    t0 = time.time()

    print("G_memstat")
    ctl("G_memstat", "positive: P4 p4a_rr16_1", True, gate("memstat", space(base, {"L": P4 / "p4a_rr16_1"}), "L").returncode)
    ctl("G_memstat", "null: batchsize_smoke rr_k16 (no memory sampler)", False, gate("memstat", space(base, {"L": BS / "rr_k16"}), "L").returncode)

    print("G_d0 rr (P4's rule plus exactly one LWDETR, pre and post)")
    for kind, tgt, want in (("positive: P4 p4a_rr16_1", P4 / "p4a_rr16_1", True), ("positive: the control leg p5ctl_p5 (rr:p5-infer)", CP5, True),
                            ("null: batchsize_smoke rr_k16 (no on-token D0: absence)", BS / "rr_k16", False)):
        p = gate("d0", space(base, {"L": tgt}), "L", "rr"); ctl("G_d0 rr", kind, want, p.returncode, last(p))
    c = space(base, {}); shutil.copytree(P4 / "p4a_rr16_1", c / "L", ignore=shutil.ignore_patterns("percore.jsonl", "fsstream_*", "collector_*"))
    (c / "L" / "MANDATE_VIOLATION.json").write_text('{"control": true}')
    p = gate("d0", c, "L", "rr"); ctl("G_d0 rr", "null: a copy of p4a_rr16_1 holding MANDATE_VIOLATION.json", False, p.returncode, last(p))
    c = space(base, {}); shutil.copytree(P4 / "p4a_rr16_1", c / "L", ignore=shutil.ignore_patterns("percore.jsonl", "fsstream_*", "collector_*"))
    ef = sorted((c / "L").glob("export_*.json"))[0]; j = json.loads(ef.read_text())
    p0 = j.get("p0") or j["provenance_video"]["p0"]
    for k in p0["d0_post"]["root_modules_with_params"]:
        if "LWDETR" in k:
            p0["d0_post"]["root_modules_with_params"][k]["count"] = 2
    ef.write_text(json.dumps(j))
    p = gate("d0", c, "L", "rr"); ctl("G_d0 rr", "null: a copy of p4a_rr16_1 whose post-leg D0 counts TWO LWDETR instances", False, p.returncode, last(p))
    print("G_d0 li")
    for kind, tgt, want in (("positive: P4 p4a_li16_1", P4 / "p4a_li16_1", True), ("positive: the control leg p5ctl_li", CLI, True),
                            ("null: batchsize_smoke li_k16 (eight LlamaIndex containers)", BS / "li_k16", False)):
        p = gate("d0", space(base, {"L": tgt}), "L", "li"); ctl("G_d0 li", kind, want, p.returncode, last(p))

    print("G_cell")
    specs = [("stock", CST, "stock", 2, 2, "rr:patched-video", True, "positive: the control leg p5ctl_stock"),
             ("p5", CP5, "p5", 2, 2, "rr:p5-infer", True, "positive: the control leg p5ctl_p5"),
             ("li", CLI, "li", 2, 2, "li:video", True, "positive: the control leg p5ctl_li"),
             ("stock", CP5, "stock", 2, 2, "rr:patched-video", False, "null: p5ctl_p5 against the STOCK spec (image, stamps)"),
             ("p5", CST, "p5", 2, 2, "rr:p5-infer", False, "null: p5ctl_stock against the P5 spec (image, node)"),
             ("stock", CST, "stock", 1, 2, "rr:patched-video", False, "null: p5ctl_stock against K=1 (two in flight)"),
             ("li", BS / "li_k16", "li", 16, 16, "li:video", False, "null: batchsize_smoke li_k16 (no read-back, no image record)")]
    for label, tgt, fl, k, nn, tag, want, kind in specs:
        p = gate("cell", space(base, {"L": tgt}), "L", fl, k, 4, nn, ids.get(tag, "DRY"))
        ctl(f"G_cell {label}", kind, want, p.returncode, last(p))

    print("G_canary")
    for kind, tgt, want in (("positive: the control canary p5ctl_canary", CCAN, True),
                            ("null: P3 p3b_a_1 (the same bench over all three videos)", P3 / "p3b_a_1", False)):
        p = gate("canary", space(base, {"L": tgt}), "L", FMAN, "v00_EN2001a"); ctl("G_canary", kind, want, p.returncode, last(p))

    print("G_correct")
    for kind, a, b, want in (("positive: P0 v1_rr_t4_a vs v1_rr_t4_b (identical 16/16)", P0 / "v1_rr_t4_a", P0 / "v1_rr_t4_b", True),
                             ("null: P0 v1_rr_def_a vs v1_rr_t4_a (T=16 vs T=4: differs on 16/16)", P0 / "v1_rr_def_a", P0 / "v1_rr_t4_a", False),
                             ("null: P3 p3b_c_1 vs p3b_c_2 (identical but 3 videos)", P3 / "p3b_c_1", P3 / "p3b_c_2", False)):
        p = gate("correct", space(base, {"A": a, "B": b}), "G_correct", "A", "B"); ctl("G_correct", kind, want, p.returncode, last(p))

    print("G_smoke_P5B (S1 AND S2 pooled, correctness first) on committed P4 legs re-expressed as P5 cells")
    for kind, p16, p1, want in (("positive: P5 K=16 cells = P4's stock K=1 legs (no slowdown, faster than stock K=16, above LI)", ("p4a_rr1_1", "p4a_rr1_2"), ("p4a_rr1_1", "p4a_rr1_2"), True),
                                ("null: P5 K=16 cells = P4's ACTIVE legs (the K=16 slowdown kept)", ("p4a_act_1", "p4a_act_2"), ("p4a_rr1_1", "p4a_rr1_2"), False)):
        c = space(base, {"p5a_stock16_1": P4 / "p4a_rr16_1", "p5a_stock16_2": P4 / "p4a_rr16_2", "p5a_li16_1": P4 / "p4a_li16_1", "p5a_li16_2": P4 / "p4a_li16_2"})
        for r in (0, 1):
            p5_fixture(c / f"p5a_p5k16_{r + 1}", P4 / p16[r]); p5_fixture(c / f"p5a_p5k1_{r + 1}", P4 / p1[r])
        p = gate("smoke", c); ctl("G_smoke_P5B", kind, want, p.returncode, last(p))

    if dry:
        print("NO_DOCKER dry run: the in-image check and G_alone are skipped; all_pass forced false")
    else:
        print("G_build_A in-image check (the engine's own Python inside each image)")
        expect = json.dumps({f: hashlib.md5((SRC / f).read_bytes()).hexdigest() for f in ("IGlobal.py", "IInstance.py", "infer_worker.py")})
        for kind, tag, want in (("positive: rr:p5-infer (the P5 node loads; one frame end to end on the inference thread; one LWDETR)", "rr:p5-infer", True),
                                ("null: rr:patched-video (fails the node-identity check)", "rr:patched-video", False)):
            p = run(["docker", "run", "--rm", "--network", "none", "-v", f"{FRAME}:/x/frame.png:ro", "-v", f"{SRC / 'check_p5_in_image.py'}:/x/check.py:ro",
                     "--workdir", "/opt/rocketride/engine", "--entrypoint", "/opt/rocketride/engine/engine", tag, "/x/check.py", expect])
            line = next((x for x in p.stdout.splitlines() if x.startswith("P5_CHECK ")), (p.stdout + p.stderr)[-300:])
            ctl("G_build_A", kind, want, p.returncode, line)
        print("G_alone")
        p = gate("alone"); ctl("G_alone", "positive: no container on the box", True, p.returncode, last(p))
        mk = run(["docker", "create", "--name", "p5_ctl_dummy", "--entrypoint", "true", "li:video"])
        p = gate("alone"); run(["docker", "rm", "p5_ctl_dummy"])
        ctl("G_alone", "null: one created container present", False, p.returncode, (last(p) + " " + mk.stderr.strip())[:300])

    targets = all(x.is_dir() for x in (CP5, CST, CLI, CCAN))
    all_pass = all(x["pass"] for x in RESULTS) and targets and not dry
    rec = {"label": "P5 gate controls: every gate run whole in its real runtime against a positive control (must PASS) and a null control (must FAIL), before launch",
           "run": n, "run_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
           "boot_id": Path("/proc/sys/kernel/random/boot_id").read_text().strip() if Path("/proc/sys/kernel/random/boot_id").exists() else None,
           "python": PY, "dry_run_no_docker": dry, "seconds": round(time.time() - t0, 1), "control_targets_present": targets, "image_ids": ids,
           "controls": RESULTS, "n": len(RESULTS), "n_pass": sum(x["pass"] for x in RESULTS), "all_pass": all_pass}
    out = camp / ("gate_controls_DRYRUN.json" if dry else ("gate_controls.json" if n == 1 else f"gate_controls_run{n}.json"))
    with open(out, "x") as f:
        json.dump(rec, f, indent=1); f.write("\n")
    print(f"\ngate controls: {rec['n_pass']} of {rec['n']} as expected -> all_pass={all_pass} ({out.name})")
    return 0 if all_pass else 1


if __name__ == "__main__":
    sys.exit(main())
