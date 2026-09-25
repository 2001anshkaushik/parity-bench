#!/usr/bin/env python3
"""P4 GATE CONTROLS (the carried rule): before launch, every gate runs WHOLE, in its real runtime (the box's ~/.venv Python;
docker for G_alone), against a known-good target that must PASS (rc 0) and a known-bad target that must FAIL (rc != 0).
The chain's 'run' stage refuses unless the highest-numbered record (gate_controls.json, gate_controls_run<N>.json) says
all_pass. Targets are COMMITTED legs in this worktree (linked, never written: each control gets its own directory under
~/p4_gate_controls_<campaign>[_run<N>]/ holding symlinks, and the gate records land there), plus the control leg
p4ctl_active (a real engine leg with OMP_WAIT_POLICY=ACTIVE, run by p4_video_chain.sh control before this).

    ~/.venv/bin/python working/scripts/p4_gate_controls.py <campaign_dir_abs>
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
GATES = ROOT / "working" / "scripts" / "p4_gates.py"
RES = ROOT / "working" / "results"
P0 = RES / "parity_p0_20260923T083031Z"
P2 = RES / "parity_p2_20260924T160106Z"
P3 = RES / "parity_p3_20260925T035027Z"
BS = RES / "batchsize_smoke_20260920T113000Z" / "video_n16"
RESULTS: list = []
N_CTL = [0]


def run(args):
    return subprocess.run(args, capture_output=True, text=True)


def ctl(gate: str, kind: str, want_pass: bool, rc: int, detail: str = "") -> None:
    got_pass = rc == 0
    ok = got_pass == want_pass
    RESULTS.append({"gate": gate, "control": kind, "expect": "PASS (rc 0)" if want_pass else "FAIL (rc != 0)",
                    "got": f"{'PASS' if got_pass else 'FAIL'} (rc {rc})", "pass": ok, "detail": detail[:600]})
    print(f"  {'ok  ' if ok else 'BAD '}  {gate} [{kind}] expect {'PASS' if want_pass else 'FAIL'}, got rc {rc}  {detail[:140]}")


def space(base: Path, links: dict) -> Path:
    """A fresh control directory holding symlinks name -> committed leg (or a real fixture directory)."""
    N_CTL[0] += 1
    c = base / f"c{N_CTL[0]:02d}"
    c.mkdir()
    for name, src in links.items():
        (c / name).symlink_to(src, target_is_directory=True)
    return c


def gate(*a) -> subprocess.CompletedProcess:
    return run([PY, str(GATES), *[str(x) for x in a]])


def last_line(p: subprocess.CompletedProcess) -> str:
    s = ((p.stdout or "") + (p.stderr or "")).strip().splitlines()
    return s[-1] if s else ""


def main() -> int:
    camp = Path(sys.argv[1])
    n = 1 + len(list(camp.glob("gate_controls.json"))) + len(list(camp.glob("gate_controls_run*.json")))
    base = Path(os.environ.get("P4_CTL_BASE", str(Path.home()))) / (f"p4_gate_controls_{camp.name}" + ("" if n == 1 else f"_run{n}"))
    if base.exists():
        print(f"REFUSED: {base} exists (one directory per control run; append-only)")
        return 2
    base.mkdir(parents=True)
    ctl_leg = camp / "p4ctl_active"
    t0 = time.time()

    print("G_memstat")
    c = space(base, {"L": P2 / "p2b_rr_base_a"}); p = gate("memstat", c, "L")
    ctl("G_memstat", "positive: P2 p2b_rr_base_a", True, p.returncode, last_line(p))
    c = space(base, {"L": BS / "rr_k16"}); p = gate("memstat", c, "L")
    ctl("G_memstat", "null: batchsize_smoke rr_k16 (no memory sampler)", False, p.returncode, last_line(p))

    print("G_d0 rr")
    c = space(base, {"L": P2 / "p2b_rr_base_a"}); p = gate("d0", c, "L", "rr")
    ctl("G_d0 rr", "positive: P2 p2b_rr_base_a", True, p.returncode, last_line(p))
    c = space(base, {"L": ctl_leg}); p = gate("d0", c, "L", "rr")
    ctl("G_d0 rr", "positive: the control leg p4ctl_active (its own on-token D0)", True, p.returncode, last_line(p))
    c = space(base, {"L": BS / "rr_k16"}); p = gate("d0", c, "L", "rr")
    ctl("G_d0 rr", "null: batchsize_smoke rr_k16 (no on-token D0: absence)", False, p.returncode, last_line(p))
    c = space(base, {}); shutil.copytree(P2 / "p2b_rr_base_a", c / "L", ignore=shutil.ignore_patterns("percore.jsonl", "fsstream_*", "collector_*"))
    (c / "L" / "MANDATE_VIOLATION.json").write_text('{"control": "two task processes"}')
    p = gate("d0", c, "L", "rr")
    ctl("G_d0 rr", "null: a copy of p2b_rr_base_a holding MANDATE_VIOLATION.json", False, p.returncode, last_line(p))
    c = space(base, {}); shutil.copytree(P2 / "p2b_rr_base_a", c / "L", ignore=shutil.ignore_patterns("percore.jsonl", "fsstream_*", "collector_*"))
    ef = sorted((c / "L").glob("export_*.json"))[0]; j = json.loads(ef.read_text())
    (j.get("p0") or j["provenance_video"]["p0"])["mandate"] = {"mandate_violation": True, "violations": ["control: 2 task processes for the leg (mandate: exactly 1)"]}
    ef.write_text(json.dumps(j))
    p = gate("d0", c, "L", "rr")
    ctl("G_d0 rr", "null: a copy of p2b_rr_base_a whose export p0 mandate says violation", False, p.returncode, last_line(p))

    print("G_d0 li")
    c = space(base, {"L": P2 / "p2b_li_a"}); p = gate("d0", c, "L", "li")
    ctl("G_d0 li", "positive: P2 p2b_li_a (one container, one worker)", True, p.returncode, last_line(p))
    c = space(base, {"L": BS / "li_k16"}); p = gate("d0", c, "L", "li")
    ctl("G_d0 li", "null: batchsize_smoke li_k16 (eight LlamaIndex containers)", False, p.returncode, last_line(p))

    print("G_cell")
    specs = [
        ("rr K=16 T=4 unset n=16", ["rr", 16, 4, "unset", 16], [("positive: P2 p2b_rr_base_a", P2 / "p2b_rr_base_a", True),
                                                                 ("null: batchsize_smoke rr_k16 (no read-back, default threads)", BS / "rr_k16", False),
                                                                 ("null: the control leg p4ctl_active (ACTIVE, K=2, n=2)", ctl_leg, False)]),
        ("rr K=1 T=4 unset n=3", ["rr", 1, 4, "unset", 3], [("positive: P3 p3b_c_1 (K=1, T=4, stamped)", P3 / "p3b_c_1", True),
                                                             ("null: P2 p2b_rr_base_a (K=16, n=16)", P2 / "p2b_rr_base_a", False)]),
        ("li K=16 T=4 unset n=16", ["li", 16, 4, "unset", 16], [("positive: P2 p2b_li_a", P2 / "p2b_li_a", True),
                                                                 ("null: batchsize_smoke li_k16 (no read-back)", BS / "li_k16", False)]),
        ("li K=1 T=4 unset n=3", ["li", 1, 4, "unset", 3], [("positive: P3 p3b_d_1", P3 / "p3b_d_1", True),
                                                             ("null: P2 p2b_li_a (K=16, n=16)", P2 / "p2b_li_a", False)]),
        ("rr ACTIVE (control-leg spec K=2 T=4 n=2)", ["rr", 2, 4, "ACTIVE", 2], [("positive: the control leg p4ctl_active", ctl_leg, True)]),
        ("rr ACTIVE K=16 T=4 n=16", ["rr", 16, 4, "ACTIVE", 16], [("null: P2 p2b_rr_base_a (OMP_WAIT_POLICY absent)", P2 / "p2b_rr_base_a", False)]),
    ]
    for label, spec, targets in specs:
        for kind, tgt, want in targets:
            c = space(base, {"L": tgt}); p = gate("cell", c, "L", *spec)
            ctl(f"G_cell {label}", kind, want, p.returncode, last_line(p))

    print("G_correct_active")
    for kind, a, b, want in (("positive: P0 v1_rr_t4_a vs v1_rr_t4_b (identical 16/16)", P0 / "v1_rr_t4_a", P0 / "v1_rr_t4_b", True),
                             ("null: P0 v1_rr_def_a vs v1_rr_t4_a (T=16 vs T=4: differs on 16/16)", P0 / "v1_rr_def_a", P0 / "v1_rr_t4_a", False),
                             ("null: P3 p3b_c_1 vs p3b_c_2 (identical but 3 videos)", P3 / "p3b_c_1", P3 / "p3b_c_2", False)):
        c = space(base, {"A": a, "B": b}); p = gate("correct", c, "G_correct_active", "A", "B")
        ctl("G_correct_active", kind, want, p.returncode, last_line(p))

    dry = os.environ.get("P4_CTL_NO_DOCKER") == "1"      # laptop dry run only: can never yield all_pass
    if dry:
        print("NO_DOCKER dry run: G_alone skipped; all_pass forced false; the record is gate_controls_DRYRUN.json")
    else:
        print("G_alone")
        p = gate("alone")
        ctl("G_alone", "positive: no container on the box", True, p.returncode, last_line(p))
        mk = run(["docker", "create", "--name", "p4_ctl_dummy", "--entrypoint", "true", "li:video"])
        p = gate("alone")
        run(["docker", "rm", "p4_ctl_dummy"])
        ctl("G_alone", "null: one created container present", False, p.returncode, (last_line(p) + " " + mk.stderr.strip())[:300])

    all_pass = all(x["pass"] for x in RESULTS) and ctl_leg.is_dir() and not dry
    rec = {"label": "P4 gate controls: every gate run whole in its real runtime against a positive control (must PASS) and a null "
                    "control (must FAIL), before launch", "run": n, "run_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
           "boot_id": Path("/proc/sys/kernel/random/boot_id").read_text().strip() if Path("/proc/sys/kernel/random/boot_id").exists() else None,
           "python": PY, "dry_run_no_docker": dry, "seconds": round(time.time() - t0, 1), "control_leg_present": ctl_leg.is_dir(),
           "controls": RESULTS, "n": len(RESULTS), "n_pass": sum(x["pass"] for x in RESULTS), "all_pass": all_pass}
    out = camp / ("gate_controls_DRYRUN.json" if dry else ("gate_controls.json" if n == 1 else f"gate_controls_run{n}.json"))
    with open(out, "x") as f:
        json.dump(rec, f, indent=1)
        f.write("\n")
    print(f"\ngate controls: {rec['n_pass']} of {rec['n']} as expected -> all_pass={all_pass} ({out.name})")
    return 0 if all_pass else 1


if __name__ == "__main__":
    sys.exit(main())
