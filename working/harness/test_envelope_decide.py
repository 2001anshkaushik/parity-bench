"""batchsize_envelope_decide — the K=512 rule on synthetic legs whose answer is known, with the
null controls that must refuse or skip (register entry 2)."""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "batchsize_envelope_decide.py"


def leg(d: Path, arm: str, k: int, docs_per_s: float, n: int = 1000) -> None:
    """n documents completing evenly at docs_per_s — p99 throughput equals docs_per_s."""
    ld = d / f"{arm}_k{k}"
    ld.mkdir(parents=True, exist_ok=True)
    with open(ld / f"perdoc_{arm}_k{k}_main.jsonl", "w") as f:
        for i in range(n):
            f.write(json.dumps({"doc": f"d{i}", "ok": True, "submit_ns": 0,
                                "completion_ns": int((i + 1) / docs_per_s * 1e9)}) + "\n")


def run(d: Path, floors: dict) -> tuple[int, str, dict]:
    fl = d / "floors.json"
    fl.write_text(json.dumps(floors))
    out = d / "decision.json"
    r = subprocess.run([sys.executable, str(SCRIPT), str(d), str(fl), str(out)],
                       capture_output=True, text=True)
    return r.returncode, r.stdout, (json.loads(out.read_text()) if out.exists() else {})


class Decide(unittest.TestCase):
    def test_flat_pair_skips_512(self):
        with tempfile.TemporaryDirectory() as t:
            d = Path(t)
            leg(d, "rr", 128, 2.00); leg(d, "rr", 256, 2.01)      # +0.5% against a 0.82% floor
            rc, out, dec = run(d, {"rr": 0.0082, "li": 0.0987})
            self.assertEqual(rc, 0)
            self.assertIn("RUN_512 rr no", out)
            self.assertFalse(dec["arms"]["rr"]["run_512"])

    def test_real_change_runs_512(self):
        with tempfile.TemporaryDirectory() as t:
            d = Path(t)
            leg(d, "rr", 128, 2.00); leg(d, "rr", 256, 2.30)      # +15% against a 0.82% floor
            rc, out, dec = run(d, {"rr": 0.0082, "li": 0.0987})
            self.assertIn("RUN_512 rr yes", out)
            self.assertTrue(dec["arms"]["rr"]["run_512"])

    def test_same_delta_different_floor_gives_different_answer(self):
        # +5%: a real change for the engine arm's 0.82% floor, noise for the service arm's 9.87%.
        with tempfile.TemporaryDirectory() as t:
            d = Path(t)
            leg(d, "rr", 128, 2.0); leg(d, "rr", 256, 2.1)
            leg(d, "li", 128, 3.0); leg(d, "li", 256, 3.15)
            rc, out, dec = run(d, {"rr": 0.0082, "li": 0.0987})
            self.assertTrue(dec["arms"]["rr"]["run_512"])
            self.assertFalse(dec["arms"]["li"]["run_512"])

    def test_null_control_missing_leg_is_not_decidable_never_skip(self):
        with tempfile.TemporaryDirectory() as t:
            d = Path(t)
            leg(d, "rr", 128, 2.0)                               # no K=256 leg at all
            rc, out, dec = run(d, {"rr": 0.0082, "li": 0.0987})
            self.assertIn("NOT_DECIDABLE", out)
            self.assertEqual(dec["arms"]["rr"]["verdict"], "NOT DECIDABLE")

    def test_null_control_refuses_to_overwrite_a_decision(self):
        with tempfile.TemporaryDirectory() as t:
            d = Path(t)
            leg(d, "rr", 128, 2.0); leg(d, "rr", 256, 2.3)
            run(d, {"rr": 0.0082, "li": 0.0987})
            rc, _, _ = run(d, {"rr": 0.5, "li": 0.5})             # a second, looser floor
            self.assertEqual(rc, 3)


if __name__ == "__main__":
    unittest.main(verbosity=1)
