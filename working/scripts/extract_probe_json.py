#!/usr/bin/env python3
"""Pull a probe's verdict JSON out of its raw stdout.

    extract_probe_json.py <stdout_file> <out_json>

The S5-B pre-check runs its probe under the engine's own interpreter, whose imports may log to
stdout. Written straight to a .json file, one such line would make the verdict unreadable, and the
S5-B chain would refuse on "no verdict" for a reason that has nothing to do with the verdict. So
stdout is kept whole, and this finds the LAST JSON object that starts a line and carries a
"verdict" key, wherever the noise sits before or after it.

Exit 0: written (append-only; an existing <out_json> refuses, exit 3).
Exit 4: no such object — nothing is written, so a caller that needs the verdict refuses.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict, Optional


def extract(text: str) -> Optional[Dict[str, Any]]:
    dec = json.JSONDecoder()
    starts = ([0] if text.startswith("{") else []) + \
             [i + 1 for i, ch in enumerate(text) if ch == "\n" and text[i + 1:i + 2] == "{"]
    found = None
    for s in starts:
        try:
            obj, _ = dec.raw_decode(text, s)
        except ValueError:
            continue
        if isinstance(obj, dict) and "verdict" in obj:
            found = obj
    return found


def main() -> int:
    if len(sys.argv) != 3:
        print(__doc__)
        return 2
    src, dst = Path(sys.argv[1]), Path(sys.argv[2])
    if dst.exists():
        print(f"REFUSED: {dst} exists — append-only")
        return 3
    text = src.read_text(errors="replace")
    obj = extract(text)
    if obj is None:
        print(f"!! no JSON object with a verdict in {src} — {dst} NOT written")
        return 4
    noise = sum(1 for line in text.splitlines() if line.strip()) - len(json.dumps(obj, indent=1).splitlines())
    dst.write_text(json.dumps(obj, indent=1) + "\n")
    print(f"verdict extracted: {obj['verdict']}" + (f"  (about {noise} other stdout line(s) kept in {src.name})"
                                                    if noise > 0 else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
