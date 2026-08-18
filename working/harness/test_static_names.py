#!/usr/bin/env python3
"""The undefined-name checker: control both directions, then sweep the tree.

Defect #36 shipped because nothing between py_compile and a 40-minute run could see an
undefined name inside an untaken branch. A checker that cannot fail proves nothing, so the
planted-defect control runs FIRST: a file with a known undefined name must be flagged, at the
right name, before the clean sweep is allowed to mean anything.
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from harness.static_names import check_files, undefined_names  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent.parent
_fails: list[str] = []


def check(name, cond, got=""):
    print(f"  {'PASS' if cond else 'FAIL'}  {name:58} {got}")
    if not cond:
        _fails.append(name)


def main() -> int:
    with tempfile.TemporaryDirectory() as td:
        # The planted defect mirrors #36 exactly: a bare name inside a conditional branch.
        bad = Path(td) / "bad.py"
        bad.write_text("import os\n\ndef main():\n    if os.environ.get('X'):\n"
                       "        return MISSING_NAME\n    return 0\n")
        finds = undefined_names(bad)
        check("planted undefined name is caught", any(f["name"] == "MISSING_NAME"
                                                     for f in finds), str(finds))
        check("its use line is reported", any(5 in f["use_lines"] for f in finds))

        good = Path(td) / "good.py"
        good.write_text("import os\nX = 1\n\ndef f(a):\n    b = a + X\n"
                        "    return [i for i in range(b) if os.sep]\n\n"
                        "class C:\n    Y = 2\n    def m(self):\n        return self.Y + X\n")
        check("clean file yields no findings", undefined_names(good) == [])

        star = Path(td) / "star.py"
        star.write_text("from os.path import *\n\ndef f():\n    return join('a')\n")
        sfinds = undefined_names(star)
        check("star import is reported unverifiable, not skipped",
              len(sfinds) == 1 and "star import" in sfinds[0].get("note", ""))

    targets = sorted(set(
        list((ROOT / "working" / "scripts").glob("*.py")) +
        list((ROOT / "working" / "harness").glob("*.py")) +
        [ROOT / "weekend_worker.py", ROOT / "docker" / "bootcheck_rocketride.py",
         ROOT / "working" / "minimal" / "count_loc.py",
         ROOT / "working" / "minimal" / "verify_loc.py"]))
    bad_files = check_files(targets)
    for f, finds in bad_files.items():
        for x in finds:
            print(f"    !! {f}: {x['name']} in {x['scope']}:{x['scope_line']} "
                  f"uses {x['use_lines']}")
    check(f"tree sweep clean ({len(targets)} files)", not bad_files,
          f"{len(bad_files)} file(s) with undefined names")

    print("\n" + ("ALL PASS" if not _fails else f"{len(_fails)} FAILED: {_fails}"))
    return 1 if _fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
