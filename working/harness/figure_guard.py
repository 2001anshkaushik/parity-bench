#!/usr/bin/env python3
"""figure_guard.py — refuse a landing that carries a never-quote figure uncaveated.

WHY THIS EXISTS
---------------
The manual "Ansh reads the diff before it goes public" gate is retired. This is what
replaces it. The repo is public and two teammates clone it, so the risk was never a
merge conflict — it was a withdrawn number becoming quotable by someone acting in good
faith. That risk is a text search, and a text search is a better checker than a human at
2am.

WHAT IT CHECKS
--------------
Every never-quote figure from DOCS_HANDOFF.md §3.6 has a pattern here. A pattern firing
is NOT a failure. A pattern firing *without a caveat marker within the window* is.

So the handoff itself passes (it caveats all of them, which is why they are in it), while
a fresh report that writes "RocketRide is 6.9x lighter" fails closed.

WHAT IT DELIBERATELY DOES NOT DO
--------------------------------
It does not judge whether a caveat is *good*. A marker within the window is accepted at
face value. This gate catches the bare quote — the overwhelmingly likely failure — and
does not pretend to catch a misleading one. Say so rather than implying more coverage
than it has.

NULL CONTROL
------------
`--null-control` writes a file containing every banned figure with no caveat and asserts
this script REFUSES it. A gate that has never refused anything is not known to work. It
exits 3 if the null control passes (i.e. if the gate failed to fire), which is the
inverse-failure case that would otherwise leave a broken checker green forever.

Exit codes:  0 clean · 1 violation found · 2 usage/IO error · 3 null control did not fire
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import List, Tuple

# Lines of context, either side, in which a caveat marker counts as covering the figure.
WINDOW = 6

# A figure is considered caveated if any of these appear within WINDOW lines.
CAVEAT_MARKERS = re.compile(
    r"never quote|do not quote|don't quote|must not be quoted|withdrawn|WITHDRAWN|"
    r"VOID|void as|superseded|SUPERSEDED|not a product finding|self-inflicted|"
    r"artifact, not|summing artifact|PRIOR-RECORD|HYPOTHESIS|invalid|INVALID|"
    r"corrupted|harness defect|not publishable|caveat",
    re.I,
)

# (id, pattern, what it is, why it is banned)
BANNED: List[Tuple[str, re.Pattern, str, str]] = [
    ("summed-rss-85g",
     re.compile(r"\b84[,_]?960(\.6)?(?!\d)"),
     "RocketRide peakRSS 84,960.6 MB",
     "summing artifact against a 58 GB cap; the number surviving IS the proof it is not a footprint"),
    ("peak-rss-any",
     re.compile(r"\bpeakRSS\b|\bpeak_summed_process_rss"),
     "a summed per-process RSS figure",
     "over-counts shared pages once per process; the bias SCALES with process count, so even the ratio is unsalvageable"),
    ("mem-6-9x",
     re.compile(r"\b6\.9\s*[x\u00d7]", re.I),
     "'RocketRide ~6.9x lighter'",
     "both sides were post-leg point samples; RocketRide's post-leg read 135.3 MB against a true sampled peak of 16,397.0 MB. Quote 1.42x from the 10k blast"),
    ("shashi-52-8",
     re.compile(r"\b52\.8\b.{0,80}\b52\.9\b|\b52\.9\b.{0,80}\b52\.8\b", re.S),
     "the 52.8% / 52.9% cross-harness match",
     "measured with the engine UNPINNED at torch=16. Honest version: 49.7% pinned vs his 52.9%, different corpora"),
    ("pipe-371",
     re.compile(r"\b371\b"),
     "the 371 PipeException failures",
     "self-inflicted: 1800s client deadline against a 900s engine idle ttl. A harness footnote, never a reliability result"),
    ("batchpos-latency",
     re.compile(r"blast_batchpos"),
     "a blast_batchpos latency figure",
     "corrupted at EVERY warm_n in run10k_p2_blast_v2 — stale enqueue stamp, measured gap 2,388.6s. Use the warm_n=64 closed-loop figures"),
    ("dup-patch-false",
     re.compile(r"duplication_patch_applied[^\n]{0,40}\b[Ff]alse\b|\b[Ff]alse\b[^\n]{0,40}duplication_patch_applied"),
     "the assertion that duplication_patch_applied is False",
     "the field is trustworthy from provenance_leela.py's label-reading fix forward (d98aa7c, 2026-09-07) and legitimately "
     "quotable; but it reads False in the two 18-Aug smoke50_parser_in__20260818T* exports while those runs were on "
     "rr:patched (sha256:073b43d8). A bare 'False' from those exports is the false record — cite the correction "
     "artifact (provenance_correction_20260818) or the image_digest instead"),
    ("stalled-doc-314",
     re.compile(r"\b314\.5(?!\d)"),
     "the 314.5s stalled document",
     "macOS artifact; did not reproduce on Linux"),
    ("macos-quotable",
     re.compile(r"docs_per_s_DO_NOT_QUOTE"),
     "a macOS-era throughput key",
     "all macOS-measured results are superseded"),
]

SCANNED_SUFFIXES = {".md", ".txt", ".rst"}


def changed_files(base: str) -> List[Path]:
    """Prose that a push from here would make public: everything the INDEX differs in from
    `base` — i.e. every commit since `base` plus whatever is staged. Deletions excluded.

    `base` must resolve. The previous version swallowed a bad base and silently scanned
    only the staged files — a gate that narrows its own scope on error is a gate that can
    only pass (register entry 8). autoland.sh chooses the base (origin/<branch>, else the
    merge-base with origin/video-bench, else origin/main, else HEAD) and prints it."""
    chk = subprocess.run(["git", "rev-parse", "--verify", "--quiet", f"{base}^{{commit}}"],
                         capture_output=True, text=True)
    if chk.returncode != 0:
        print(f"figure_guard: base {base!r} does not resolve to a commit — refusing rather than "
              f"scanning a narrower set than asked", file=sys.stderr)
        raise SystemExit(2)
    r = subprocess.run(["git", "diff", "--name-only", "--diff-filter=d", "--cached", base],
                       capture_output=True, text=True, check=True)
    out = {x for x in r.stdout.split("\n") if x.strip()}
    return [Path(p) for p in sorted(out) if Path(p).suffix.lower() in SCANNED_SUFFIXES]


def scan(path: Path) -> List[str]:
    """Return one message per uncaveated banned figure in `path`."""
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").split("\n")
    except OSError as e:
        return [f"{path}: unreadable ({e})"]

    problems: List[str] = []
    for i, line in enumerate(lines):
        for fid, pat, what, why in BANNED:
            if not pat.search(line):
                continue
            lo, hi = max(0, i - WINDOW), min(len(lines), i + WINDOW + 1)
            if CAVEAT_MARKERS.search("\n".join(lines[lo:hi])):
                continue
            problems.append(
                f"{path}:{i + 1}  [{fid}] {what}\n"
                f"      line: {line.strip()[:110]}\n"
                f"      why : {why}\n"
                f"      fix : caveat it within {WINDOW} lines, or remove it."
            )
    return problems


def null_control() -> int:
    """The gate must REFUSE a file built to be refused. Otherwise it is not known to work."""
    body = ["# null control — every banned figure, deliberately uncaveated", ""]
    for fid, _pat, what, _why in BANNED:
        body.append(f"RocketRide peakRSS was 84,960.6 MB and 6.9x lighter; 52.8 matched 52.9; "
                    f"371 failures; blast_batchpos p50; duplication_patch_applied: False; 314.5s; "
                    f"docs_per_s_DO_NOT_QUOTE.  <- {fid} / {what}")
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "null_control.md"
        p.write_text("\n".join(body), encoding="utf-8")
        found = scan(p)
        fired = {m.split("[")[1].split("]")[0] for m in found if "[" in m}
        missing = [fid for fid, *_ in BANNED if fid not in fired]
        if missing:
            print("NULL CONTROL FAILED — these patterns did not fire on a file built to "
                  "trip them:", file=sys.stderr)
            for m in missing:
                print(f"  - {m}", file=sys.stderr)
            print("\nThe gate is broken. A clean run from here proves nothing.", file=sys.stderr)
            return 3
    print(f"NULL CONTROL PASSED — all {len(BANNED)} patterns fired on the seeded file.")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--base", default="origin/HEAD",
                    help="revision to diff against (default: origin/HEAD)")
    ap.add_argument("--all", action="store_true",
                    help="scan every tracked prose file, not just changed ones")
    ap.add_argument("--paths", nargs="*", default=None,
                    help="explicit paths to scan instead of deriving from git")
    ap.add_argument("--null-control", action="store_true",
                    help="prove the gate can refuse, then exit")
    a = ap.parse_args()

    if a.null_control:
        return null_control()

    if a.paths is not None:
        targets = [Path(p) for p in a.paths if Path(p).suffix.lower() in SCANNED_SUFFIXES]
    elif a.all:
        try:
            r = subprocess.run(["git", "ls-files"], capture_output=True, text=True, check=True)
        except (subprocess.CalledProcessError, FileNotFoundError) as e:
            print(f"figure_guard: cannot list tracked files ({e})", file=sys.stderr)
            return 2
        targets = [Path(p) for p in r.stdout.split("\n")
                   if p.strip() and Path(p).suffix.lower() in SCANNED_SUFFIXES]
    else:
        targets = changed_files(a.base)

    targets = [t for t in targets if t.is_file()]
    if not targets:
        print("figure_guard: no prose files in scope — nothing to check.")
        return 0

    problems: List[str] = []
    for t in targets:
        problems.extend(scan(t))

    if problems:
        print(f"\nFIGURE GUARD: REFUSED — {len(problems)} uncaveated never-quote "
              f"figure(s) across {len(targets)} file(s)\n", file=sys.stderr)
        for p in problems:
            print(p + "\n", file=sys.stderr)
        print("These figures are withdrawn, superseded or artifacts. Landing them "
              "uncaveated into a PUBLIC repo makes them quotable.", file=sys.stderr)
        return 1

    print(f"FIGURE GUARD: clean — {len(targets)} file(s) scanned, "
          f"{len(BANNED)} patterns, 0 uncaveated.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
