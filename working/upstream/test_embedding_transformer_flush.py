#!/usr/bin/env python3
"""Regression test for BUG_CHUNK_DUPLICATION (embedding_transformer flush path).

THE CONTRACT UNDER TEST. `rocketlib.preventDefault()` RAISES (APERR, Ec.PreventDefault —
filters.py:180-190); it is the only way a node stops the engine's default action, which
forwards the incoming event downstream. `IInstance.writeDocuments()` prevents the default on
the buffering path (documents < maxDocuments, IInstance.py:80) but FALLS THROUGH after
`_flushDocuments()` (IInstance.py:83) — so once a document reaches maxDocuments (64) chunks,
the flush writes the batch downstream AND the default action forwards it again. Measured on
real corpora: every affected document returns its chunk list exactly twice ([A,B,C,A,B,C],
repeat_factor 2); documents that never reach 64 chunks drain through `close()` where no event
is in flight, which is why they never duplicate.

WHAT A UNIT TEST CAN AND CANNOT SEE. The duplicate emission itself is performed by the ENGINE
(the default action), which no unit test reaches. What the unit level CAN pin is the contract
whose violation causes it: **writeDocuments must prevent the default on EVERY path**. On stock,
the 64th chunk's write returns without raising — this test fails there and passes patched.
The end-to-end confirmation (chunk lists asserted repeat_factor 1 on five real documents that
duplicated on stock) lives in the benchmark harness's smoke, section A.

Runs standalone anywhere: rocketlib and ai.common.schema are stubbed if absent, so the test is
usable both in the engine repo's CI (real imports) and outside it.

    IINSTANCE=/path/to/IInstance.py python3 test_embedding_transformer_flush.py
"""
from __future__ import annotations

import importlib.util
import os
import sys
import types
from pathlib import Path
from unittest.mock import MagicMock


class PreventDefault(Exception):
    """Stands in for APERR(Ec.PreventDefault) when rocketlib is not importable."""


def _ensure_stubs():
    if "rocketlib" not in sys.modules:
        rl = types.ModuleType("rocketlib")

        class IInstanceBase:
            def preventDefault(self):
                # Same semantics as rocketlib/filters.py:180-190: RAISE, never return.
                raise PreventDefault()

        rl.IInstanceBase = IInstanceBase
        rl.Entry = object
        sys.modules["rocketlib"] = rl
    if "ai.common.schema" not in sys.modules:
        ai = types.ModuleType("ai")
        common = types.ModuleType("ai.common")
        schema = types.ModuleType("ai.common.schema")
        schema.Doc = object
        schema.Question = object
        ai.common = common
        common.schema = schema
        sys.modules["ai"] = ai
        sys.modules["ai.common"] = common
        sys.modules["ai.common.schema"] = schema
    # the node package does `from .IGlobal import IGlobal` — satisfy it without the package
    if "IGlobal" not in sys.modules:
        igl = types.ModuleType("IGlobal")
        igl.IGlobal = object
        sys.modules["IGlobal"] = igl


def load_iinstance(path: Path):
    _ensure_stubs()
    src = path.read_text().replace("from .IGlobal import IGlobal",
                                   "from IGlobal import IGlobal")
    mod = types.ModuleType("iinstance_under_test")
    exec(compile(src, str(path), "exec"), mod.__dict__)
    return mod.IInstance


def make(inst_cls):
    node = inst_cls.__new__(inst_cls)      # no engine: construct bare, then wire stubs
    node.documents = []
    node.maxDocuments = 64
    node.IGlobal = MagicMock()
    node.instance = MagicMock()
    return node


def prevented(fn, *a):
    """Did the call prevent the engine's default action (i.e. raise PreventDefault)?"""
    try:
        fn(*a)
        return False
    except PreventDefault:
        return True


def main() -> int:
    path = Path(os.environ.get("IINSTANCE",
                               "engine/nodes/embedding_transformer/IInstance.py"))
    inst_cls = load_iinstance(path)
    fails = []

    def check(name, cond, got=""):
        print(f"  {'PASS' if cond else 'FAIL'}  {name:60} {got}")
        if not cond:
            fails.append(name)

    print(f"IInstance under test: {path}")

    # 63 chunks: buffering path. Must prevent the default and must NOT flush.
    n = make(inst_cls)
    check("63 chunks: default prevented (buffer path)",
          prevented(n.writeDocuments, [MagicMock()] * 63))
    check("63 chunks: nothing flushed", not n.IGlobal.embedding.encodeChunks.called)

    # 64th chunk arrives: the flush path. THE BUG — stock returns without raising here,
    # so the engine's default action forwards the batch a second time.
    check("64th chunk: default STILL prevented (flush path)",
          prevented(n.writeDocuments, [MagicMock()]))
    check("64th chunk: batch was encoded exactly once",
          n.IGlobal.embedding.encodeChunks.call_count == 1,
          f"encodeChunks called {n.IGlobal.embedding.encodeChunks.call_count}x")
    check("64th chunk: batch was written downstream exactly once",
          n.instance.writeDocuments.call_count == 1,
          f"instance.writeDocuments called {n.instance.writeDocuments.call_count}x")
    check("64th chunk: buffer cleared after flush", n.documents == [])

    # 64 in one write: same contract when the batch lands whole.
    n2 = make(inst_cls)
    check("64 chunks in one write: default prevented",
          prevented(n2.writeDocuments, [MagicMock()] * 64))

    print("\n" + ("ALL PASS" if not fails else f"{len(fails)} FAILED: {fails}"))
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
