"""batchsize_analyse_threads.frame_compare — per-frame output of two video legs from the driver's
records. The null control: a leg compared with itself (or an identical replicate) must report full
identity and a zero delta; a perturbed score, a changed label and a changed count must each be seen."""
from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import batchsize_analyse_threads as bat  # noqa: E402


def leg():
    return {"v1": {"chunk_sha256": "aa", "frame_label_multisets": [["person", "tv"], ["person"]],
                   "frame_scores": [[0.9, 0.4], [0.7]]},
            "v2": {"chunk_sha256": "bb", "frame_label_multisets": [["cup"]], "frame_scores": [[0.35]]}}


class FrameCompare(unittest.TestCase):
    def test_null_control_identity(self):
        r = bat.frame_compare(leg(), leg())
        self.assertEqual((r["frames"], r["frames_label_multiset_identical"], r["frames_detection_count_identical"],
                          r["max_abs_score_delta_at_least"], r["chunk_identical_videos"]), (3, 3, 3, 0.0, 2))

    def test_a_score_change_is_seen_and_labels_still_match(self):
        b = leg(); b["v1"]["frame_scores"][0][1] = 0.4022; b["v1"]["chunk_sha256"] = "zz"
        r = bat.frame_compare(leg(), b)
        self.assertAlmostEqual(r["max_abs_score_delta_at_least"], 0.0022, places=6)
        self.assertEqual((r["frames_label_multiset_identical"], r["chunk_identical_videos"]), (3, 1))

    def test_a_label_change_is_seen(self):
        b = leg(); b["v2"]["frame_label_multisets"][0] = ["bottle"]
        self.assertEqual(bat.frame_compare(leg(), b)["frames_label_multiset_identical"], 2)

    def test_a_count_change_is_seen(self):
        b = leg(); b["v1"]["frame_label_multisets"][1] = ["person", "person"]; b["v1"]["frame_scores"][1] = [0.7, 0.31]
        r = bat.frame_compare(leg(), b)
        self.assertEqual(r["frames_detection_count_identical"], 2)

    def test_sorted_pairing_is_a_lower_bound(self):
        # scores swapped between two detections: sorted pairing sees no change, the TRUE pairing would;
        # the figure is therefore labelled "at least"
        a = {"v": {"chunk_sha256": "x", "frame_label_multisets": [["a", "a"]], "frame_scores": [[0.5, 0.6]]}}
        b = copy.deepcopy(a); b["v"]["frame_scores"] = [[0.6, 0.5]]
        self.assertEqual(bat.frame_compare(a, b)["max_abs_score_delta_at_least"], 0.0)


if __name__ == "__main__":
    unittest.main(verbosity=1)
