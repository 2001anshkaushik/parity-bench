#!/usr/bin/env python3
"""provenance_correction_20260818 — re-emit the `provenance_leela` blocks of every 18-Aug
export with `duplication_patch_applied` / `duplication_patch_id` derived from the image
label evidence instead of the literal False that `provenance_leela.build()` hardcoded from
17 Aug to 7 Sep 2026 (DOCS_HANDOFF.md §2.4, §10.1). The ORIGINAL export files are never
opened for writing; the correction is a separate result under its own name.

How the corrected value is derived — never asserted:
  1. Every 18-Aug export written through `experiment_common.provenance()` carries
     `provenance/image_digests/rocketride = <digest>|<tag>|<created>` beside
     `provenance/engine/label_raw`, which `_engine_patch_state()` READ from the image label
     `benchmark.rocketride.duplication_patch_applied` at run time. That is a measured
     digest -> label table, and it is built here from the artifacts, not typed in.
  2. A `provenance_leela` arm block whose `image_digest` is in that table gets the label's
     value under the same rule `provenance_leela._patch_state` applies live ("1" -> True with
     the id, "0" -> False). A digest with NO label reading in any 18-Aug artifact (the
     LlamaIndex image, which carries no RocketRide patch label) is recorded as None on both
     fields — UNKNOWN, never False.
  3. `duplication_patch_source` states which artifacts evidenced the value.

Run (from the repo root; writes working/results/provenance_correction_20260818__<utc>__<sha>.json):
  python3 working/scripts/provenance_correction_20260818.py [--results DIR] [--dry-run]
`--dry-run` prints the payload sha256_12 and writes nothing, so the artifact can be re-derived
and compared against the committed one.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "working"))
from harness import provenance_leela as pvl  # noqa: E402

DAY = "20260818"
FIELDS = ("duplication_patch_applied", "duplication_patch_id")


def _load(p: Path) -> Dict[str, Any]:
    return json.loads(p.read_text())


def _sha256(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def digest_label_evidence(exports: List[Tuple[Path, Dict[str, Any]]]) -> Dict[str, Dict[str, Any]]:
    """digest -> {label_raw, duplication_patch_id, tag, evidenced_by[]} from every export that
    carries BOTH an engine label reading and the RocketRide image digest it was read from."""
    ev: Dict[str, Dict[str, Any]] = {}
    for p, d in exports:
        prov = (d.get("data") or {}).get("provenance") or {}
        eng = prov.get("engine") or {}
        digs = prov.get("image_digests") or {}
        raw = eng.get("label_raw")
        rr = digs.get("rocketride")
        if raw is None or not rr:
            continue
        digest, tag = rr.split("|")[0], (rr.split("|") + [None])[1]
        e = ev.setdefault(digest, {"label_raw": raw, "tag": tag,
                                   "duplication_patch_id": eng.get("duplication_patch_id"),
                                   "evidenced_by": []})
        if e["label_raw"] != raw:
            raise SystemExit(f"CONTRADICTION: digest {digest} read label {e['label_raw']!r} "
                             f"in {e['evidenced_by']} but {raw!r} in {p.name} — refusing")
        e["evidenced_by"].append(p.name)
    return ev


def corrected_block(block: Dict[str, Any], evidence: Dict[str, Dict[str, Any]],
                    arm: Optional[str] = None) -> Dict[str, Any]:
    """A copy of one `provenance_leela` arm block with the two patch fields re-derived from
    the digest -> label table and a `duplication_patch_source` saying how. Same value rule as
    `provenance_leela._patch_state`; an unevidenced digest is None on both fields.

    Post-R2 (2026-09-08, 4029eab): an arm with no RocketRide image is marked
    `not_applicable_no_engine` — the same marker build() now writes — so `check()` scopes
    the two patch fields out for it and lists the exemption; the reason the label could not
    be read is kept beside it in `duplication_patch_note`."""
    out = dict(block)
    digest = block.get("image_digest")
    e = evidence.get(digest) if digest else None
    if e is None:
        out["duplication_patch_applied"] = None
        out["duplication_patch_id"] = None
        why = (f"no label reading of image {digest or '(no digest)'} exists in any {DAY} artifact "
               "(the LlamaIndex image carries no RocketRide patch label) — UNKNOWN, not asserted")
        if arm is not None and not pvl.is_rocketride_arm(arm):
            out["duplication_patch_source"] = pvl.NOT_APPLICABLE
            out["duplication_patch_note"] = why
        else:
            out["duplication_patch_source"] = why
        return out
    raw = e["label_raw"]
    if raw == "1":
        out["duplication_patch_applied"] = True
        out["duplication_patch_id"] = e["duplication_patch_id"]
    elif raw == "0":
        out["duplication_patch_applied"] = False
        out["duplication_patch_id"] = None
    else:
        out["duplication_patch_applied"] = None
        out["duplication_patch_id"] = None
    out["duplication_patch_source"] = (
        f"re-derived 2026-09-07: image_digest {digest} ({e['tag']}) carries label "
        f"{pvl.PATCH_LABEL}={raw!r}, read by docker inspect at run time and recorded in "
        f"{sorted(e['evidenced_by'])}")
    return out


def _arm_blocks(pl: Any) -> Optional[Dict[str, Dict[str, Any]]]:
    if not isinstance(pl, dict):
        return None
    if "image_digest" in pl:                      # a single un-keyed block
        return {"(single)": pl}
    return {k: v for k, v in pl.items() if isinstance(v, dict)}


def build_correction(results: Path) -> Dict[str, Any]:
    paths = sorted(p for p in results.glob(f"*__{DAY}T*.json") if p.is_file())
    if not paths:
        raise SystemExit(f"no *__{DAY}T*.json exports under {results}")
    exports = [(p, _load(p)) for p in paths]
    evidence = digest_label_evidence(exports)
    entries: List[Dict[str, Any]] = []
    changed, unchanged = [], []
    for p, d in exports:
        rel = str(p.resolve().relative_to(ROOT)) if ROOT in p.resolve().parents else f"working/results/{p.name}"
        entry: Dict[str, Any] = {"export": p.name, "path_in_repo": f"working/results/{p.name}",
                                 "original_sha256": _sha256(p)}
        data = d.get("data") or {}
        arms = _arm_blocks(data.get("provenance_leela"))
        if arms is None:
            eng = ((data.get("provenance") or {}).get("engine")) or None
            entry["status"] = "unchanged"
            entry["reason"] = ("carries no provenance_leela block (written through "
                               "experiment_common.provenance(), whose engine block READS the "
                               "image label; nothing false to correct)" if eng else
                               "carries neither a provenance_leela block nor an engine "
                               "provenance block")
            if eng:
                entry["engine_block_as_recorded"] = {k: eng.get(k) for k in
                                                     ("duplication_patch_applied",
                                                      "duplication_patch_id", "label_raw")}
            unchanged.append(p.name)
            entries.append(entry)
            continue
        per_arm = {}
        any_change = False
        for arm, block in arms.items():
            arm_name = None if arm == "(single)" else arm
            new = corrected_block(block, evidence, arm=arm_name)
            before = {k: block.get(k) for k in FIELDS}
            after = {k: new.get(k) for k in FIELDS}
            arm_changed = before != after
            any_change |= arm_changed
            per_arm[arm] = {"image_digest": block.get("image_digest"),
                            "before": before, "after": after, "changed": arm_changed,
                            "check_before": pvl.check(block),
                            "check_after": pvl.check(new, arm=arm_name),
                            "corrected_provenance_leela": new}
        entry["status"] = "corrected" if any_change else "unchanged"
        entry["arms"] = per_arm
        (changed if any_change else unchanged).append(p.name)
        entries.append(entry)
    from harness.resultio import latest
    prev = latest(f"provenance_correction_{DAY}")
    supersedes = None
    if prev is not None:
        supersedes = {
            "artifact": prev.name,
            "why": ("its check_after for the LlamaIndex arm was computed with the pre-R2 check() "
                    "(no arm scoping) and reads PASS=False, which contradicts provenance_leela.check() "
                    "from 4029eab onward (Advisor R2: the two patch fields are exempted by scope for an "
                    "arm with no RocketRide image, and the exemption is listed). Recomputed here with "
                    "check(block, arm=<arm>); the earlier file is untouched — artifacts are append-only."),
        }
    return {
        "correction_of": ("duplication_patch_applied / duplication_patch_id inside every "
                          f"provenance_leela arm block of the {DAY} exports"),
        "check_semantics": {
            "check_before": "provenance_leela.check(block) — Leela's port, no arm scoping (as it read at the time)",
            "check_after": ("provenance_leela.check(block, arm=<arm>) — post-R2 (4029eab): patch fields exempted "
                            "by scope for a non-RocketRide arm, exemption listed under `exempted` / `exemption_reasons`"),
        },
        "supersedes": supersedes,
        "defect": ("working/harness/provenance_leela.py build() hardcoded "
                   "\"duplication_patch_applied\": False from 17 Aug to 7 Sep 2026 "
                   "(main:140, video-bench:140, unconditional); the 18-Aug measured docs runs "
                   "were on rr:patched. Fixed 2026-09-07 to read the image label; None when "
                   "unreadable, never False. DOCS_HANDOFF.md §2.4 / §10.1."),
        "originals_untouched": True,
        "derivation_rule": corrected_block.__doc__.strip(),
        "digest_label_evidence": evidence,
        "exports": entries,
        "summary": {"n_exports": len(entries), "changed": changed, "unchanged": unchanged},
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--results", default=str(ROOT / "working" / "results"),
                    help="directory holding the 18-Aug exports (default working/results)")
    ap.add_argument("--dry-run", action="store_true", help="print the payload hash, write nothing")
    a = ap.parse_args(argv)
    data = build_correction(Path(a.results))
    from harness.resultio import _payload_hash, write_result
    print(f"exports scanned: {data['summary']['n_exports']}")
    print(f"  changed  : {data['summary']['changed']}")
    print(f"  unchanged: {data['summary']['unchanged']}")
    for e in data["exports"]:
        for arm, r in (e.get("arms") or {}).items():
            print(f"  {e['export']} / {arm}: {r['before']} -> {r['after']}  "
                  f"check {r['check_before']['PASS']} -> {r['check_after']['PASS']}")
    print(f"payload_sha256_12: {_payload_hash(data)}")
    if a.dry_run:
        return 0
    out = write_result(f"provenance_correction_{DAY}", data)
    print(f"wrote {out.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
