#!/usr/bin/env python3
"""Characterise the NUL-truncation defect to filing standard.

The weekend run surfaced it on one 348 KB PDF. A maintainer will not accept that. This reduces it
to a minimal reproducer with no PDF involved, establishes scope and boundaries, determines whether
the loss is inbound or outbound, and checks the other control characters.

Each sub-test is independent and prints PASS/FAIL against an explicit expectation, so the output
can be pasted into an issue.
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import time
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "working"))


async def send(text: str, tag: str) -> dict:
    """One document through the canonical 4-node pipeline. Unique project_id per call."""
    from rocketride import RocketRideClient
    base = json.loads((ROOT / "working" / "pipes" / "embed_probe.pipe").read_text())
    base["project_id"] = str(uuid.uuid5(uuid.NAMESPACE_DNS,
                                        f"nulchar-{tag}-{os.getpid()}-{time.time()}"))
    p = ROOT / "working" / "pipes" / "generated" / f"nulchar_{tag}_{os.getpid()}.pipe"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(base))
    c = RocketRideClient()
    await c.connect(timeout=60000)
    tok = (await c.use(filepath=str(p.relative_to(ROOT))))["token"]
    try:
        out = await asyncio.wait_for(c.send(tok, text, mimetype="text/plain"), timeout=600)
    finally:
        try:
            await asyncio.wait_for(c.terminate(tok), timeout=60)
        except Exception:
            pass
        try:
            await c.disconnect()
        except Exception:
            pass
    return out


def run(text: str, tag: str):
    out = asyncio.run(send(text, tag))
    docs = out.get("documents") or []
    return ([d.get("page_content", "") for d in docs],
            [d.get("embedding") or [] for d in docs], docs, out)


def main() -> int:
    results = {}

    # (a) MINIMAL REPRODUCER — no PDF, no large file, one string, one assertion
    print("=" * 96)
    print("(a) MINIMAL REPRODUCER — plain string through the API, no PDF involved")
    print("=" * 96)
    text = "AAAA\x00BBBB"
    ch, vc, _, _ = run(text, "min")
    got = ch[0] if ch else ""
    print(f"  sent    : {text!r}   (len {len(text)})")
    print(f"  returned: {got!r}   (len {len(got)})")
    print(f"  EXPECTED 'AAAA\\x00BBBB' (9 chars) — ACTUAL {got!r} ({len(got)} chars)")
    ok = got == text
    print(f"  => {'PASS (no truncation)' if ok else 'FAIL — TRUNCATED AT THE NUL'}")
    results["minimal"] = {"sent": repr(text), "returned": repr(got), "truncated": not ok}

    # (b) SCOPE — is it PDF-specific?
    print("\n" + "=" * 96)
    print("(b) SCOPE — the reproducer above used no PDF at all, so the defect is in the")
    print("    text path, not the PDF reader. Confirming with a second, longer plain string.")
    print("=" * 96)
    t2 = ("The quick brown fox. " * 50) + "\x00" + ("SHOULD SURVIVE. " * 50)
    ch2, _, _, _ = run(t2, "scope")
    g2 = ch2[0] if ch2 else ""
    exp_cut = t2.index("\x00")
    print(f"  sent len {len(t2)}, NUL at {exp_cut}, returned len {len(g2)}")
    print(f"  => {'TRUNCATED AT NUL — not PDF-specific' if len(g2) == exp_cut else 'not truncated at NUL'}")
    results["scope_plain_text"] = {"sent_len": len(t2), "nul_at": exp_cut, "returned_len": len(g2)}

    # (c) OTHER CONTROL CHARACTERS
    print("\n" + "=" * 96)
    print("(c) OTHER CONTROL CHARACTERS — \\x01..\\x1f and \\x7f. Does only NUL truncate?")
    print("=" * 96)
    trunc, survived = [], []
    for code in list(range(0x00, 0x20)) + [0x7F]:
        c = chr(code)
        t = f"AAAA{c}BBBB"
        ch3, _, _, _ = run(t, f"cc{code:02x}")
        g = ch3[0] if ch3 else ""
        # \n and \r are legitimately reformatted by a text pipeline; judge on LENGTH LOSS only
        lost = len(g) < len(t)
        (trunc if lost else survived).append((code, len(g), len(t)))
        print(f"  \\x{code:02x}  sent {len(t)}  returned {len(g)}  {'LOST' if lost else 'ok'}")
    print(f"\n  truncating: {[f'0x{c:02x}' for c, _, _ in trunc]}")
    print(f"  surviving : {len(survived)} of {len(trunc) + len(survived)} control chars")
    results["control_chars"] = {"truncating": [f"0x{c:02x}" for c, _, _ in trunc],
                                "n_surviving": len(survived)}

    # (d) OTHER FIELDS
    print("\n" + "=" * 96)
    print("(d) OTHER FIELDS — is only page_content affected?")
    print("=" * 96)
    ch4, vc4, docs4, out4 = run("HEAD\x00TAIL", "fields")
    if docs4:
        d0 = docs4[0]
        for k, v in d0.items():
            sv = repr(v)[:70] if not isinstance(v, list) else f"<list len {len(v)}>"
            print(f"  documents[0].{k:18s} = {sv}")
    print(f"  top-level response keys: {list(out4.keys())}")
    results["fields"] = {"doc_keys": list(docs4[0].keys()) if docs4 else [],
                         "top_keys": list(out4.keys())}

    # (e) BOUNDARY CASES
    print("\n" + "=" * 96)
    print("(e) BOUNDARY — NUL at position 0, mid, final byte, and multiple NULs")
    print("=" * 96)
    cases = {"leading": "\x00ABCDEFGH", "mid": "ABCD\x00EFGH", "trailing": "ABCDEFGH\x00",
             "multiple": "AB\x00CD\x00EF\x00GH", "only_nul": "\x00",
             "nul_run": "AB\x00\x00\x00CD"}
    bound = {}
    for name, t in cases.items():
        ch5, _, _, _ = run(t, f"b{name}")
        g = ch5[0] if ch5 else ""
        first = t.find("\x00")
        bound[name] = {"sent": repr(t), "returned": repr(g), "sent_len": len(t),
                       "returned_len": len(g), "first_nul": first,
                       "cut_at_first_nul": len(g) == first}
        print(f"  {name:10s} sent {repr(t):24s} -> {repr(g):20s} "
              f"(first NUL at {first}, returned {len(g)}) "
              f"{'cut at first NUL' if len(g) == first else 'OTHER'}")
    results["boundary"] = bound

    # (f) DIRECTION — inbound or outbound?
    print("\n" + "=" * 96)
    print("(f) DIRECTION — was the text lost BEFORE embedding (inbound) or only in the")
    print("    response (outbound)? Decided by comparing embeddings, not by inference.")
    print("=" * 96)
    from ws1.pipeline import LlamaIndexPipeline
    pl = LlamaIndexPipeline(model_name="sentence-transformers/multi-qa-MiniLM-L6-cos-v1",
                            chunk_size=4000, chunk_overlap=200, device="cpu")
    pl.warm()
    import math

    def cos(a, b):
        return (sum(x * y for x, y in zip(a, b)) /
                (math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b))))

    probe = "Machine learning systems process documents. " * 20 + "\x00" + \
            "Distinctive tail content about quantum chromodynamics. " * 20
    ch6, vc6, _, _ = run(probe, "dir")
    full_vec = pl.embed([probe])[0]                  # embedding of the FULL text
    trunc_vec = pl.embed([probe[:probe.index(chr(0))]])[0]   # embedding of the TRUNCATED text
    rr_vec = vc6[0]
    c_full = cos(rr_vec, full_vec)
    c_trunc = cos(rr_vec, trunc_vec)
    print(f"  returned text length   : {len(ch6[0])} (sent {len(probe)}, NUL at {probe.index(chr(0))})")
    print(f"  cos(RR vector, embedding of FULL text)      = {c_full:.4f}")
    print(f"  cos(RR vector, embedding of TRUNCATED text) = {c_trunc:.4f}")
    verdict = ("OUTBOUND — the engine embedded the FULL text; only the response text is lost"
               if c_full > c_trunc else
               "INBOUND — the engine never saw the text past the NUL")
    print(f"  => {verdict}")
    results["direction"] = {"cos_full": round(c_full, 4), "cos_truncated": round(c_trunc, 4),
                            "verdict": verdict}

    (ROOT / "working" / "results").mkdir(parents=True, exist_ok=True)
    from harness.resultio import write_result
    p = write_result("nul_characterization", results)
    print(f"\n  written -> {p.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
