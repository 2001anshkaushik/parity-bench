#!/usr/bin/env python3
"""Regression tests — every defect found in this project becomes a test that fails if it returns.

Each test names the incident it guards. A test here is not hypothetical: each one corresponds to a
defect that actually produced a wrong number or lost data.

Run:  ../.venv/bin/python working/scripts/regression_selftest.py
Exit: 0 all pass, 1 any fail.  Tests needing a live engine are SKIPPED (not failed) when it is down.
"""
from __future__ import annotations

import json, math, os, subprocess, sys, time, uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "working"))

PASS, FAIL, SKIP, XFAIL, XPASS = [], [], [], [], []

# Defects that are OPEN UPSTREAM: the test SHOULD fail today. Marking them xfail keeps the suite
# green and meaningful, while turning an unexpected PASS into a signal that the bug was fixed and
# the test must be promoted to a hard requirement (so a later regression is caught).
KNOWN_OPEN = {"nul_truncation": "RocketRide 3.3.1.35 — see publishable/BUG_NUL_TRUNCATION.md"}


def check(name, incident, fn):
    try:
        r = fn()
        if r == "skip":
            SKIP.append((name, incident)); print(f"  SKIP  {name:36s} {incident}")
        elif name in KNOWN_OPEN:
            XPASS.append(name)
            print(f"  XPASS {name:36s} FIXED UPSTREAM — promote to a hard requirement")
        else:
            PASS.append(name); print(f"  PASS  {name:36s} {incident}")
    except AssertionError as e:
        if name in KNOWN_OPEN:
            XFAIL.append((name, KNOWN_OPEN[name]))
            print(f"  XFAIL {name:36s} known open: {KNOWN_OPEN[name]}")
        else:
            FAIL.append((name, str(e))); print(f"  FAIL  {name:36s} {e}")
    except Exception as e:
        if name in KNOWN_OPEN:
            XFAIL.append((name, KNOWN_OPEN[name]))
            print(f"  XFAIL {name:36s} known open: {KNOWN_OPEN[name]}")
        else:
            FAIL.append((name, f"{type(e).__name__}: {e}"))
            print(f"  FAIL  {name:36s} {type(e).__name__}: {e}")


def engine_up():
    try:
        import urllib.request
        urllib.request.urlopen("http://127.0.0.1:5565/version", timeout=5).read()
        return True
    except Exception:
        return False


# ---------------------------------------------------------------- 1. NUL truncation
def t_nul_truncation():
    """Session 13: page_content silently truncated at the first NUL; embedding was correct."""
    if not engine_up():
        return "skip"
    import asyncio
    from rocketride import RocketRideClient

    async def go():
        base = json.loads((ROOT / "working" / "pipes" / "embed_probe.pipe").read_text())
        base["project_id"] = str(uuid.uuid5(uuid.NAMESPACE_DNS, f"reg-nul-{os.getpid()}-{time.time()}"))
        p = ROOT / "working" / "pipes" / "generated" / f"reg_nul_{os.getpid()}.pipe"
        p.parent.mkdir(parents=True, exist_ok=True); p.write_text(json.dumps(base))
        c = RocketRideClient(); await c.connect(timeout=60000)
        tok = (await c.use(filepath=str(p.relative_to(ROOT))))["token"]
        try:
            out = await asyncio.wait_for(c.send(tok, "AAAA\x00BBBB", mimetype="text/plain"), timeout=300)
        finally:
            try: await asyncio.wait_for(c.terminate(tok), timeout=60)
            except Exception: pass
            await c.disconnect()
        return out
    out = asyncio.run(go())
    got = (out.get("documents") or [{}])[0].get("page_content", "")
    assert got == "AAAA\x00BBBB", (
        f"NUL TRUNCATION STILL PRESENT: sent 9 chars, got {len(got)} ({got!r}). "
        f"See publishable/BUG_NUL_TRUNCATION.md")


# ---------------------------------------------------------------- 2. engine matched by PID
def t_engine_pid_not_name():
    """Session 13: name matching counted a 5-day-old unrelated engine (104 MB, 5.8% of median)."""
    import importlib.util
    spec = importlib.util.spec_from_file_location("w", ROOT / "weekend_worker.py")
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
    src = (ROOT / "weekend_worker.py").read_text()
    assert "lsof" in src, "engine PID lookup no longer uses lsof (psutil.net_connections needs root)"
    assert "engine_tree_rss_mb(self.engine_pid)" in src, \
        "RocketArm.rss() is not passing the resolved PID — it has fallen back to name matching"
    if not engine_up():
        return "skip"
    pid = m.RocketArm._engine_pid()
    assert pid is not None, "engine PID did not resolve while the engine is up"
    out = subprocess.run(["lsof", "-nP", "-iTCP:5565", "-sTCP:LISTEN"],
                         capture_output=True, text=True).stdout
    holders = [l.split()[1] for l in out.splitlines()[1:] if len(l.split()) > 1]
    assert str(pid) in holders, f"resolved PID {pid} does not hold port 5565 ({holders})"


# ---------------------------------------------------------------- 3. non-fatal content gate
def t_gate_non_fatal():
    """Session 13: one pathological document ended a 16-hour phase at 2.7% completion."""
    src = (ROOT / "weekend_worker.py").read_text()
    assert "consecutive_gp" in src, "the consecutive-failure counter is gone"
    assert "consecutive_gp >= 25" in src, "systemic-abort threshold missing"
    i = src.index("except GoodputFailure")
    seg = src[i:i + 1400]
    assert "return EXIT_ERR" not in seg.split("if consecutive_gp")[0], \
        "a single goodput failure aborts the phase again"


# ---------------------------------------------------------------- 4. warm-up excluded from slope
def t_slope_excludes_rampup():
    """Session 13: +1,505 MB/1k was warm-up ramp plus endpoint luck across a ±500 MB oscillation."""
    # weekend_summarise.py runs its body at import time, which would regenerate the summary as a
    # side effect of running tests. Extract just the function instead.
    import types
    src = (ROOT / "weekend_summarise.py").read_text()
    start = src.index("def slope(")
    end = src.index("\nrows = []")
    m = types.ModuleType("slope_only")
    exec(compile(src[start:end], "slope_only", "exec"), m.__dict__)
    short = [{"n": i, "rss_mb": 1000 + i * 5} for i in range(5, 270, 5)]   # 267-doc window
    assert m.slope(short) is None, "a 267-document window still yields a slope"
    long_flat = [{"n": i, "rss_mb": 1000 + (i % 7)} for i in range(5, 10000, 5)]
    s = m.slope(long_flat)
    assert s is not None and abs(s) < 5, f"flat 10k-doc series should be ~0, got {s}"


# ---------------------------------------------------------------- 5. content sanity
def t_content_sanity():
    """Session 13: the goodput gate passed 39,803 chars of binary as 11 valid vectors."""
    from harness.content_sanity import inspect, classify, PRINTABLE_RATIO_MIN
    garbage = "".join(chr(i % 32) for i in range(5000))
    g = inspect(garbage)
    assert g["suspect"], "binary noise not flagged"
    assert g["low_printable"], f"printable ratio {g['printable_ratio']} not below {PRINTABLE_RATIO_MIN}"
    clean = "The quick brown fox jumps over the lazy dog. " * 200
    c = inspect(clean)
    assert not c["suspect"], f"legitimate text falsely flagged: {c}"
    n = inspect("head\x00tail")
    assert n["has_nul"] and n["suspect"], "NUL presence not detected"
    assert classify(clean) == "ok" and classify(garbage).startswith("garbage")
    # the measured separation the threshold rests on
    assert PRINTABLE_RATIO_MIN < 0.9757, "threshold has risen above the lowest legitimate document"
    assert PRINTABLE_RATIO_MIN > 0.7003, "threshold has fallen below the known-garbage document 267"


# ---------------------------------------------------------------- 6. result writes cannot collide
def t_resultio_no_clobber():
    """Session 11: two runs were destroyed by hardcoded result paths."""
    from harness.resultio import write_result, ResultCollision, RESULTS
    a = write_result("regression_probe", {"v": 1})
    b = write_result("regression_probe", {"v": 2})
    assert a != b, "two writes produced the same path"
    try:
        fd = os.open(a, os.O_WRONLY | os.O_CREAT | os.O_EXCL); os.close(fd)
        raise AssertionError("O_EXCL did not prevent overwriting an existing result")
    except FileExistsError:
        pass
    for f in RESULTS.glob("regression_probe__*.json"):
        f.unlink()


# ---------------------------------------------------------------- 7. goodput gate still strict
def t_goodput_gate_shape():
    """Sessions 12-13: the gate must still catch the six shape failures it was built for."""
    from harness.goodput import check_document, GoodputFailure
    cases = [([], []), ([""], [[0.0] * 384]), (["x"], [[0.0] * 384]),
             (["x"], [[0.1] * 768]), (["a", "b"], [[0.05] * 384])]
    for ch, vc in cases:
        try:
            check_document("t", ch, vc)
            raise AssertionError(f"gate failed to catch {ch!r}")
        except GoodputFailure:
            pass
    v = [1 / math.sqrt(384)] * 384
    w = [0.0] * 384; w[0] = 1.0
    check_document("good", ["alpha", "beta"], [v, w])


# ---------------------------------------------------------------- 8. setsid trap
def t_no_setsid():
    """Sessions 12-13: `nohup setsid ...` dies instantly on macOS; it cost 2h once and recurred."""
    bad = []
    for f in list(ROOT.glob("*.sh")) + list((ROOT / "working" / "scripts").glob("*.sh")):
        if "setsid" in f.read_text():
            bad.append(f.name)
    assert not bad, f"setsid used in {bad} — not available on macOS"



# ---------------------------------------------------------------- 9. arms' thread settings match
def t_thread_settings_matched():
    """Session 14: a full 10,000-document comparison ran with RocketRide on 1 thread and
    LlamaIndex on 10, and nothing detected it. The mismatch was invisible for the whole run."""
    src = (ROOT / "matched_replication.py").read_text()
    assert "def assert_matched" in src, "the run-start thread-matching assertion is gone"
    assert "REFUSING TO RUN" in src, "the assertion no longer refuses to run on mismatch"
    assert "if et == 1" in src, "the both-arms-pinned guard is gone (matched but not best)"
    assert "len(med) >= 3" in src, "the gate no longer requires n>=3 (n=1 passes trivially)"
    # An engine answering on :5565 is NOT the same as THIS tree being able to drive one — a bare
    # clone has no engine/ (PROVISIONING §1) yet still sees a neighbouring engine on the port, and
    # then fails opaquely inside probe_env. Require both, or skip.
    if not engine_up() or not (ROOT / "engine").is_dir():
        return "skip"
    import importlib.util
    spec = importlib.util.spec_from_file_location("mr", ROOT / "matched_replication.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    et, lt = m.engine_threads(), m.llama_threads()
    assert et == lt, (
        f"ARMS ARE NOT MATCHED: engine task process reports {et} torch threads, LlamaIndex "
        f"reports {lt}. This is the session-14 defect. See publishable/FAIRNESS_BASIS.md")
    assert et > 1, (
        f"both arms pinned to {et} thread — matched, but not each arm's best at concurrency 1 "
        f"(unpinned is 3.07x/3.26x better)")


# ---------------------------------------------------------------- 11. node match fails loudly
def t_node_mark_fails_loudly():
    """A clone named anything but `benchmark-A` made the engine-node match string find nothing,
    so counts() reported 0 node processes and kill_orphans() reported a clean teardown while
    leaving every orphan running. Zero looked exactly like a healthy idle engine.

    Driven against a SYNTHETIC process table, so it needs no engine and cannot be fooled by
    whatever happens to be running on the host."""
    import importlib, types
    import psutil as _ps

    class FakeProc:
        def __init__(self, pid, cmd):
            self.info = {"pid": pid, "cmdline": cmd.split(" "),
                         "uids": types.SimpleNamespace(real=os.getuid())}

    # a renamed clone: real engine nodes running, none of them under `benchmark-A/`
    renamed = [FakeProc(1, "/x/parity-bench/engine/bin/python /x/parity-bench/engine/ai/node.py t1"),
               FakeProc(2, "/x/parity-bench/engine/bin/python /x/parity-bench/engine/ai/node.py t2")]
    # the tree the default pattern was written for
    original = [FakeProc(3, "/x/benchmark-A/engine/bin/python /x/benchmark-A/engine/ai/node.py t1")]

    real_iter = _ps.process_iter
    try:
        import harness.engine_ops as eo
        eo = importlib.reload(eo)

        # --- direction 1: pattern matches nothing while nodes exist -> must RAISE, not return 0
        _ps.process_iter = lambda *a, **k: iter(renamed)
        for fn, label in ((eo.counts, "counts"), (eo.kill_orphans, "kill_orphans"),
                          (eo.check_node_mark, "check_node_mark")):
            try:
                fn()
            except eo.NodeMarkStale as e:
                msg = str(e)
                assert "RR_NODE_MARK" in msg, f"{label} error does not name the env var override"
                assert eo.NODE_MARK in msg, f"{label} error does not name the pattern in use"
                assert "node.py" in msg, f"{label} error shows no example cmdline"
            else:
                raise AssertionError(
                    f"{label}() returned silently while 2 engine node processes were running — "
                    f"this is the silent-zero defect")

        # --- direction 2: the override makes it resolve again
        os.environ["RR_NODE_MARK"] = "engine/ai/node.py"
        eo = importlib.reload(eo)
        assert eo.counts()["node_procs"] == 2, "RR_NODE_MARK override did not take effect"

        # --- direction 3 (null control): default pattern, matching tree -> no raise, correct count
        del os.environ["RR_NODE_MARK"]
        eo = importlib.reload(eo)
        _ps.process_iter = lambda *a, **k: iter(original)
        assert eo.counts()["node_procs"] == 1, "default pattern broke on the tree it was written for"

        # --- direction 4 (null control): idle engine -> 0 nodes, and that must NOT raise
        _ps.process_iter = lambda *a, **k: iter([])
        assert eo.counts()["node_procs"] == 0, "idle engine should report 0"
        assert eo.check_node_mark()["conclusive"] is False, "idle table cannot confirm the pattern"
    finally:
        _ps.process_iter = real_iter
        os.environ.pop("RR_NODE_MARK", None)
        import harness.engine_ops as eo2
        importlib.reload(eo2)


# ---------------------------------------------------------------- 12. chunk-hash content gate
def t_chunk_hash_gate():
    """The vector-shape gate passes on truncated content; the chunk-hash gate does not.

    Approach adopted from Leela's bench_langgraph_prod (pdf1k/ground_truth.py). The embedder
    truncates at 512 tokens while chunks are ~4,000 chars, so cosine similarity cannot see content
    lost in a chunk's tail. Hashing the text can.

    Runs entirely offline against the reference splitter — no engine, no service, no corpus."""
    from harness.chunk_hash import (check_chunks, reference_chunks, effective_config,
                                    ChunkHashMismatch)
    from harness.goodput import check_document

    cfg = effective_config()
    assert cfg["chunk_size"] == 4000 and cfg["chunk_overlap"] == 200, (
        f"splitter defaults moved: {cfg} — every chunk hash in the archive was computed at 4000/200")

    text = ("Alpha beta gamma delta epsilon. " * 60) + "\x00" + ("Zeta eta theta iota kappa. " * 400)
    ref = reference_chunks(text)
    assert len(ref) > 1, "fixture must span multiple chunks or the count check cannot be exercised"

    # --- null control: the reference must accept itself
    check_chunks("self", ref, text)

    # --- content truncated at the NUL (the documented engine defect) must FAIL
    truncated = [ref[0].split("\x00")[0]] + ref[1:]
    try:
        check_chunks("truncated", truncated, text)
    except ChunkHashMismatch as e:
        assert "NUL" in str(e) or "SHORTER" in str(e), f"mismatch not diagnosed: {e}"
    else:
        raise AssertionError("chunk-hash gate accepted NUL-truncated content — it cannot fail")

    # --- and the OLD gate must pass on that same input, which is why this test exists
    dim = 384
    vecs = [[1.0] + [0.0] * (dim - 1) if i % 2 == 0 else [0.0, 1.0] + [0.0] * (dim - 2)
            for i in range(len(truncated))]
    check_document("truncated", truncated, vecs)      # shape-valid, content wrong -> passes

    # --- wrong chunk count must FAIL with a count-specific message
    try:
        check_chunks("dropped", ref[:-1], text)
    except ChunkHashMismatch as e:
        assert "COUNT" in str(e), f"count mismatch not diagnosed as a count problem: {e}"
    else:
        raise AssertionError("chunk-hash gate accepted a dropped chunk")

    # --- missing the text+'\n' transform must FAIL (Leela's Stage 0/1 finding)
    from langchain_text_splitters import RecursiveCharacterTextSplitter
    no_nl = RecursiveCharacterTextSplitter(
        chunk_size=4000, chunk_overlap=200, length_function=len).split_text(text)
    if hash(tuple(no_nl)) != hash(tuple(ref)):
        try:
            check_chunks("no-newline", no_nl, text)
        except ChunkHashMismatch:
            pass
        else:
            raise AssertionError("gate did not notice the missing text+newline transform")


# ---------------------------------------------------------------- 10. artifact protected content
def t_artifact_protected_content():
    """Sessions 16 and 17: an edit to MEETING_2026-08-10.md destroyed the thread-asymmetry
    disclosure — twice. Once by rewriting section 2 wholesale. The disclosure is the document's
    strongest credibility signal and must survive any edit, so it is asserted structurally rather
    than remembered."""
    f = ROOT / "publishable" / "MEETING_2026-08-10.md"
    assert f.exists(), "the meeting artifact is missing"
    t = f.read_text()
    required = {
        "thread-asymmetry table":      "measured inside the process",
        "handicap stated plainly":     "disadvantageous configuration",
        "endurance marked VOID":       "VOID, not correctable",
        "both thread counts named":    "**1** (pinned)",
        "matched-config disclosure":   "torch intra-op threads",
        "goodput equivalence lead":    "functional equivalence",
        "no-reversal caveat":          "not a reversal claim",
        "leak claim withdrawn":        "is WITHDRAWN",
    }
    missing = [name for name, marker in required.items() if marker not in t]
    assert not missing, (
        f"PROTECTED CONTENT REMOVED from MEETING_2026-08-10.md: {missing}. "
        f"These were destroyed by an edit twice before. Restore them; do not delete the "
        f"disclosure to make the artifact read better.")
    # the withdrawn figures must not reappear as live claims
    import re
    for label, pat in (("1.73x", r"1\.73\s*[x\u00d7]"), ("31.3% decay", r"31\.3\s*%"),
                       ("1.76x peak/median", r"1\.76\s*[x\u00d7]")):
        for m in re.finditer(pat, t):
            ctx = t[max(0, m.start()-160):m.start()+60]
            assert any(w in ctx for w in ("withdraw", "WITHDRAWN", "superseded", "SUPERSEDED",
                                          "corrected", "CORRECTION")), \
                f"withdrawn figure {label} appears without a withdrawal marker nearby"

if __name__ == "__main__":
    print("=" * 92); print("REGRESSION SELFTEST — one test per defect that produced a wrong number")
    print("=" * 92)
    check("nul_truncation", "page_content truncated at first NUL", t_nul_truncation)
    check("engine_pid_not_name", "engine matched by PID, not name", t_engine_pid_not_name)
    check("gate_non_fatal", "one bad doc must not end a phase", t_gate_non_fatal)
    check("slope_excludes_rampup", "no slope from a too-short window", t_slope_excludes_rampup)
    check("content_sanity", "garbage content detected, clean text not", t_content_sanity)
    check("resultio_no_clobber", "result writes cannot collide", t_resultio_no_clobber)
    check("goodput_gate_shape", "the six shape failures still caught", t_goodput_gate_shape)
    check("no_setsid", "setsid never used (absent on macOS)", t_no_setsid)
    check("thread_settings_matched", "both arms same in-process thread count",
          t_thread_settings_matched)
    check("node_mark_fails_loudly", "engine-node match errors instead of returning 0",
          t_node_mark_fails_loudly)
    check("chunk_hash_gate", "content verified by hash, not vector shape", t_chunk_hash_gate)
    check("artifact_protected_content", "disclosure + VOID markers survive edits",
          t_artifact_protected_content)
    print("=" * 92)
    print(f"  {len(PASS)} passed, {len(FAIL)} failed, {len(SKIP)} skipped, "
          f"{len(XFAIL)} xfail (known open upstream), {len(XPASS)} xpass")
    for n, e in FAIL:
        print(f"    FAILED {n}: {e[:150]}")
    for n, why in XFAIL:
        print(f"    xfail  {n}: {why}")
    for n in XPASS:
        print(f"    XPASS  {n}: bug appears FIXED — remove from KNOWN_OPEN so regressions fail")
    sys.exit(1 if FAIL else 0)
