"""The S5-B pre-check's comparator, executed on fake detections whose answer is known. The
numerics themselves cannot be tested here — arm64 bit patterns do not transfer to the box's
x86_64 oneDNN (register entry 3) — so this proves only that the comparator is not blind."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import s5b_batch_identity_probe as p  # noqa: E402


class D:
    def __init__(self, xyxy, conf, cid):
        self.xyxy, self.confidence, self.class_id = (np.asarray(xyxy, "float32"),
                                                     np.asarray(conf, "float32"),
                                                     np.asarray(cid, "int64"))


A = D([[1, 2, 3, 4]], [0.91], [1])


class Comparator(unittest.TestCase):
    def test_identical_detections_hash_identical(self):
        self.assertEqual(p.frame_hash(A), p.frame_hash(D([[1, 2, 3, 4]], [0.91], [1])))
        self.assertEqual(p.max_abs(A, D([[1, 2, 3, 4]], [0.91], [1])), 0.0)

    def test_null_control_one_ulp_in_a_score_is_seen(self):
        b = D([[1, 2, 3, 4]], [np.nextafter(np.float32(0.91), np.float32(1))], [1])
        self.assertNotEqual(p.frame_hash(A), p.frame_hash(b))
        self.assertGreater(p.max_abs(A, b), 0.0)

    def test_null_control_a_box_coordinate_is_seen(self):
        self.assertNotEqual(p.frame_hash(A), p.frame_hash(D([[1, 2, 3, 4.0001]], [0.91], [1])))

    def test_null_control_a_different_count_is_infinite_difference(self):
        two = D([[1, 2, 3, 4], [5, 6, 7, 8]], [0.91, 0.5], [1, 2])
        self.assertNotEqual(p.frame_hash(A), p.frame_hash(two))
        self.assertEqual(p.max_abs(A, two), float("inf"))

    def test_null_control_dtype_is_part_of_identity(self):
        b = D([[1, 2, 3, 4]], [0.91], [1]); b.confidence = b.confidence.astype("float64")
        self.assertNotEqual(p.frame_hash(A), p.frame_hash(b))





class Tier2(unittest.TestCase):
    """The pre-registered Tier 2 rule, exercised at each boundary (fx = fy = 1 unless stated)."""

    def test_identical_frame_is_ok(self):
        r = p.tier2_frame(A, D([[1, 2, 3, 4]], [0.91], [1]), 1.0, 1.0)
        self.assertTrue(r["ok"])

    def test_score_delta_just_inside_passes_just_outside_fails(self):
        self.assertTrue(p.tier2_frame(A, D([[1, 2, 3, 4]], [0.91 + 0.9e-5], [1]), 1, 1)["ok"])
        self.assertFalse(p.tier2_frame(A, D([[1, 2, 3, 4]], [0.91 + 5e-5], [1]), 1, 1)["ok"])

    def test_box_tolerance_is_applied_in_OUTPUT_pixels(self):
        near = D([[1, 2, 3, 4.0008]], [0.91], [1])       # 0.0008 px in the downscaled image
        self.assertTrue(p.tier2_frame(A, near, 1.0, 1.0)["ok"])          # within 1e-3 at scale 1
        self.assertFalse(p.tier2_frame(A, near, 2.0, 2.0)["ok"])         # 0.0016 px after rescale

    def test_detection_inside_the_band_may_differ(self):
        single = D([[1, 2, 3, 4], [5, 6, 7, 8]], [0.91, 0.3005], [1, 2])   # second one in-band
        batched = D([[1, 2, 3, 4]], [0.91], [1])                           # it vanished
        self.assertTrue(p.tier2_frame(single, batched, 1, 1)["ok"])

    def test_null_control_a_detection_OUTSIDE_the_band_may_not_differ(self):
        single = D([[1, 2, 3, 4], [5, 6, 7, 8]], [0.91, 0.35], [1, 2])     # 0.35: outside band
        batched = D([[1, 2, 3, 4]], [0.91], [1])
        r = p.tier2_frame(single, batched, 1, 1)
        self.assertFalse(r["ok"])
        self.assertIn("label multiset or count", r["why"])

    def test_null_control_same_count_different_label_fails(self):
        self.assertFalse(p.tier2_frame(A, D([[1, 2, 3, 4]], [0.91], [7]), 1, 1)["ok"])

    def test_reordered_detections_still_pair_correctly(self):
        single = D([[1, 2, 3, 4], [50, 60, 70, 80]], [0.91, 0.8], [1, 1])
        batched = D([[50, 60, 70, 80], [1, 2, 3, 4]], [0.8, 0.91], [1, 1])
        self.assertTrue(p.tier2_frame(single, batched, 1, 1)["ok"])


if __name__ == "__main__":
    unittest.main(verbosity=1)
