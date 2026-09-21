"""batchsize_analyse.load_campaign — the service arm's worker count must be found in BOTH layouts
(exports beside the launches, as pulled from S3; exports one level up, as committed), and an
unknown count must REFUSE rather than pool configurations (register 39). The null controls: an
export one level up that names a DIFFERENT campaign's launch of the same name must not be used,
and a campaign with no export at all must refuse."""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import batchsize_analyse as ba  # noqa: E402


def leg(d: Path, launch: str, arm: str = "li") -> None:
    (d / launch).mkdir(parents=True, exist_ok=True)
    (d / launch / f"leg_{arm}_k1_x.json").write_text(json.dumps({
        "arm": arm, "leg": "k1_x", "verdict": "OK",
        "documents": {"submitted": 4, "recorded": 4, "ok": 4, "hard_failure_reasons": []}}))


def export(where: Path, run_dir: str, workers) -> None:
    where.mkdir(parents=True, exist_ok=True)
    n = len(list(where.glob("exp_batchsize_sweep_*.json")))
    (where / f"exp_batchsize_sweep_li__2026092{n}T000000Z__x.json").write_text(json.dumps(
        {"data": {"run_dir": run_dir, "posture": {"ws1_workers": workers}}}))


class Layouts(unittest.TestCase):
    def setUp(self):
        ba.LAUNCHES = None

    def test_exports_beside_launches(self):
        with tempfile.TemporaryDirectory() as t:
            d = Path(t) / "s3b_copy"
            leg(d, "li_w16"); export(d, "working/results/batchsize_s3b_X/li_w16", 16)
            self.assertEqual([g["arm_units"] for g in ba.load_campaign(d)], [16])

    def test_exports_one_level_up_naming_this_campaign(self):
        with tempfile.TemporaryDirectory() as t:
            root = Path(t) / "working" / "results"; d = root / "batchsize_s3b_X"
            leg(d, "li_w16"); export(root, "working/results/batchsize_s3b_X/li_w16", 16)
            self.assertEqual([g["arm_units"] for g in ba.load_campaign(d)], [16])

    def test_null_other_campaigns_launch_of_the_same_name_is_not_used(self):
        with tempfile.TemporaryDirectory() as t:
            root = Path(t) / "working" / "results"; d = root / "batchsize_s3b_X"
            leg(d, "li_w16"); export(root, "working/results/batchsize_OTHER/li_w16", 32)
            with self.assertRaises(SystemExit) as e:
                ba.load_campaign(d)
            self.assertIn("worker count is unknown", str(e.exception))

    def test_null_no_export_refuses_instead_of_pooling(self):
        with tempfile.TemporaryDirectory() as t:
            d = Path(t) / "c"
            leg(d, "li_w16"); leg(d, "li_w32")
            with self.assertRaises(SystemExit) as e:
                ba.load_campaign(d)
            self.assertIn("worker count is unknown", str(e.exception))

    def test_rocketride_needs_no_export(self):
        with tempfile.TemporaryDirectory() as t:
            d = Path(t) / "c"
            leg(d, "rr_a", arm="rr")
            self.assertEqual([g["arm_units"] for g in ba.load_campaign(d)], [1])

    def test_launch_selector(self):
        with tempfile.TemporaryDirectory() as t:
            d = Path(t) / "c"
            leg(d, "rr_a", arm="rr"); leg(d, "rr_b", arm="rr")
            ba.LAUNCHES = {"rr_b"}
            self.assertEqual([g["_launch"] for g in ba.load_campaign(d)], ["rr_b"])


def mk(arm, k, c, cond, units, dps, cores=1.0, launch="x"):
    return {"arm": arm, "k": k, "reference_c": c, "condition": cond, "arm_units": units, "verdict": "OK",
            "_launch": launch, "leg": "l", "throughput": {"docs_per_s": dps},
            "cost": {"engine_container_cores": cores}}


class Partitions(unittest.TestCase):
    """cache_effect compares a cold leg only with warm legs of the SAME arm shape (register 39)."""
    def test_cold_compared_with_its_own_worker_count_only(self):
        legs = [mk("li", None, 32, "warm", 24, 3.6), mk("li", None, 32, "warm", 24, 3.4),
                mk("li", None, 32, "warm", 16, 3.2), mk("li", None, 32, "warm", 32, 3.3),
                mk("li", None, 32, "cold", 24, 3.2835)]
        ce = ba.cache_effect(legs)["li"]
        self.assertEqual(list(ce), ["C=32@units=24"])
        self.assertEqual(ce["C=32@units=24"]["warm_runs"], [3.6, 3.4])

    def test_null_pooling_would_have_moved_the_delta(self):
        # the same legs, pooled across worker counts, give a different delta: the test can see the bug
        legs = [3.6, 3.4, 3.2, 3.3]
        pooled = (3.2835 / (sum(legs) / 4) - 1) * 100
        partitioned = (3.2835 / 3.5 - 1) * 100
        self.assertGreater(abs(pooled - partitioned), 1.0)

    def test_reference_units_is_the_warm_mode(self):
        legs = [mk("li", 128, None, "warm", 24, 1), mk("li", 128, None, "warm", 24, 1),
                mk("li", None, 32, "warm", 16, 1), mk("li", 128, None, "cold", 16, 1),
                mk("li", 128, None, "cold", 16, 1), mk("li", 128, None, "cold", 16, 1)]
        self.assertEqual(ba.reference_units(legs), {"li": 24})


if __name__ == "__main__":
    unittest.main(verbosity=1)
