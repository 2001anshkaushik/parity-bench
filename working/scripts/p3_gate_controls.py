#!/usr/bin/env python3
"""P3 GATE CONTROLS (the P3 rule after register 55-57): before launch, every gate and in-image check runs WHOLE, in its
real runtime (the box's ~/.venv Python for the chain gates; the engine's Python inside the container for the in-image
check; each image's own interpreter for the bare microbenchmark), against a known-good target that must PASS and a
known-bad target that must FAIL. The master refuses to start unless <camp>/gate_controls.json says all_pass.

    ~/.venv/bin/python working/scripts/p3_gate_controls.py <campaign_dir_abs>

Fixtures are built in ~/p3_gate_controls_<campaign>/ (outside the repository) from P2's COMMITTED legs, which are in
this worktree. Nothing here measures anything.
"""
from __future__ import annotations

import base64
import gzip
import json
import shutil
import struct
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PY = sys.executable
GATES = ROOT / "working" / "scripts" / "p3_gates.py"
P2 = ROOT / "working" / "results" / "parity_p2_20260924T160106Z"
CHECK = ROOT / "working" / "nodes" / "p2_pdfium_src" / "check_in_image.py"
BENCH_DIR = ROOT / "working" / "video" / "p3b"
CORPUS = Path.home() / "parity-bench" / "corpus" / "govdocs1" / "pdfs"
RESULTS: list = []


def run(args, **kw):
    return subprocess.run(args, capture_output=True, text=True, **kw)


def ctl(gate: str, kind: str, expect: str, got: str, detail: str = "") -> None:
    ok = expect == got
    RESULTS.append({"gate": gate, "control": kind, "expect": expect, "got": got, "pass": ok, "detail": detail[:600]})
    print(f"  {'PASS' if ok else 'FAIL'}  {gate} [{kind}] expect {expect}, got {got}  {detail[:160]}")


def gate(camp: Path, *a) -> subprocess.CompletedProcess:
    return run([PY, str(GATES), a[0], str(camp), *[str(x) for x in a[1:]]] if a[0] not in ("mandate", "mandate_v", "alone")
               else [PY, str(GATES), *[str(x) for x in a]])


def rc_word(rc: int) -> str:
    return {0: "0 (pass/fired/clean)", 1: "1 (fail/not fired/violation)"}.get(rc, f"{rc} (other)")


def copyleg(src: Path, dst: Path) -> Path:
    shutil.copytree(src, dst)
    return dst


def edit_perdoc(leg: Path, fn) -> None:
    f = next(leg.glob("perdoc_*.jsonl"))
    rows = [json.loads(x) for x in f.read_text().splitlines() if x.strip()]
    rows = fn(rows)
    f.write_text("".join(json.dumps(r) + "\n" for r in rows))


def faster(rows, factor):
    t0 = min(r["submit_ns"] for r in rows)
    for r in rows:
        r["submit_ns"] = t0 + int((r["submit_ns"] - t0) * factor)
        r["completion_ns"] = t0 + int((r["completion_ns"] - t0) * factor)
    return rows


def alter_first_chunk(rows):
    for r in rows:
        if r.get("ok"):
            r["chunk_sha256"] = ["0" * 64] + r["chunk_sha256"][1:]
            break
    return rows


def write_vecs(leg: Path, eps: float) -> None:
    rows = [json.loads(x) for x in next(leg.glob("perdoc_*.jsonl")).read_text().splitlines() if x.strip()]
    with gzip.open(leg / "vecs.jsonl.gz", "wt", encoding="utf-8") as f:
        for r in rows:
            vecs = [base64.b64encode(struct.pack("<4f", *(0.1 * (i + 1) + eps for i in range(4)))).decode() for _ in range(r.get("n_chunks") or 0)]
            f.write(json.dumps({"doc": r["doc"], "dim": 4, "vecs": vecs}) + "\n")


NO_DOCKER = __import__("os").environ.get("P3_CTL_NO_DOCKER") == "1"   # laptop dry run only: can never yield all_pass


def main() -> int:
    camp = Path(sys.argv[1])
    base = Path(__import__("os").environ.get("P3_CTL_BASE", str(Path.home()))) / f"p3_gate_controls_{camp.name}"
    if base.exists():
        print(f"REFUSED: {base} exists (one control run per campaign; append-only)")
        return 2
    base.mkdir()
    t0 = time.time()
    print("G_memstat")
    c = base / "memstat"; c.mkdir()
    copyleg(P2 / "p2a_rr_a", c / "legpos")
    (c / "legnull").mkdir(); (c / "legnull" / "memstat.jsonl").write_text("")
    ctl("G_memstat", "positive: P2's p2a_rr_a", rc_word(0), rc_word(gate(c, "memstat", "legpos").returncode))
    ctl("G_memstat", "null: an empty memstat.jsonl", rc_word(1), rc_word(gate(c, "memstat", "legnull").returncode))

    print("G_mandate (docs and video)")
    c = base / "mandate"; c.mkdir()
    ctl("G_mandate_docs", "positive: P2's p2a_rr_a (clean)", rc_word(0), rc_word(gate(c, "mandate", P2 / "p2a_rr_a").returncode))
    v = copyleg(P2 / "p2a_rr_a", c / "viol")
    lf = next(v.glob("leg_*.json")); j = json.loads(lf.read_text()); j["p0"]["mandate"]["mandate_violation"] = True
    j["p0"]["mandate"]["violations"] = ["control: two task processes"]; lf.write_text(json.dumps(j))
    ctl("G_mandate_docs", "null: the same leg marked violating", rc_word(1), rc_word(gate(c, "mandate", v).returncode))
    ctl("G_mandate_video", "positive: P2's p2b_rr_base_a (clean)", rc_word(0), rc_word(gate(c, "mandate_v", P2 / "p2b_rr_base_a").returncode))
    vv = c / "vviol"; vv.mkdir(); (vv / "MANDATE_VIOLATION.json").write_text("{}")
    ctl("G_mandate_video", "null: a leg with MANDATE_VIOLATION.json", rc_word(1), rc_word(gate(c, "mandate_v", vv).returncode))

    print("G_health_A")
    for kind, fn, mem_empty in (("positive: P2's p2a_rr_b / p2a_li_b as the P3 legs", None, False),
                                ("null: one chunk hash altered in the RR leg", alter_first_chunk, False),
                                ("null: the LlamaIndex leg's memory sampler empty", None, True)):
        c = base / f"health_{len(RESULTS)}"; c.mkdir()
        rr = copyleg(P2 / "p2a_rr_b", c / "p3a_rr_h"); li = copyleg(P2 / "p2a_li_b", c / "p3a_li_h")
        if fn:
            edit_perdoc(rr, fn)
        if mem_empty:
            (li / "memstat.jsonl").write_text("")
        want = 0 if kind.startswith("positive") else 1
        ctl("G_health_A", kind, rc_word(want), rc_word(gate(c, "health_a", P2 / "p2a_rr_a", P2 / "p2a_rr_b").returncode))

    print("G_smoke_C (thread shapes)")
    for kind, t2_factor, t2_fn, want in (("positive: vars=2 10% faster, chunks identical", 1 / 1.10, None, ["2"]),
                                         ("null: vars=2 and vars=4 as fast as vars=1", 1.0, None, []),
                                         ("null: vars=2 faster but one chunk list differs", 1 / 1.10, alter_first_chunk, [])):
        c = base / f"smokec_{len(RESULTS)}"; c.mkdir()
        for r, src in (("a", "p2a_rr_a"), ("b", "p2a_rr_b")):
            write_vecs(copyleg(P2 / src, c / f"p3c_t1_{r}"), 0.0)
            l2 = copyleg(P2 / src, c / f"p3c_t2_{r}"); edit_perdoc(l2, lambda rows: faster(rows, t2_factor)); write_vecs(l2, 1e-6)
            if t2_fn:
                edit_perdoc(l2, t2_fn)
            write_vecs(copyleg(P2 / src, c / f"p3c_t4_{r}"), 0.0)
        rc = gate(c, "smoke_c").returncode
        recf = c / "gates" / "G_smoke_C.json"
        got = json.loads(recf.read_text())["fired_shapes"] if recf.exists() else f"no record (rc {rc})"
        vd = (json.loads(recf.read_text())["per_shape"]["2"]["vector_max_abs_delta_vs_vars1"][0] if recf.exists() else {})
        ctl("G_smoke_C", kind, json.dumps(want), json.dumps(got), f"vector max|delta| vars2 vs vars1: {vd.get('max_abs_delta')}")

    print("G_node_D")
    c = base / "noded"; c.mkdir()
    for leg, cnt in (("ok", {"docs": 36, "text": 30, "fallback": 6, "errors": 0}),
                     ("bad", {"docs": 36, "text": 0, "fallback": 36, "errors": 36, "last_error": "ModuleNotFoundError: pypdfium2_cfg"})):
        (c / leg).mkdir(); (c / leg / "p1_pdfium_hybrid.json").write_text(json.dumps(cnt))
    ctl("G_node_D", "positive: counters with text", rc_word(0), rc_word(gate(c, "node_d", "ok", "hybrid").returncode))
    c2 = base / "noded2"; shutil.copytree(c, c2, ignore=shutil.ignore_patterns("gates"))
    ctl("G_node_D", "null: P1's failure (text 0)", rc_word(1), rc_word(gate(c2, "node_d", "bad", "hybrid").returncode))

    print("G_smoke_D (P2-C's gate, P3 names)")
    sys.path.insert(0, str(ROOT / "working" / "scripts"))
    import p2_tooling_test as T  # the P2 synthetic-leg builders (write_leg, stamps_for)
    for kind, parse, pure_empty, want in (("positive: HYBRID 10% faster than Tika's spread, no coverage loss",
                                           {"fix": (1.0, 1.02), "hyb": (0.90, 0.90), "pure": (0.99, 1.0)}, True, ["hybrid"]),
                                          ("null: both variants inside Tika's spread", {"fix": (1.0, 1.02), "hyb": (0.995, 1.0), "pure": (0.99, 1.0)}, True, [])):
        c = base / f"smoked_{len(RESULTS)}"; c.mkdir()
        tmp = base / f"tmp_{len(RESULTS)}"; tmp.mkdir()
        src = T.c_camp(tmp, "x", parse, pure_empty)
        for leg in src.iterdir():
            if leg.is_dir():
                shutil.copytree(leg, c / leg.name.replace("p2c_", "p3d_"))
        gate(c, "smoke_d")
        recf = c / "gates" / "G_smoke_D.json"
        got = json.loads(recf.read_text())["fired_variants"] if recf.exists() else "no record"
        ctl("G_smoke_D", kind, json.dumps(want), json.dumps(got))

    if NO_DOCKER:
        print("NO_DOCKER dry run: the container-dependent controls are skipped and all_pass is forced false")
        return finish(camp, t0, dry=True)
    print("G_alone (P3-B: every cell alone)")
    ctl("G_alone", "positive: no container on the box", rc_word(0), rc_word(gate(base, "alone").returncode))
    mk = run(["docker", "create", "--name", "p3_ctl_dummy", "--entrypoint", "true", "li:video"])
    got = gate(base, "alone").returncode
    run(["docker", "rm", "p3_ctl_dummy"])
    ctl("G_alone", "null: one created container present", rc_word(1), rc_word(got), mk.stderr.strip())

    print("G_build_D in-image check (the engine's own Python inside the container)")
    for kind, img, want in (("positive: rr:p2-pdfium (pypdfium2 complete)", "rr:p2-pdfium", "ok=True rc=0"),
                            ("null: rr:p1-pdfium (pypdfium2_cfg missing)", "rr:p1-pdfium", "ok=False rc=1")):
        r = run(["docker", "run", "--rm", "-v", f"{CORPUS}:/corpus:ro", "-v", f"{CHECK}:/x/check.py:ro", "--workdir", "/opt/rocketride/engine",
                 "--entrypoint", "/opt/rocketride/engine/engine", img, "/x/check.py", "/corpus/002_002489.pdf"])
        line = next((x for x in r.stdout.splitlines() if x.startswith("P2_PDFIUM_CHECK ")), None)
        j = json.loads(line.split(" ", 1)[1]) if line else {}
        ctl("G_build_D", kind, want, f"ok={j.get('ok')} rc={r.returncode}", json.dumps(j)[:400])

    print("P3-B bare microbenchmark one-model check (each image's own interpreter)")
    fr = base / "frames"; fr.mkdir()
    man = Path.home() / "parity-bench-video" / "working" / "video" / "ami_video_manifest.jsonl"
    rows = [json.loads(x) for x in man.read_text().splitlines() if x.strip() and not x.startswith("#")]
    first = [r for r in rows if isinstance(r, dict) and r.get("role") == "measured"][0]["file"]
    vdir = Path.home() / "parity-bench-video" / "corpus" / "ami" / "full"
    r = run(["docker", "run", "--rm", "--network", "none", "-v", f"{vdir}:/v:ro", "-v", f"{fr}:/frames", "-v", f"{BENCH_DIR}:/x:ro",
             "--entrypoint", "python", "li:video", "/x/p3b_frames.py", "--out", "/frames", f"/v/{first}"])
    print("   frames:", r.stdout.strip()[-200:], r.stderr.strip()[-200:])
    small = base / "frames_small" / "v00"; small.mkdir(parents=True)
    for p in sorted((fr).rglob("*.png"))[:8]:
        shutil.copy(p, small / p.name)
    env = []
    for k in ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS", "VECLIB_MAXIMUM_THREADS", "NUMEXPR_NUM_THREADS", "TORCH_NUM_THREADS"):
        env += ["-e", f"{k}=4"]
    cells = {"a": (["--workdir", "/opt/rocketride/engine", "--entrypoint", "/opt/rocketride/engine/engine", "rr:patched-video"],
                   "/opt/rocketride/engine/cache/models/rfdetr"),
             "b": (["--entrypoint", "python", "li:video"], "/opt/rfdetr-cache")}
    for cell, (img, wdir) in cells.items():
        for kind, extra, want_rc in (("positive: one model", [], 0), ("null: --null-two-models", ["--null-two-models"], 3)):
            out = base / f"bench_{cell}_{want_rc}"; out.mkdir()
            r = run(["docker", "run", "--rm", "--network", "none", "--memory", "16g", *env, "-v", f"{small.parent}:/frames:ro",
                     "-v", f"{BENCH_DIR}:/x:ro", "-v", f"{out}:/out", *img, "/x/p3b_bench.py", "--frames", "/frames",
                     "--weights-dir", wdir, "--out", "/out/bench.json", "--warmup", "2", *extra])
            line = next((x for x in r.stdout.splitlines() if x.startswith("P3B_BENCH ")), "")
            ctl(f"P3B_one_model ({cell})", kind, f"rc={want_rc}", f"rc={r.returncode}",
                (line or (r.stdout + r.stderr)[-400:]))
    return finish(camp, t0)


def finish(camp: Path, t0: float, dry: bool = False) -> int:
    all_pass = all(x["pass"] for x in RESULTS) and not dry
    rec = {"label": "P3 gate controls: every gate run whole in its real runtime against a positive control (must PASS) and a null "
                    "control (must FAIL), before launch (the P3 GATE CONTROLS rule)", "run_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
           "boot_id": open("/proc/sys/kernel/random/boot_id").read().strip() if Path("/proc/sys/kernel/random/boot_id").exists() else None,
           "seconds": round(time.time() - t0, 1), "dry_run_no_docker": dry,
           "controls": RESULTS, "n": len(RESULTS), "n_pass": sum(x["pass"] for x in RESULTS), "all_pass": all_pass}
    out = camp / ("gate_controls_DRYRUN.json" if dry else "gate_controls.json")
    out.write_text(json.dumps(rec, indent=1) + "\n")
    print(f"\ngate controls: {rec['n_pass']} of {rec['n']} as expected -> all_pass={all_pass} ({out.name})")
    return 0 if all_pass else 1


if __name__ == "__main__":
    sys.exit(main())
