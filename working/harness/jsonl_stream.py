"""Crash-durable per-document records, and resume from what survived.

WHY. The smoke buffered every record in a list and wrote the whole file once, after the loop
finished (`dump_jsonl` -> `write_text`). A run killed at document 7,000 of 10,000 left
**nothing**: the JSONL did not exist yet, the list died with the process, and the result JSON is
written later still. At ~25 hours for 10k that is an all-or-nothing bet on nothing going wrong
for a day — on a box whose auto-stop fires silently.

WHAT THIS GIVES. One line appended and flushed as each document completes, so a kill costs at
most the in-flight document. A later run with SMOKE_RESUME=1 reads what survived, skips those
documents and appends to the same file.

DURABILITY, precisely. `write` + `flush` puts the line in the OS page cache, which survives
process death (a kill, an exception, an OOM-killed driver). It does NOT survive host power loss
without `fsync`, which is deliberately not called per line: at 10k documents that is 10k syncs,
and the failure we are protecting against is the process dying, not the machine losing power.
`fsync_every` is available for callers who want the stronger guarantee.

A TORN LAST LINE IS EXPECTED, not an error. If the process died mid-write the final line can be
truncated JSON. `read_completed` skips an unparseable trailing line and reports it, rather than
refusing to resume or — worse — silently treating a partial record as a completed document.
An unparseable line that is NOT last is corruption, and that raises.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple


class JsonlWriter:
    """Append-and-flush one record at a time. Never buffers the run in memory."""

    def __init__(self, path: Path, fsync_every: int = 0):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.fsync_every = fsync_every
        self._n = 0
        self._fh = None

    def __enter__(self) -> "JsonlWriter":
        # Append, so a resumed run adds to what survived instead of truncating it. Opening
        # "w" here would destroy the very records resume depends on.
        self._fh = self.path.open("a", encoding="utf-8")
        return self

    def write(self, row: Dict[str, Any]) -> None:
        assert self._fh is not None, "JsonlWriter used outside its context manager"
        self._fh.write(json.dumps(row, separators=(",", ":")) + "\n")
        self._fh.flush()                      # out of process memory, into the page cache
        self._n += 1
        if self.fsync_every and self._n % self.fsync_every == 0:
            os.fsync(self._fh.fileno())       # onto the disk; only if the caller asked

    def __exit__(self, *exc) -> None:
        if self._fh is not None:
            self._fh.flush()
            os.fsync(self._fh.fileno())       # one sync at close is cheap and worth it
            self._fh.close()
            self._fh = None


def read_completed(path, key: str = "doc") -> Tuple[List[Dict], Set[str], Optional[str]]:
    """(records, completed keys, torn-line note) from a file that may have died mid-write."""
    p = Path(path)
    if not p.exists():
        return [], set(), None
    rows: List[Dict] = []
    torn: Optional[str] = None
    lines = p.read_text(encoding="utf-8", errors="replace").splitlines()
    for i, line in enumerate(lines):
        if not line.strip():
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            if i == len(lines) - 1:
                torn = (f"last line of {p.name} is truncated JSON ({len(line)} bytes) — the "
                        "process died mid-write. Skipped; that document will be re-run.")
            else:
                raise ValueError(
                    f"line {i + 1} of {p.name} is unparseable and is NOT the last line. "
                    "That is corruption, not a torn write. Refusing to resume from it.")
    return rows, {r[key] for r in rows if key in r}, torn


def rewrite_atomically(path, rows: List[Dict]) -> None:
    """Replace a file's contents via temp + rename, for post-loop passes that enrich records
    in place. Rename is atomic, so a crash leaves either the old file or the new one."""
    p = Path(path)
    tmp = p.with_suffix(p.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r, separators=(",", ":")) + "\n")
        fh.flush()
        os.fsync(fh.fileno())
    tmp.replace(p)
