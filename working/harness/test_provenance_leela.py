#!/usr/bin/env python3
"""Regression test for `provenance_leela.build()`'s patch fields (DOCS_HANDOFF.md §10.1).

The defect: from 17 Aug to 7 Sep 2026 `build()` hardcoded `duplication_patch_applied: False`,
so every measured docs export carried a false record — on the patched engine AND on the
LlamaIndex arm, which has no engine to patch. The contract now: the field is READ from the
image label; "1" -> True, "0" -> False, anything unreadable -> None, NEVER False.

Three layers, cheapest first, and the planted-defect control runs before the clean checks so a
checker that cannot fail is never allowed to pass:
  1. `build()` with the docker label reader stubbed: every branch of the contract.
  2. The module source carries no `"duplication_patch_applied": False` literal.
  4. check() is scoped by arm (Advisor R2): a RocketRide arm missing the patch fields
     FAILS; a LlamaIndex arm with None PASSES with the exemption LISTED in the output.
  3. Over the committed 18-Aug exports (when present in working/results — they live on main
     and docs-bench, not on video-bench before the import) and the committed correction
     artifact: on every arm whose image_digest matches a patched image, the re-emitted field
     is never False; on the LlamaIndex image it is None, not False.

Run: python3 working/harness/test_provenance_leela.py   (exit 1 on any FAIL)
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(ROOT / "working" / "scripts"))
from harness import provenance_leela as pvl  # noqa: E402
import provenance_correction_20260818 as corr  # noqa: E402

PATCHED_DIGEST = "sha256:073b43d8"     # rr:patched — every 18-Aug measured docs number rides it
STOCK_DIGEST = "sha256:5e83c803"       # rr:stock — the null control
LI_DIGEST = "sha256:3d2f1f43"          # ws1-llamaindex:x86_64 — no RocketRide patch label
RESULTS = ROOT / "working" / "results"

_fails: list[str] = []
_n = 0


def check(name: str, cond: bool, got: str = "") -> None:
    global _n
    _n += 1
    print(f"  {'PASS' if cond else 'FAIL'}  {name:70} {got}")
    if not cond:
        _fails.append(name)


def _build(container, labels):
    """build() with docker replaced by a label table {container: {key: value}}."""
    orig = pvl._docker_label
    pvl._docker_label = lambda c, k: (labels.get(c) or {}).get(k)
    try:
        return pvl.build(arm="rocketride_pdf", mode="test", corpus_sha="x", corpus_n=1,
                         offered_concurrency=1, configured_concurrency=1, warmup_policy="none",
                         timeout_s=1, parser="tika", chunk_size=4000, chunk_overlap=200,
                         embedding_model="m", container=container)
    finally:
        pvl._docker_label = orig


def layer1_contract() -> None:
    print("layer 1: build() against a stubbed label reader")
    A, I = pvl.PATCH_LABEL, pvl.PATCH_ID_LABEL
    pid = "preventDefault-after-embedding-flush"

    b = _build("rr", {"rr": {A: "1", I: pid}})
    check("label '1' -> applied True", b["duplication_patch_applied"] is True, repr(b["duplication_patch_applied"]))
    check("label '1' -> id from the id label", b["duplication_patch_id"] == pid, repr(b["duplication_patch_id"]))
    check("label '1' -> source names the label", A in b["duplication_patch_source"])
    check("label '1' -> Leela check passes on the patch fields",
          not {"duplication_patch_applied", "duplication_patch_id"} & set(pvl.check(b)["missing_fields"]))

    b = _build("rr", {"rr": {A: "0"}})
    check("label '0' -> applied False (measured stock)", b["duplication_patch_applied"] is False)
    check("label '0' -> id None", b["duplication_patch_id"] is None)
    check("label '0' -> id exempted in check()", "duplication_patch_id" in pvl.check(b)["exempted"])

    for label, tbl in (("absent label (LlamaIndex image)", {"li": {}}),
                       ("empty string", {"li": {A: ""}}),
                       ("'<no value>'", {"li": {A: "<no value>"}}),
                       ("docker unreachable (reader returns None)", {})):
        b = _build("li", tbl)
        check(f"{label} -> applied None", b["duplication_patch_applied"] is None, repr(b["duplication_patch_applied"]))
        check(f"{label} -> never False", b["duplication_patch_applied"] is not False)
        check(f"{label} -> id None", b["duplication_patch_id"] is None)
        gaps = pvl.check(b)["missing_fields"]
        check(f"{label} -> check() fails as missing, not publishable",
              "duplication_patch_applied" in gaps and "duplication_patch_id" in gaps, str(gaps))

    b = _build(None, {})
    check("no container -> applied None", b["duplication_patch_applied"] is None)
    check("no container -> never False", b["duplication_patch_applied"] is not False)

    b = _build("rr,rr2", {"rr": {A: "1", I: pid}, "rr2": {A: "1", I: pid}})
    check("two containers agreeing on '1' -> True", b["duplication_patch_applied"] is True)
    b = _build("rr,li", {"rr": {A: "1", I: pid}, "li": {}})
    check("patched engine + label-less LI container -> True (only readable value)", b["duplication_patch_applied"] is True)
    b = _build("rr,rr2", {"rr": {A: "1", I: pid}, "rr2": {A: "0"}})
    check("two containers disagreeing -> None (ambiguous)", b["duplication_patch_applied"] is None)
    check("disagreeing -> never False", b["duplication_patch_applied"] is not False)

    b = _build("rr", {"rr": {A: "yes"}})
    check("unparseable label 'yes' -> None", b["duplication_patch_applied"] is None)

    # The planted-defect control for layer 3's rule: a block that IS False on a patched
    # digest must be caught by the same predicate the artifact checks use.
    bad = {"image_digest": PATCHED_DIGEST + "0" * 56, "duplication_patch_applied": False}
    check("control: the layer-3 predicate flags a False-on-patched block", not _never_false_on_patched(bad))


def _never_false_on_patched(block: dict) -> bool:
    d = block.get("image_digest") or ""
    if d.startswith(PATCHED_DIGEST):
        return block.get("duplication_patch_applied") is not False
    return True


def layer2_source() -> None:
    print("layer 2: the module source")
    import inspect
    body = inspect.getsource(pvl.build)
    check("build() carries no `\"duplication_patch_applied\": False` literal",
          not re.search(r'"duplication_patch_applied"\s*:\s*False', body))
    check("build() delegates to _patch_state(container), scoped by is_rocketride_arm(arm)",
          "_patch_state(container) if is_rocketride_arm(arm)" in body and "NOT_APPLICABLE" in body)
    whole = (HERE / "provenance_leela.py").read_text()
    lits = [l for l in whole.splitlines() if re.search(r'"duplication_patch_applied"\s*:\s*False', l)
            and not l.lstrip().startswith(("#", "hardcoded"))]
    check("the only False literal in the module is the measured-stock branch (label '0')",
          len(lits) == 1 and "duplication_patch_id" in lits[0], str(lits))


def layer3_artifacts() -> None:
    print("layer 3: the committed 18-Aug exports and the correction artifact")
    exports = sorted(RESULTS.glob("smoke50_parser_in__20260818T*.json"))
    if not exports:
        print("  SKIP  smoke50_parser_in__20260818T*.json not under working/results on this "
              "branch (main-only until the docs-bench import) — export checks skipped")
    for p in exports:
        d = json.loads(p.read_text())["data"]
        pl = d.get("provenance_leela") or {}
        check(f"{p.name[:40]}: carries a provenance_leela block per arm", isinstance(pl, dict) and len(pl) == 2)
        # Evidence table built from the same day's artifacts, as the correction script does.
        ev = corr.digest_label_evidence([(q, json.loads(q.read_text()))
                                         for q in sorted(RESULTS.glob("*__20260818T*.json"))])
        check("evidence: the patched digest was read as label '1'",
              any(k.startswith(PATCHED_DIGEST) and v["label_raw"] == "1" for k, v in ev.items()), str({k[:19]: v['label_raw'] for k, v in ev.items()}))
        check("evidence: the stock digest was read as label '0'",
              any(k.startswith(STOCK_DIGEST) and v["label_raw"] == "0" for k, v in ev.items()))
        for arm, block in pl.items():
            digest = block.get("image_digest") or ""
            new = corr.corrected_block(block, ev)
            if digest.startswith(PATCHED_DIGEST):
                check(f"{p.name[:40]} / {arm}: original records the defect (False on patched digest)",
                      block.get("duplication_patch_applied") is False)
                check(f"{p.name[:40]} / {arm}: re-emitted field is True, never False",
                      new["duplication_patch_applied"] is True, repr(new["duplication_patch_applied"]))
                check(f"{p.name[:40]} / {arm}: re-emitted id is the patch id",
                      new["duplication_patch_id"] == "preventDefault-after-embedding-flush")
            elif digest.startswith(LI_DIGEST):
                check(f"{p.name[:40]} / {arm}: LlamaIndex image -> None, not False",
                      new["duplication_patch_applied"] is None and new["duplication_patch_id"] is None,
                      repr(new["duplication_patch_applied"]))
            else:
                check(f"{p.name[:40]} / {arm}: unexpected digest {digest[:19]}", False)
            check(f"{p.name[:40]} / {arm}: never False on a patched digest", _never_false_on_patched(new))

    arts = sorted(RESULTS.glob("provenance_correction_20260818__*.json"))
    check("correction artifact is committed under working/results", bool(arts), str([a.name for a in arts]))
    if not arts:
        return
    art = json.loads(arts[-1].read_text())["data"]
    check("correction artifact says originals untouched", art.get("originals_untouched") is True)
    n_blocks = 0
    for e in art["exports"]:
        for arm, r in (e.get("arms") or {}).items():
            n_blocks += 1
            blk = r["corrected_provenance_leela"]
            check(f"artifact {e['export'][:40]} / {arm}: never False on a patched digest", _never_false_on_patched(blk))
            if (blk.get("image_digest") or "").startswith(PATCHED_DIGEST):
                check(f"artifact {e['export'][:40]} / {arm}: True on the patched digest", blk["duplication_patch_applied"] is True)
            if (blk.get("image_digest") or "").startswith(LI_DIGEST):
                check(f"artifact {e['export'][:40]} / {arm}: None on the LlamaIndex digest", blk["duplication_patch_applied"] is None)
            check(f"artifact {e['export'][:40]} / {arm}: source stated", bool(blk.get("duplication_patch_source")))
    check("artifact re-emits at least the two smoke50 exports (4 arm blocks)", n_blocks >= 4, str(n_blocks))
    # Post-R2 supersession (2026-09-08): the newest artifact must be the recomputed one, name
    # what it supersedes, and show the LlamaIndex arm PASSING with the exemption listed.
    if art.get("supersedes"):
        sup = art["supersedes"]
        check("newest artifact names the artifact it supersedes", (RESULTS / sup["artifact"]).exists() and sup["artifact"] != arts[-1].name, str(sup.get("artifact")))
        check("newest artifact says WHY it supersedes (pre-R2 check on the LI arm)", "pre-R2" in sup.get("why", "") and "append-only" in sup.get("why", ""))
        check("newest artifact declares its check semantics", "arm=" in (art.get("check_semantics") or {}).get("check_after", ""))
        for e in art["exports"]:
            for arm, r in (e.get("arms") or {}).items():
                if arm.startswith("llamaindex"):
                    ca = r["check_after"]
                    check(f"artifact {e['export'][:40]} / {arm}: post-R2 check_after PASSES", ca["PASS"] is True, str(ca))
                    check(f"artifact {e['export'][:40]} / {arm}: exemption LISTED for both patch fields", ca.get("exempted") == sorted(pvl.PATCH_FIELDS), str(ca.get("exempted")))
                    check(f"artifact {e['export'][:40]} / {arm}: marked not_applicable_no_engine", r["corrected_provenance_leela"].get("duplication_patch_source") == pvl.NOT_APPLICABLE)
                elif arm.startswith("rocketride"):
                    check(f"artifact {e['export'][:40]} / {arm}: post-R2 check_after PASSES with nothing exempted", r["check_after"]["PASS"] is True and r["check_after"]["exempted"] == [], str(r["check_after"]))
    else:
        print(f"  NOTE  newest artifact {arts[-1].name} predates the post-R2 recomputation (its LI check_after is the pre-R2 reading) — the superseding artifact lives on docs-bench")
    check("artifact: the two smoke50_parser_in exports are the ones that changed",
          sorted(art["summary"]["changed"]) == sorted(n for n in art["summary"]["changed"] if n.startswith("smoke50_parser_in__20260818"))
          and len(art["summary"]["changed"]) == 2, str(art["summary"]["changed"]))
    for e in art["exports"]:
        if e["status"] == "unchanged":
            check(f"artifact {e['export'][:40]}: unchanged WITH a stated reason", bool(e.get("reason")))
    for e in art["exports"]:
        p = RESULTS / e["export"]
        if p.exists():
            import hashlib
            check(f"artifact {e['export'][:40]}: original sha256 matches the committed file",
                  hashlib.sha256(p.read_bytes()).hexdigest() == e["original_sha256"])


def layer4_arm_scoped_check() -> None:
    """Advisor R2 (2026-09-08): check() exempts the two patch fields for an arm with no
    RocketRide image and LISTS the exemption; a RocketRide arm missing them still FAILS."""
    print("layer 4: check() arm-scoped exemption, both directions")
    A, I = pvl.PATCH_LABEL, pvl.PATCH_ID_LABEL
    pid = "preventDefault-after-embedding-flush"

    def build_arm(arm, container, labels):
        orig = pvl._docker_label
        pvl._docker_label = lambda c, k: (labels.get(c) or {}).get(k)
        try:
            return pvl.build(arm=arm, mode="test", corpus_sha="x", corpus_n=1, offered_concurrency=1,
                             configured_concurrency=1, warmup_policy="none", timeout_s=1, parser="p",
                             chunk_size=4000, chunk_overlap=200, embedding_model="m", container=container)
        finally:
            pvl._docker_label = orig

    def complete(block):   # fill every non-patch REQUIRED field so only the patch fields decide
        b = dict(block)
        for k in pvl.REQUIRED:
            if k not in pvl.PATCH_FIELDS and (b.get(k) is None or b.get(k) == ""):
                b[k] = "filled"
        return b

    # direction 1: a RocketRide arm missing the fields still FAILS, nothing exempted
    rr = complete(build_arm("rocketride_pdf", "rr", {}))          # label unreadable -> None
    r = pvl.check(rr, arm="rocketride_pdf")
    check("RR arm, label unreadable -> None on both fields", rr["duplication_patch_applied"] is None and rr["duplication_patch_id"] is None)
    check("RR arm, None -> check FAILS", r["PASS"] is False, str(r))
    check("RR arm, None -> both patch fields listed missing", set(pvl.PATCH_FIELDS) <= set(r["missing_fields"]), str(r["missing_fields"]))
    check("RR arm, None -> nothing exempted", r["exempted"] == [], str(r["exempted"]))
    r2 = pvl.check(rr)                                             # arm inferred from the record
    check("RR arm without arm= -> still FAILS (no not_applicable marker on it)", r2["PASS"] is False and r2["exempted"] == [])
    rr_marked = dict(rr, duplication_patch_source=pvl.NOT_APPLICABLE)
    r3 = pvl.check(rr_marked, arm="rocketride_pdf")
    check("RR arm carrying the not_applicable marker, arm= given -> arm wins, still FAILS", r3["PASS"] is False and r3["exempted"] == [], str(r3))
    rr_ok = complete(build_arm("rocketride_pdf", "rr", {"rr": {A: "1", I: pid}}))
    check("RR arm, label '1' -> check PASSES with nothing exempted", pvl.check(rr_ok, arm="rocketride_pdf")["PASS"] is True and pvl.check(rr_ok, arm="rocketride_pdf")["exempted"] == [])
    rr_stock = complete(build_arm("rocketride_pdf", "rr", {"rr": {A: "0"}}))
    rs = pvl.check(rr_stock, arm="rocketride_pdf")
    check("RR arm, label '0' -> PASSES, only the id exempted, reason listed", rs["PASS"] is True and rs["exempted"] == ["duplication_patch_id"] and "stock" in rs["exemption_reasons"]["duplication_patch_id"], str(rs))

    # direction 2: a LlamaIndex arm with None PASSES, with the exemption listed
    li = build_arm("llamaindex_http_pdf", "li", {"li": {A: "1", I: pid}})   # even a stray label is not read
    check("LI arm -> applied None (never False, never read from a label)", li["duplication_patch_applied"] is None)
    check("LI arm -> id None", li["duplication_patch_id"] is None)
    check("LI arm -> source is not_applicable_no_engine", li["duplication_patch_source"] == pvl.NOT_APPLICABLE, repr(li.get("duplication_patch_source")))
    li = complete(li)
    l1 = pvl.check(li, arm="llamaindex_http_pdf")
    check("LI arm, arm= given -> check PASSES", l1["PASS"] is True, str(l1))
    check("LI arm -> both patch fields listed as exempted", l1["exempted"] == sorted(pvl.PATCH_FIELDS), str(l1["exempted"]))
    check("LI arm -> exemption reason names the scope", all(pvl.NOT_APPLICABLE in v for v in l1["exemption_reasons"].values()), str(l1["exemption_reasons"]))
    check("LI arm -> nothing else missing", l1["missing_fields"] == [], str(l1["missing_fields"]))
    l2 = pvl.check(li)                                             # arm inferred from the marker
    check("LI arm without arm= -> marker infers the scope, PASSES with exemption listed", l2["PASS"] is True and l2["exempted"] == sorted(pvl.PATCH_FIELDS), str(l2))
    li_unmarked = {k: v for k, v in li.items() if k != "duplication_patch_source"}
    l3 = pvl.check(li_unmarked)
    check("LI-shaped block WITHOUT the marker and without arm= -> FAILS (no scope claimed, none granted)", l3["PASS"] is False and l3["exempted"] == [], str(l3))
    # a LlamaIndex arm missing some OTHER required field must still fail: the exemption is narrow
    li_gap = dict(li); li_gap["corpus_manifest_sha256"] = None
    l4 = pvl.check(li_gap, arm="llamaindex_http_pdf")
    check("LI arm missing an unrelated field -> FAILS on that field only", l4["PASS"] is False and l4["missing_fields"] == ["corpus_manifest_sha256"], str(l4["missing_fields"]))
    check("is_rocketride_arm: video arm names", pvl.is_rocketride_arm("rocketride_video_parity") and not pvl.is_rocketride_arm("llamaindex_video_workers") and not pvl.is_rocketride_arm(None))


def main() -> int:
    layer1_contract()
    layer2_source()
    layer3_artifacts()
    layer4_arm_scoped_check()
    print(f"\n{_n - len(_fails)} passed, {len(_fails)} failed")
    for f in _fails:
        print("  FAIL", f)
    return 1 if _fails else 0


if __name__ == "__main__":
    sys.exit(main())
