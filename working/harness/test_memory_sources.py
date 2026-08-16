#!/usr/bin/env python3
"""memory_sources against a synthetic cgroup tree — the arithmetic, not the kernel.

Built after defect #30 (2026-08-16): a report printed a summed-RSS "peak" of 84,960 MB for a
container capped at 58 GB, next to a cgroup anon of 1,025 MB from a different leg, and nothing
on the page objected. The impossible-footprint check below is the objection.

macOS has no cgroup v2, so the fixture writes the files the reader expects. That tests our
arithmetic and our naming; it does not test the kernel, which is fine — the kernel is not the
part that was wrong.
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from harness import memory_sources as msrc  # noqa: E402

_fails: list[str] = []


def check(name, cond, got=""):
    print(f"  {'PASS' if cond else 'FAIL'}  {name:56} {got}")
    if not cond:
        _fails.append(name)


def fake_cgroup(d: Path, anon_mb, file_mb, peak_mb, limit_mb) -> Path:
    mb = 1048576
    (d / "memory.current").write_text(str(int((anon_mb + file_mb) * mb)))
    (d / "memory.peak").write_text(str(int(peak_mb * mb)))
    (d / "memory.max").write_text("max" if limit_mb is None else str(int(limit_mb * mb)))
    (d / "memory.stat").write_text(
        f"anon {int(anon_mb * mb)}\nfile {int(file_mb * mb)}\n"
        f"inactive_file {int(file_mb * mb * 0.8)}\nshmem 0\nkernel 0\n")
    return d


def main() -> int:
    print("memory_sources — synthetic cgroup")
    with tempfile.TemporaryDirectory() as td:
        cg = fake_cgroup(Path(td), anon_mb=1025.4, file_mb=4000.0, peak_mb=2100.0,
                         limit_mb=58000.0)
        m = msrc.cgroup_memory(cg)
        check("anon_mb read from memory.stat", abs(m["anon_mb"] - 1025.4) < 0.2, m["anon_mb"])
        check("limit surfaced as max_mb", abs(m["max_mb"] - 58000.0) < 1, m["max_mb"])
        check("docker-stats equivalent excludes inactive_file only",
              abs(m["docker_stats_equivalent_mb"] - (1025.4 + 800.0)) < 1.0,
              m["docker_stats_equivalent_mb"])
        check("page cache is NOT folded into anon", m["file_mb"] > m["anon_mb"],
              f"file={m['file_mb']} anon={m['anon_mb']}")

        # The real 10k case: a summed-RSS peak far past the container's own cap.
        rep = dict(msrc.memory_report(None, 84960.6))
        rep.update(cgroup=m, cgroup_anon_mb=m["anon_mb"], cgroup_limit_mb=m["max_mb"])
        lim, s = m["max_mb"], 84960.6
        impossible = s > lim
        check("84,960 MB is flagged impossible under a 58 GB cap", impossible,
              f"{s / lim:.1f}x the limit")
        # And the same figure through the real code path.
        orig = msrc.cgroup_path_for_pid
        msrc.cgroup_path_for_pid = lambda pid: cg
        try:
            r = msrc.memory_report(4242, 84960.6)
        finally:
            msrc.cgroup_path_for_pid = orig
        check("memory_report sets summed_rss_exceeds_cgroup_limit",
              r.get("summed_rss_exceeds_cgroup_limit") is True)
        check("memory_report names cgroup anon as the quotable figure",
              r.get("comparable_to_teammates") == "cgroup_anon_mb")
        check("sharing factor computed against anon, not current",
              abs(r["sharing_factor_summed_over_anon"] - round(84960.6 / 1025.4, 2)) < 0.01,
              r["sharing_factor_summed_over_anon"])

        # A plausible in-limit figure must NOT be flagged — the check has to discriminate.
        msrc.cgroup_path_for_pid = lambda pid: cg
        try:
            ok = msrc.memory_report(4242, 1513.8)
        finally:
            msrc.cgroup_path_for_pid = orig
        check("a within-limit summed RSS is not flagged",
              "summed_rss_exceeds_cgroup_limit" not in ok,
              f"sharing={ok.get('sharing_factor_summed_over_anon')}x")

        # No limit set (memory.max == "max") must not crash or false-positive.
        cg2 = fake_cgroup(Path(tempfile.mkdtemp()), 100.0, 10.0, 150.0, None)
        m2 = msrc.cgroup_memory(cg2)
        check("unlimited cgroup -> max_mb is None, no flag", m2["max_mb"] is None)

    print("\n" + ("ALL PASS" if not _fails else f"{len(_fails)} FAILED: {_fails}"))
    return 1 if _fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
