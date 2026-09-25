#!/usr/bin/env python3
"""P6 GATE CONTROLS: before launch, every gate runs WHOLE, in its real runtime (the box's ~/.venv Python; docker for G_alone),
against a known-good target that must PASS (rc 0) and a known-bad target that must FAIL (rc != 0). The chain's 'run' stage
refuses unless the latest record says all_pass. Targets: COMMITTED legs (P0, P3, P5, batch-size smoke; linked, never
written) and the control stage's real legs p6ctl_p5t16, p6ctl_lit16, p6ctl_warm_rr, p6ctl_warm_li.

    ~/.venv/bin/python working/scripts/p6_gate_controls.py <campaign_dir_abs>        (P6_CTL_NO_DOCKER=1: laptop dry run)
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
GATES = ROOT / "working" / "scripts" / "p6_gates.py"
RES = ROOT / "working" / "results"
P0, P3, P5 = RES / "parity_p0_20260923T083031Z", RES / "parity_p3_20260925T035027Z", RES / "parity_p5_20260925T141647Z"
BS = RES / "batchsize_smoke_20260920T113000Z" / "video_n16"
FMAN = P3 / "p3b_frames_manifest.json"
RESULTS: list = []
N = [0]


def run(args):
    return subprocess.run(args, capture_output=True, text=True)


def last(p):
    s = ((p.stdout or "") + (p.stderr or "")).strip().splitlines()
    return s[-1] if s else ""


def ctl(gate, kind, want, rc, detail=""):
    ok = (rc == 0) == want
    RESULTS.append({"gate": gate, "control": kind, "expect": "PASS (rc 0)" if want else "FAIL (rc != 0)",
                    "got": f"{'PASS' if rc == 0 else 'FAIL'} (rc {rc})", "pass": ok, "detail": detail[:600]})
    print(f"  {'ok  ' if ok else 'BAD '}  {gate} [{kind}] expect {'PASS' if want else 'FAIL'}, got rc {rc}  {detail[:140]}")


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


def main() -> int:
    camp = Path(sys.argv[1])
    dry = os.environ.get("P6_CTL_NO_DOCKER") == "1"
    n = 1 + len(list(camp.glob("gate_controls.json"))) + len(list(camp.glob("gate_controls_run*.json")))
    base = Path(os.environ.get("P6_CTL_BASE", str(Path.home()))) / (f"p6_gate_controls_{camp.name}" + ("" if n == 1 else f"_run{n}"))
    if base.exists():
        print(f"REFUSED: {base} exists"); return 2
    base.mkdir(parents=True)
    T16, L16, WRR, WLI = camp / "p6ctl_p5t16", camp / "p6ctl_lit16", camp / "p6ctl_warm_rr", camp / "p6ctl_warm_li"
    ids = {} if dry else {t: imgid(t) for t in ("rr:patched-video", "rr:p5-infer", "li:video")}
    I = lambda t: ids.get(t, "DRY")  # noqa: E731
    t0 = time.time()

    print("G_memstat")
    ctl("G_memstat", "positive: P5 p5a_stock16_1", True, gate("memstat", space(base, {"L": P5 / "p5a_stock16_1"}), "L").returncode)
    ctl("G_memstat", "null: batchsize_smoke rr_k16 (no memory sampler)", False, gate("memstat", space(base, {"L": BS / "rr_k16"}), "L").returncode)

    print("G_d0")
    for arm, kind, tgt, want in (("rr", "positive: P5 p5a_p5k16_1", P5 / "p5a_p5k16_1", True), ("rr", "positive: the control leg p6ctl_p5t16 (out of box)", T16, True),
                                 ("rr", "null: batchsize_smoke rr_k16 (no on-token D0: absence)", BS / "rr_k16", False),
                                 ("li", "positive: P5 p5a_li16_1", P5 / "p5a_li16_1", True), ("li", "positive: the control leg p6ctl_lit16", L16, True),
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
            ("p5 T=16 unset", T16, "p5", 2, 16, 2, "rr:p5-infer", "unset", True, "positive: the control leg p6ctl_p5t16"),
            ("p5 T=16 unset", P5 / "p5a_p5k16_1", "p5", 16, 16, 16, "rr:p5-infer", "unset", False, "null: P5 p5a_p5k16_1 against T=16 unset (torch 4, vars set)"),
            ("li T=16", L16, "li", 2, 16, 2, "li:video", "set", True, "positive: the control leg p6ctl_lit16"),
            ("li T=16", P5 / "p5a_li16_1", "li", 16, 16, 16, "li:video", "set", False, "null: P5 p5a_li16_1 against T=16 (torch 4)"),
            ("stock T=4", P5 / "p5a_stock16_1", "stock", 16, 4, 16, "rr:patched-video", "set", True, "positive: P5 p5a_stock16_1"),
            ("stock T=4", P5 / "p5a_p5k16_1", "stock", 16, 4, 16, "rr:patched-video", "set", False, "null: P5 p5a_p5k16_1 against the stock spec (image, stamps)"),
            ("li T=4", P5 / "p5a_li16_1", "li", 16, 4, 16, "li:video", "set", True, "positive: P5 p5a_li16_1"),
            ("li T=4", BS / "li_k16", "li", 16, 4, 16, "li:video", "set", False, "null: batchsize_smoke li_k16 (no read-back)")):
        p = gate("cell", space(base, {"L": tgt}), "L", fl, k, t, nn, I(tag), env); ctl(f"G_cell {label}", kind, want, p.returncode, last(p))

    print("G_warm (the P6 warm symmetry: declared and shown in the leg's warm-up ledger)")
    for kind, tgt, s, cc, want in (("positive: the control leg p6ctl_warm_rr (2 at 2)", WRR, 2, 2, True),
                                   ("positive: the control leg p6ctl_warm_li (2 at 2)", WLI, 2, 2, True),
                                   ("null: P5 p5a_p5k16_1 (the default warm policy, nothing declared)", P5 / "p5a_p5k16_1", 2, 2, False),
                                   ("null: p6ctl_warm_rr against 16 at 16", WRR, 16, 16, False)):
        p = gate("warm", space(base, {"L": tgt}), "L", s, cc); ctl("G_warm", kind, want, p.returncode, last(p))

    print("G_canary")
    for kind, tgt, want in (("positive: P5 p5c_can_1 (committed canary)", P5 / "p5c_can_1", True),
                            ("null: P3 p3b_a_1 (the same bench over all three videos)", P3 / "p3b_a_1", False)):
        p = gate("canary", space(base, {"L": tgt}), "L", FMAN, "v00_EN2001a"); ctl("G_canary", kind, want, p.returncode, last(p))

    print("G_correct")
    for kind, a, b, want in (("positive: P0 v1_rr_t4_a vs v1_rr_t4_b (identical 16/16)", P0 / "v1_rr_t4_a", P0 / "v1_rr_t4_b", True),
                             ("positive (the P6-C reference form, an absolute path): P0 v1_rr_def_b vs v1_rr_def_a (identical 16/16)", P0 / "v1_rr_def_b", None, True),
                             ("null: P0 v1_rr_def_a vs v1_rr_t4_a (T=16 vs T=4: differs on 16/16)", P0 / "v1_rr_def_a", P0 / "v1_rr_t4_a", False),
                             ("null: P3 p3b_c_1 vs p3b_c_2 (identical but 3 videos)", P3 / "p3b_c_1", P3 / "p3b_c_2", False)):
        if b is None:
            p = gate("correct", space(base, {"A": a}), "G_correct", "A", str(P0 / "v1_rr_def_a"))
        else:
            p = gate("correct", space(base, {"A": a, "B": b}), "G_correct", "A", "B")
        ctl("G_correct", kind, want, p.returncode, last(p))

    print("G_smoke_P6B (correctness both rounds AND Q1 round 1, round 2, pooled) on P5's committed smoke legs as P6-A cells")
    for kind, p5legs, want in (("positive: P6-A cells = P5's stock / P5 / LI K=16 legs (Q1 1.35 and 1.40, identical output)", ("p5a_p5k16_1", "p5a_p5k16_2"), True),
                               ("null: the 'P5' cell = P5's STOCK legs (P5/LI below 0.95; output identical)", ("p5a_stock16_1", "p5a_stock16_2"), False)):
        links = {}
        for r in (1, 2):
            links[f"p6a_stock16_{r}"] = P5 / f"p5a_stock16_{r}"
            links[f"p6a_p5k16_{r}"] = P5 / p5legs[r - 1]
            links[f"p6a_li16_{r}"] = P5 / f"p5a_li16_{r}"
        c = space(base, links)
        if p5legs[0].startswith("p5a_stock"):       # the stock legs carry P1 stamps; give the P5 reader its schema
            for r in (1, 2):
                (c / f"p6a_p5k16_{r}").unlink()
                shutil.copytree(P5 / p5legs[r - 1], c / f"p6a_p5k16_{r}", ignore=shutil.ignore_patterns("percore.jsonl", "fsstream_*", "collector_*"))
                rows = [json.loads(x) for x in (P5 / p5legs[r - 1] / "p1_stamps.jsonl").read_text().splitlines() if x.strip()]
                with open(c / f"p6a_p5k16_{r}" / "p5_stamps.jsonl", "w") as f:
                    for x in rows:
                        f.write(json.dumps(dict(x, kind="frame", queue_wait=x.get("lock_wait"), infer_held=x.get("lock_held"), handoff=0.0, qdepth=0, infer_tid=1)) + "\n")
        p = gate("smoke", c); ctl("G_smoke_P6B", kind, want, p.returncode, last(p))

    if dry:
        print("NO_DOCKER dry run: G_alone skipped; all_pass forced false")
    else:
        print("G_alone")
        p = gate("alone"); ctl("G_alone", "positive: no container on the box", True, p.returncode, last(p))
        mk = run(["docker", "create", "--name", "p6_ctl_dummy", "--entrypoint", "true", "li:video"])
        p = gate("alone"); run(["docker", "rm", "p6_ctl_dummy"])
        ctl("G_alone", "null: one created container present", False, p.returncode, (last(p) + " " + mk.stderr.strip())[:300])

    targets = all(x.is_dir() for x in (T16, L16, WRR, WLI))
    all_pass = all(x["pass"] for x in RESULTS) and targets and not dry
    rec = {"label": "P6 gate controls: every gate run whole in its real runtime against a positive control (must PASS) and a null control (must FAIL), before launch",
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
