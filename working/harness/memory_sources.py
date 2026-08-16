"""Memory, from every source that has a claim to the word — named, never merged.

WHY THIS EXISTS. Our harness reported LlamaIndex peak memory as **34,411.8 MB** while
`docker stats` on the same container in the same run showed **20.06 GiB**, and the a-priori
estimate was ~580 MB x 32 workers = 18.6 GB. The harness number is the outlier and it is the
one that is wrong.

WHAT OUR NUMBER ACTUALLY IS. `collector.py:360` does `rss += snap.rss` over every process in
the tree and `:378` takes `peak_rss = max(peak_rss, rss)`. So it is **the peak of a SUM of
per-process RSS**. `psutil.memory_info().rss` counts a resident page in FULL for every process
that maps it. Thirty-three uvicorn workers fork after loading torch and the embedding model, so
those pages are shared copy-on-write and are counted **33 times**. Summed RSS is not a memory
footprint; it is a footprint multiplied by an unknown sharing factor.

THE THREE PER-PROCESS METRICS, and why only one of them sums:

    RSS  resident, shared pages counted in full by every mapper  -> sums to an OVER-count
    USS  unique-set-size, private pages only                     -> sums to an UNDER-count
                                                                    (shared pages vanish)
    PSS  proportional: private + shared/n_mappers                -> **sums correctly**

Our collector can collect USS (`collector.py:179`) but `want_uss` defaults to False
(`:218`) and `collector_proc.py` never sets it, so in every run to date we collected
**neither USS nor PSS** — there was no deduplicated number to sanity-check the sum against.

WHAT THE TEAMMATES REPORT — this is the comparability answer:

    Leela   `aws_run/box/cgroup_sampler.py:55-62` reads cgroup `memory.stat` **anon**, with the
            explicit note that `memory.current` includes page cache "which PDF parsing fills".
    Shashi  `docker/bench/cstats.py:132-140` reads the Docker API `memory_stats.stats.rss`,
            falling back to `usage - stats.file` — i.e. usage minus page cache.

Both are **cgroup-level and deduplicated**: the kernel charges a shared page to the cgroup once,
however many processes map it. Neither is a sum of per-process RSS. **Our summed RSS is not
comparable to either of their figures**, and cgroup `anon` is what must be quoted alongside them.

THE BIAS IS NOT A CONSTANT, WHICH IS THE DANGEROUS PART. Over-count scales with the number of
processes sharing pages. The LlamaIndex arm forks 32 workers off one loaded model, so its summed
RSS is inflated by a large factor. The RocketRide arm runs an engine parent plus one task child —
almost nothing shared — so its summed RSS is close to correct. **A LlamaIndex-over-RocketRide
memory RATIO computed from summed RSS is therefore wrong in a direction that scales with worker
count**, not merely offset. That is how a 34.4 GB figure and a 20.06 GiB `docker stats` reading
coexist for one container.

The other direction: `docker stats` MemUsage is `memory.current - inactive_file`, so it INCLUDES
active page cache. A run that read 7.78 GB of PDF blocks fills that cache, which is why the
RocketRide arm can show 6.5-7.5 GiB in `docker stats` against ~2.8 GB of actual anonymous memory.
Page cache is reclaimable and is not the process's footprint. `anon` excludes it.

SOURCE HIERARCHY, best first:

    cgroup memory.peak   kernel high-water mark, UNSAMPLED - cannot miss a spike
    cgroup memory.stat anon   sampled, deduplicated, EXCLUDES page cache - what the teammates
                              report, and the number to quote against theirs
    summed PSS           deduplicated but sampled AND decimated (USS_DECIMATION = 20 ticks, so
                         every ~10 s at a 0.5 s interval) - a coarse peak, useful as a
                         cross-check on the cgroup figure, not as the headline
    summed RSS           over-counts shared pages - never quote as a peak

Note the decimation: on a run shorter than 20 ticks, PSS and USS are never sampled at all and
come back None. That is a real hole on short smokes and is why the cgroup reading, not PSS, is
the primary source.

This module reads the cgroup directly, from the host, for a container's own group.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional

CG_ROOT = Path("/sys/fs/cgroup")


def cgroup_path_for_pid(pid: int) -> Optional[Path]:
    """Resolve a (host) pid to its cgroup directory, without guessing the layout.

    `/proc/<pid>/cgroup` on cgroup v2 is a single line `0::/system.slice/docker-<id>.scope`.
    Reading it beats pattern-matching on Docker's directory naming, which differs between the
    systemd and cgroupfs drivers.
    """
    try:
        for line in Path(f"/proc/{pid}/cgroup").read_text().splitlines():
            parts = line.split(":", 2)
            if len(parts) == 3 and parts[0] == "0":          # cgroup v2 unified
                rel = parts[2].lstrip("/")
                p = CG_ROOT / rel
                return p if p.is_dir() else None
    except OSError:
        return None
    return None


def _read_int(p: Path) -> Optional[int]:
    try:
        return int(p.read_text().strip())
    except (OSError, ValueError):
        return None


def cgroup_memory(cg: Path) -> Dict[str, Any]:
    """Every memory figure the cgroup exposes, each named for what it is.

    `memory.peak` is a kernel-maintained HIGH-WATER MARK (cgroup v2, Linux 5.19+). It is not
    sampled, so unlike our 0.5 s sampler it cannot miss a spike between ticks — the weakness
    Shashi flagged in his review of our M5.
    """
    out: Dict[str, Any] = {"cgroup": str(cg)}
    out["current_bytes"] = _read_int(cg / "memory.current")   # anon + page cache + kernel
    out["peak_bytes"] = _read_int(cg / "memory.peak")         # true HWM, unsampled
    out["max_bytes"] = _read_int(cg / "memory.max")           # the limit, not a usage
    stat: Dict[str, int] = {}
    try:
        for line in (cg / "memory.stat").read_text().splitlines():
            k, _, v = line.partition(" ")
            if v.strip().isdigit():
                stat[k] = int(v)
    except OSError:
        pass
    # anon is what BOTH teammates report. file is page cache — the thing that makes
    # `docker stats` look large after a run that read gigabytes of PDFs.
    out["anon_bytes"] = stat.get("anon")
    out["file_bytes"] = stat.get("file")
    out["shmem_bytes"] = stat.get("shmem")
    out["kernel_bytes"] = stat.get("kernel")
    for k in ("current", "peak", "anon", "file", "max"):
        b = out.get(f"{k}_bytes")
        out[f"{k}_mb"] = round(b / 1048576, 1) if b is not None else None
    # docker stats' MemUsage column is current minus inactive_file, not `anon`; recorded so a
    # reader comparing against a screenshot knows which line they are looking at.
    inactive = stat.get("inactive_file")
    out["docker_stats_equivalent_mb"] = (
        round((out["current_bytes"] - inactive) / 1048576, 1)
        if out.get("current_bytes") is not None and inactive is not None else None)
    return out


def memory_report(pid: Optional[int], summed_rss_mb: Optional[float]) -> Dict[str, Any]:
    """All sources side by side, with the comparability call made explicit.

    Never merges them and never picks one silently: a summed-RSS peak and a cgroup anon peak
    answer different questions, and the difference between them IS the sharing factor.
    """
    rep: Dict[str, Any] = {
        "summed_process_rss_peak_mb": summed_rss_mb,
        "summed_process_rss_note": (
            "peak of a SUM of per-process RSS (collector.py:360,378). Shared copy-on-write "
            "pages are counted once per mapping process, so with N forked workers this "
            "OVER-counts by roughly the sharing factor. NOT comparable to Leela's or "
            "Shashi's figures."),
        "comparable_to_teammates": "cgroup_anon_mb",
        "comparable_note": (
            "Leela reads cgroup memory.stat anon (cgroup_sampler.py:55-62); Shashi reads the "
            "Docker API memory_stats.stats.rss, else usage-file (cstats.py:132-140). Both are "
            "cgroup-level: the kernel charges a shared page once per cgroup, not once per "
            "process. Quote anon against theirs."),
    }
    if pid is None:
        rep["cgroup"] = None
        rep["cgroup_unavailable_reason"] = "no host pid resolved for the service"
        return rep
    cg = cgroup_path_for_pid(pid)
    if cg is None:
        rep["cgroup"] = None
        rep["cgroup_unavailable_reason"] = (
            f"no cgroup v2 directory for pid {pid} (cgroup v1 host, or the pid is gone)")
        return rep
    m = cgroup_memory(cg)
    rep["cgroup"] = m
    rep["cgroup_anon_mb"] = m.get("anon_mb")
    rep["cgroup_peak_mb"] = m.get("peak_mb")
    rep["cgroup_limit_mb"] = m.get("max_mb")
    if summed_rss_mb and m.get("anon_mb"):
        rep["sharing_factor_summed_over_anon"] = round(summed_rss_mb / m["anon_mb"], 2)
    # THE CHEAPEST INSTRUMENT CHECK WE HAVE, and it was missing when a summed-RSS "peak" of
    # 84,960 MB shipped from a container capped at 58 GB (defect #30). A real footprint cannot
    # exceed its own cgroup limit — the kernel would have OOM-killed it. A number that does
    # exceed it has proved, by surviving, that it is not a footprint. The reason the sum can
    # run so far past the cap is that the cgroup charges a shared page ONCE however many
    # processes map it, while summed RSS charges it once PER process.
    lim = m.get("max_mb")
    if summed_rss_mb and lim and summed_rss_mb > lim:
        rep["summed_rss_exceeds_cgroup_limit"] = True
        rep["summed_rss_impossible_as_footprint"] = (
            f"summed RSS {summed_rss_mb:.1f} MB exceeds this cgroup's own limit "
            f"{lim:.1f} MB by {summed_rss_mb / lim:.1f}x. The container was not OOM-killed, "
            f"so the figure is an over-count of shared pages, not a footprint. Quote "
            f"cgroup anon ({m.get('anon_mb')} MB).")
    return rep
