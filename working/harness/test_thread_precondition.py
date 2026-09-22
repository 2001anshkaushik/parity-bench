"""thread_settings_matched's precondition, driven with the engine STUBBED so every outcome is
deterministic. Ansh's ruling, 2026-09-21: unreachable must SKIP and never pass; reachable and
failing must REFUSE (land in FAIL, which gate 3 refuses as a failure not in the baseline)."""
from __future__ import annotations

import json
import sys
import types
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import regression_selftest as rs  # noqa: E402


def mr(et, lt=None, raise_on_engine=None):
    m = types.SimpleNamespace()
    def engine_threads():
        if raise_on_engine:
            raise raise_on_engine
        return et
    m.engine_threads, m.llama_threads = engine_threads, (lambda: lt if lt is not None else et)
    return m


class Precondition(unittest.TestCase):
    def setUp(self):
        for lst in (rs.PASS, rs.FAIL, rs.SKIP, rs.XFAIL, rs.XPASS):
            lst.clear()
        self._saved = (rs.engine_up, rs.our_engine_on_port, rs.engine_runs_pipelines,
                       rs._load_matched_replication, rs.engine_bundle_present)
        rs.engine_up = lambda *a, **k: True
        rs.our_engine_on_port = lambda *a, **k: (True, "stubbed: ours")
        # Stubbed too: without this the tests passed only where the untracked engine/ bundle exists.
        rs.engine_bundle_present = lambda: True

    def tearDown(self):
        (rs.engine_up, rs.our_engine_on_port, rs.engine_runs_pipelines,
         rs._load_matched_replication, rs.engine_bundle_present) = self._saved

    def run_check(self):
        rs.check("thread_settings_matched", "stubbed", rs.t_thread_settings_matched)

    def test_null_control_no_bundle_skips_and_never_passes(self):
        rs.engine_bundle_present = lambda: False
        rs.engine_runs_pipelines = lambda *a, **k: self.fail("probed an engine this tree cannot drive")
        rs._load_matched_replication = lambda: self.fail("the test ran without a bundle")
        self.run_check()
        self.assertEqual([n for n, _ in rs.SKIP], ["thread_settings_matched"])
        self.assertEqual((rs.PASS, rs.FAIL), ([], []))

    def test_null_control_unreachable_skips_and_never_passes(self):
        rs.engine_runs_pipelines = lambda *a, **k: (False, "stub: no echo")
        rs._load_matched_replication = lambda: self.fail("the test ran past a failed precondition")
        self.run_check()
        self.assertEqual([n for n, _ in rs.SKIP], ["thread_settings_matched"])
        self.assertEqual(rs.PASS, [])
        self.assertEqual(rs.FAIL, [])

    def test_null_control_reachable_and_mismatched_threads_fails(self):
        rs.engine_runs_pipelines = lambda *a, **k: (True, "stub: echoed")
        rs._load_matched_replication = lambda: mr(et=1, lt=4)
        self.run_check()
        self.assertEqual([n for n, _ in rs.FAIL], ["thread_settings_matched"])
        self.assertEqual(rs.SKIP, [])

    def test_null_control_reachable_but_probe_returns_garbage_fails_never_skips(self):
        # The exact flake signature, now AFTER a successful precondition: it must be a failure.
        rs.engine_runs_pipelines = lambda *a, **k: (True, "stub: echoed")
        rs._load_matched_replication = lambda: mr(et=None, raise_on_engine=json.JSONDecodeError("Expecting value", "", 0))
        self.run_check()
        self.assertEqual([n for n, _ in rs.FAIL], ["thread_settings_matched"])
        self.assertEqual(rs.SKIP, [])

    def test_reachable_and_matched_passes(self):
        rs.engine_runs_pipelines = lambda *a, **k: (True, "stub: echoed")
        rs._load_matched_replication = lambda: mr(et=4, lt=4)
        self.run_check()
        self.assertEqual(rs.PASS, ["thread_settings_matched"])


if __name__ == "__main__":
    unittest.main(verbosity=1)
