"""exp_batchsize_sweep — the pure parts, executed (register entry 4: a string that parses is not
a path that ran). Attribution carries its null controls: a reordered response must still credit
the right file, and a file with no response must be a failure row, never a dropped one."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "working"))
sys.path.insert(0, str(ROOT / "working" / "scripts"))

import exp_batchsize_sweep as bsz          # noqa: E402
import batchsize_slice as bsl              # noqa: E402


def item(name, texts):
    return {"filepath": f"/x/{name}", "upload_time": 1.5,
            "result": {"documents": [{"page_content": t} for t in texts]}}


class Batching(unittest.TestCase):
    def test_batches_cover_every_item_once_in_order(self):
        for k in (1, 8, 16, 32, 64, 128):
            g = bsz.batches(list(range(384)), k)
            self.assertEqual([x for b in g for x in b], list(range(384)))
            self.assertTrue(all(len(b) == k for b in g[:-1]))

    def test_k_larger_than_n_is_one_batch(self):
        self.assertEqual(len(bsz.batches(list(range(30)), 64)), 1)     # why n=30 cannot rank K>=32

    def test_cpus_from_spec(self):
        self.assertEqual(bsz.cpus_from_spec("0-3,8,10-11"), [0, 1, 2, 3, 8, 10, 11])


class Attribution(unittest.TestCase):
    FILES = [Path("/c/a.pdf"), Path("/c/b.pdf"), Path("/c/c.pdf")]

    def test_reordered_response_credits_by_basename(self):
        out = [item("c.pdf", ["C1", "C2", "C3"]), item("a.pdf", ["A1"]), item("b.pdf", ["B1", "B2"])]
        r = {x["doc"]: x for x in bsz.rr_batch_records(self.FILES, out, 0, 10, 20, None)}
        self.assertEqual([r[n]["n_chunks"] for n in ("a.pdf", "b.pdf", "c.pdf")], [1, 2, 3])

    def test_null_control_missing_response_is_a_failure_row(self):
        out = [item("a.pdf", ["A1"]), item("c.pdf", ["C1"])]
        rows = bsz.rr_batch_records(self.FILES, out, 0, 10, 20, None)
        self.assertEqual(len(rows), 3)
        b = [x for x in rows if x["doc"] == "b.pdf"][0]
        self.assertFalse(b["ok"])
        self.assertEqual(b["reason"], "no_response_for_file")

    def test_empty_document_is_named_not_ok(self):
        rows = bsz.rr_batch_records(self.FILES[:1], [item("a.pdf", [])], 0, 10, 20, None)
        self.assertEqual((rows[0]["ok"], rows[0]["reason"]), (False, "no_documents"))

    def test_batch_error_fails_every_file_in_it(self):
        rows = bsz.rr_batch_records(self.FILES, None, 4, 10, 20, "batch_error:TimeoutError")
        self.assertEqual([x["ok"] for x in rows], [False] * 3)
        self.assertEqual({x["batch"] for x in rows}, {4})


class Slice(unittest.TestCase):
    def test_slice_is_deterministic_disjoint_and_sized(self):
        a, b = bsl.build(384, 25), bsl.build(384, 25)
        self.assertEqual(a["slice_sha256"], b["slice_sha256"])
        self.assertEqual((len(a["measured"]), len(a["warm_docs"])), (384, 25))
        self.assertFalse(set(a["measured"]) & set(a["warm_docs"]))

    def test_null_control_a_different_n_is_a_different_slice(self):
        self.assertNotEqual(bsl.build(384, 25)["slice_sha256"], bsl.build(383, 25)["slice_sha256"])

    def test_every_stratum_is_represented(self):
        s = bsl.build(384, 25)
        self.assertTrue(all(v >= 1 for v in s["cell_take"].values()))
        self.assertEqual(sum(s["cell_take"].values()), 384)


if __name__ == "__main__":
    unittest.main(verbosity=1)
