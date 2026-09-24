#!/usr/bin/env python3
"""P2 tooling tests, offline (laptop): every gate in p2_gates.py on synthetic legs built to PASS and on a null
control built to FAIL (a checker that cannot fail proves nothing), the video driver's noDebug injection, and the
build's RECORD selection. Also runs manip_b on P1's banked E2 legs (the real read-back format).

    python working/scripts/p2_tooling_test.py        -> prints PASS/FAIL per check, exit 0 iff all pass
"""
from __future__ import annotations

import asyncio
import csv
import gzip
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
GATES = ROOT / "working" / "scripts" / "p2_gates.py"
P1 = ROOT / "working" / "results" / "parity_p1_20260923T184000Z"
RESULTS: list = []


def check(name: str, cond: bool, detail: str = "") -> None:
    RESULTS.append(cond)
    print(f"  {'PASS' if cond else 'FAIL'}  {name}{('  — ' + detail) if detail and not cond else ''}")


def gate(camp: Path, *args: str) -> int:
    return subprocess.run([sys.executable, str(GATES), args[0], str(camp), *args[1:]], capture_output=True, text=True).returncode


def write_leg(camp: Path, name: str, arm: str, docs: dict, stamps: list = None, texts: dict = None) -> None:
    """docs: {doc: (ok, submit_s, completion_s, n_chunks)}"""
    d = camp / name
    d.mkdir(parents=True)
    (d / f"leg_{name}.json").write_text(json.dumps({"arm": arm, "leg": name, "window": {"t0_ns": 0, "t1_ns": int(1e12)}}))
    (d / f"perdoc_{name}.jsonl").write_text("".join(json.dumps(
        {"doc": k, "ok": v[0], "submit_ns": int(v[1] * 1e9), "completion_ns": int(v[2] * 1e9), "n_chunks": v[3],
         "chunk_sha256": ["x"] * v[3]}) + "\n" for k, v in docs.items()))
    if stamps is not None:
        (d / "stamp_probe.jsonl").write_text("".join(json.dumps(s) + "\n" for s in stamps))
    if texts is not None:
        with gzip.open(d / "texts.jsonl.gz", "wt", encoding="utf-8") as f:
            for k, t in texts.items():
                f.write(json.dumps({"doc": k, "texts": [t]}) + "\n")


def stamps_for(docs: dict, parse_s: dict) -> list:
    out = []
    for k, v in docs.items():
        op = v[1] + 0.01
        pl = op + parse_s[k]
        for st, t in (("after_parse", pl), ("after_split", pl + 0.1), ("after_embed", pl + 0.2)):
            out.append({"doc": k, "stage": st, "open_t": op, "first_t": t, "last_t": t, "close_t": t + 0.01,
                        "tname": "External", "native_id": 1})
    return out


def test_memstat(tmp: Path) -> None:
    print("G_memstat")
    c = tmp / "ms"; (c / "l1").mkdir(parents=True); (c / "l2").mkdir(parents=True)
    (c / "l1" / "memstat.jsonl").write_text('{"t": 1, "anon": 1, "file": 1, "total": 2}\n')
    (c / "l2" / "memstat.jsonl").write_text("")
    check("one row passes", gate(c, "memstat", "l1") == 0)
    check("null control: an empty file fails", gate(c, "memstat", "l2") == 1)
    check("null control: a missing file fails", gate(c, "memstat", "l3") == 1)
    check("a gate is decided once (second call refuses)", gate(c, "memstat", "l1") == 2)


def a_camp(tmp: Path, name: str, rr_rate: float, li_rate: float) -> Path:
    c = tmp / name
    n = 100
    for arm, rate in (("rr", rr_rate), ("li", li_rate)):
        for r, jitter in (("a", 1.0), ("b", 1.01)):
            span = n / rate * jitter
            write_leg(c, f"p2a_{arm}_{r}", arm, {f"d{i}.pdf": (True, 0.0, span * (i + 1) / n, 3) for i in range(n)})
    return c


def test_a_smoke(tmp: Path) -> None:
    print("G_smoke_A")
    c = a_camp(tmp, "a_fire", 4.4, 5.0)       # ratio 0.88
    check("ratio 0.88 fires", gate(c, "a_smoke") == 0)
    rec = json.loads((c / "gates" / "G_smoke_A.json").read_text())
    check("record carries ratio, spreads, floors, bias", all(k in rec for k in ("ratio_rr_over_li", "spreads", "floors", "known_bias")))
    c = a_camp(tmp, "a_null", 4.0, 5.0)       # ratio 0.80
    check("null control: ratio 0.80 does not fire", gate(c, "a_smoke") == 1)
    c = a_camp(tmp, "a_edge", 4.25, 5.0)      # ratio exactly 0.85 -> fires (>=)
    check("ratio exactly 0.85 fires (>=)", gate(c, "a_smoke") == 0)
    c = tmp / "a_missing"; c.mkdir()
    check("missing legs -> not evaluable (2)", gate(c, "a_smoke") == 2)


def test_node_c(tmp: Path) -> None:
    print("G_node_C")
    c = tmp / "nc"
    for leg, cnt in (("ok", {"docs": 36, "text": 30, "fallback": 6, "errors": 0}),
                     ("p1fail", {"docs": 36, "text": 0, "fallback": 36, "errors": 36, "last_error": "ModuleNotFoundError: pypdfium2_cfg"})):
        (c / leg).mkdir(parents=True)
        (c / leg / "p1_pdfium_hybrid.json").write_text(json.dumps(cnt))
    (c / "none").mkdir()
    check("counters with text pass", gate(c, "node_c", "ok", "hybrid") == 0)
    c2 = tmp / "nc2"; shutil.copytree(c, c2, ignore=shutil.ignore_patterns("gates"))
    check("null control: P1's failure (text 0) fails", gate(c2, "node_c", "p1fail", "hybrid") == 1)
    c3 = tmp / "nc3"; shutil.copytree(c, c3, ignore=shutil.ignore_patterns("gates"))
    check("null control: no counters file fails", gate(c3, "node_c", "none", "hybrid") == 1)


ELEVEN = ["000_000344.pdf", "002_002489.pdf", "008_008871.pdf", "011_011464.pdf", "011_011730.pdf", "014_014261.pdf",
          "014_014969.pdf", "031_031239.pdf", "033_033172.pdf", "034_034697.pdf", "039_039660.pdf"]


def c_camp(tmp: Path, name: str, parse: dict, pure_empty_doc: bool, hyb_empty_doc: bool = False) -> Path:
    """parse: {arm: (run_a_p50_scale, run_b_p50_scale)}; each leg's eleven parse brackets are scale*(1..11)/6"""
    c = tmp / name
    for arm, (sa, sb) in parse.items():
        for r, s in (("a", sa), ("b", sb)):
            docs = {k: (True, 100.0 * i, 100.0 * i + 50, 2) for i, k in enumerate(ELEVEN)}
            pb = {k: s * (i + 1) / 6 for i, k in enumerate(ELEVEN)}
            write_leg(c, f"p2c_s_{arm}_{r}", "rr", docs, stamps_for(docs, pb))
    m = [f"m{i}.pdf" for i in range(20)]
    for arm in ("fix", "hyb", "pure"):
        for r in ("a", "b"):
            docs = {k: (True, 0.0, 1.0, 2) for k in m}
            texts = {k: "some text" for k in m}
            if arm == "pure" and pure_empty_doc and r == "b":
                docs["m3.pdf"] = (True, 0.0, 1.0, 0); texts["m3.pdf"] = ""
            if arm == "hyb" and hyb_empty_doc and r == "a":
                texts["m5.pdf"] = "   "
            write_leg(c, f"p2c_{arm}_{r}", "rr", docs, texts=texts)
    return c


def test_c_smoke(tmp: Path) -> None:
    print("G_smoke_C")
    # fix p50 1.0 / 1.02 (spread ~2%); hyb 0.90 (10% lower) -> (a) holds; pure 0.99 (~2% lower, inside spread) -> fails (a)
    c = c_camp(tmp, "c1", {"fix": (1.0, 1.02), "hyb": (0.90, 0.90), "pure": (0.99, 1.0)}, pure_empty_doc=True)
    check("c_smoke evaluates (exit 0)", gate(c, "c_smoke") == 0)
    r = json.loads((c / "gates" / "G_smoke_C.json").read_text())
    pv = r["per_variant"]
    check("HYBRID (a) holds at 10% lower vs ~2% spread", pv["hyb"]["a"]["holds"] is True, json.dumps(pv["hyb"]["a"]))
    check("HYBRID (b) holds (no loss)", pv["hyb"]["b"]["holds"] is True)
    check("HYBRID fires", r["fired_variants"] == ["hybrid"], str(r["fired_variants"]))
    check("null control: PURE (a) fails inside Tika's spread", pv["pure"]["a"]["holds"] is False)
    check("null control: PURE (b) fails and names the document", pv["pure"]["b"]["L_V"] == ["m3.pdf"], str(pv["pure"]["b"]))
    check("p50 is the true median (6th of 11)", abs(pv["hyb"]["a"]["V_mean_s"] - 0.90) < 1e-9, str(pv["hyb"]["a"]["V_mean_s"]))
    c = c_camp(tmp, "c2", {"fix": (1.0, 1.02), "hyb": (0.90, 0.90), "pure": (0.5, 0.5)}, pure_empty_doc=False, hyb_empty_doc=True)
    gate(c, "c_smoke")
    r = json.loads((c / "gates" / "G_smoke_C.json").read_text())
    check("null control: whitespace-only HYBRID text fails (b)", r["per_variant"]["hyb"]["b"]["L_V"] == ["m5.pdf"])
    check("PURE fires when faster and no loss", r["fired_variants"] == ["pure"], str(r["fired_variants"]))


def test_manip_b(tmp: Path) -> None:
    print("G_manip_B (on P1's banked E2 read-backs)")
    c = tmp / "mb"
    c.mkdir()
    for src, dst in (("e2_rr_off_a", "base_leg"), ("e2_li_off_a", "li_leg")):
        (c / dst).mkdir()
        for f in (P1 / src).glob("*"):
            if f.name == "p1_readback.json" or f.name.startswith("preflight_"):
                shutil.copy(f, c / dst / f.name)
    check("P1 RR untraced leg passes as baseline (debugger loaded, no malloc)", gate(c, "manip_b", "base_leg", "base") == 0)
    c2 = tmp / "mb2"; shutil.copytree(c, c2, ignore=shutil.ignore_patterns("gates"))
    check("null control: the same leg FAILS as COMBINED", gate(c2, "manip_b", "base_leg", "comb") == 1)
    c3 = tmp / "mb3"; shutil.copytree(c, c3, ignore=shutil.ignore_patterns("gates"))
    check("null control: the LlamaIndex leg (malloc=2 but no on-token probe) FAILS as COMBINED", gate(c3, "manip_b", "li_leg", "comb") == 1)
    # a synthetic COMBINED: the RR leg with the debugger gone and MALLOC_ARENA_MAX=2
    c4 = tmp / "mb4"; shutil.copytree(c, c4, ignore=shutil.ignore_patterns("gates"))
    rb = json.loads((c4 / "base_leg" / "p1_readback.json").read_text())
    rb["env"]["MALLOC_ARENA_MAX"] = "2"; rb["monitoring_tools"] = {}
    (c4 / "base_leg" / "p1_readback.json").write_text(json.dumps(rb))
    pf = next((c4 / "base_leg").glob("preflight_*.json"))
    j = json.loads(pf.read_text())
    for k in ("d0_pre", "d0_post"):
        if (j.get("p0") or {}).get(k):
            j["p0"][k]["trace"]["pydevd_loaded"] = False
            j["p0"][k]["trace"]["sys_monitoring_tools"] = {}
    pf.write_text(json.dumps(j))
    check("a synthetic COMBINED read-back passes as COMBINED", gate(c4, "manip_b", "base_leg", "comb") == 0)
    c5 = tmp / "mb5"; shutil.copytree(c4, c5, ignore=shutil.ignore_patterns("gates"))
    check("null control: that COMBINED read-back FAILS as baseline", gate(c5, "manip_b", "base_leg", "base") == 1)


def test_nodebug() -> None:
    print("driver_video P2_NODEBUG injection")
    sys.path.insert(0, str(ROOT / "working" / "video"))
    src = (ROOT / "working" / "video" / "driver_video.py").read_text()
    ns: dict = {"Dict": dict, "Any": object}
    start = src.index("async def _use_nodebug")
    end = src.index("\n\n\n", start)
    exec(src[start:end], ns)
    calls = []

    class Fake:
        async def call(self, method, **a):
            calls.append((method, a))
            return {"token": "t"}

        async def use(self, **kw):
            await self.call("validate", pipeline=1)
            return await self.call("execute", **kw)

    f = Fake()
    orig = f.call
    out = asyncio.run(ns["_use_nodebug"](f, {"filepath": "p", "ttl": 0}))
    check("execute carries noDebug=True", calls[1] == ("execute", {"filepath": "p", "ttl": 0, "noDebug": True}), str(calls))
    check("other calls untouched", calls[0] == ("validate", {"pipeline": 1}))
    check("client.call restored after use()", f.call == orig and out == {"token": "t"})
    check("OFF by default (env unset)", "P2_NODEBUG = os.environ.get('P2_NODEBUG', '') not in ('', '0')" in src)


def test_record(tmp: Path) -> None:
    print("p2_pdfium_build RECORD selection")
    rec = tmp / "RECORD"
    rows = [["pypdfium2/__init__.py", "", ""], ["pypdfium2_raw/bindings.py", "", ""], ["pypdfium2_cfg/__init__.py", "", ""],
            ["pypdfium2_cli/__main__.py", "", ""], ["pypdfium2-5.13.0.dist-info/RECORD", "", ""], ["../../../bin/pypdfium2", "", ""]]
    with open(rec, "w", newline="") as f:
        csv.writer(f).writerows(rows)
    sh = (ROOT / "working" / "scripts" / "p2_pdfium_build.sh").read_text()
    snippet = sh[sh.index("<<'PYREC'\n", sh.index("TOPS=")) + len("<<'PYREC'\n"):sh.index("PYREC\n)", sh.index("TOPS="))]
    out = subprocess.run([sys.executable, "-", str(rec)], input=snippet, capture_output=True, text=True).stdout.split()
    check("all top-level entries incl. pypdfium2_cfg and the dist-info; console script excluded",
          out == ["pypdfium2", "pypdfium2-5.13.0.dist-info", "pypdfium2_cfg", "pypdfium2_cli", "pypdfium2_raw"], str(out))


def main() -> int:
    with tempfile.TemporaryDirectory() as t:
        tmp = Path(t)
        test_memstat(tmp)
        test_a_smoke(tmp)
        test_node_c(tmp)
        test_c_smoke(tmp)
        test_manip_b(tmp)
        test_nodebug()
        test_record(tmp)
    n, ok = len(RESULTS), sum(RESULTS)
    print(f"\np2 tooling: {ok} pass, {n - ok} fail")
    return 0 if ok == n else 1


if __name__ == "__main__":
    sys.exit(main())
