"""results_prefix.sh — the S3 key that mirrors a path under working/results/, on relative and
absolute paths, with the null controls: the OLD expression must fail the same case table, and
the static guard must flag a synthetic script that still derives its own key."""
from __future__ import annotations

import re
import subprocess
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
HELPER = REPO / "working" / "harness" / "results_prefix.sh"

# (input, results_rel expected or None for "must refuse")
REL_CASES = [
    ("working/results/batchsize_s4_X", "batchsize_s4_X"),
    ("working/results/batchsize_s4_X/", "batchsize_s4_X"),
    ("./working/results/batchsize_s5_X/s5c", "batchsize_s5_X/s5c"),
    ("/home/ubuntu/parity-bench-batch/working/results/batchsize_s5_X/s5a", "batchsize_s5_X/s5a"),
    ("/home/ubuntu/parity-bench-batch/working/results/batchsize_s5_X/s5b/", "batchsize_s5_X/s5b"),
    ("/tmp/elsewhere/run", None),
    ("working/results", None),
    ("working/results/", None),
    ("results/batchsize_s4_X", None),
    ("", None),
]
PARENT_CASES = [
    # every banked docs launch is <campaign>/<leg>: the key must equal the old basename(dirname)
    ("working/results/batchsize_s4_X/e7_rr_k256", "batchsize_s4_X"),
    # two levels deep: the old basename(dirname) gave a top-level "s5c"
    ("working/results/batchsize_s5_X/s5c/rr_b", "batchsize_s5_X/s5c"),
    ("/home/ubuntu/b/working/results/batchsize_s5_X/s5d/rr_stamped", "batchsize_s5_X/s5d"),
    ("working/results/batchsize_s4_X", None),      # a campaign dir is not a leg
    ("/tmp/x/y", None),
]

OLD_REL = 'old_rel() { printf "%s\\n" "${1##*/working/results/}"; }'
OLD_PARENT = 'old_parent() { basename "$(dirname "$1")"; }'


def sh(func: str, arg: str, prelude: str = "") -> tuple[int, str]:
    src = prelude or f'. "{HELPER}"'
    r = subprocess.run(["bash", "-c", f'{src}; {func} "$1"', "_", arg], capture_output=True, text=True)
    return r.returncode, r.stdout.strip()


def table_ok(func: str, cases, prelude: str = "") -> list:
    """Every case whose result differs from the expectation; empty means the table passes."""
    bad = []
    for arg, want in cases:
        rc, out = sh(func, arg, prelude)
        got = out if rc == 0 else None
        if want is None and (rc == 0 or out):
            bad.append((arg, "should refuse", rc, out))
        elif want is not None and got != want:
            bad.append((arg, want, rc, out))
    return bad


# THE STATIC GUARD: a script that uploads under batch-size-optimization/ derives its key through
# the helper, and nothing still carries the old expression outside a comment.
OLD_PATTERN = re.compile(r"\$\{[A-Za-z_][A-Za-z_0-9]*##\*/working/results/\}")


def offending(text: str) -> list:
    code = [l for l in text.splitlines() if not l.lstrip().startswith("#")]
    probs = [l.strip() for l in code if OLD_PATTERN.search(l)]
    uploads = any("batch-size-optimization/" in l for l in code)
    if uploads and not any(re.search(r"\bresults_(parent_)?rel\b", l) for l in code):
        probs.append("uploads under batch-size-optimization/ without results_rel")
    return probs


class Helper(unittest.TestCase):
    def test_results_rel(self):
        self.assertEqual(table_ok("results_rel", REL_CASES), [])

    def test_results_parent_rel(self):
        self.assertEqual(table_ok("results_parent_rel", PARENT_CASES), [])

    def test_refusal_prints_nothing(self):
        rc, out = sh("results_rel", "/tmp/elsewhere/run")
        self.assertEqual((rc, out), (1, ""))


class NullControls(unittest.TestCase):
    def test_old_expression_fails_the_same_table(self):
        bad = table_ok("old_rel", REL_CASES, prelude=OLD_REL)
        self.assertIn("working/results/batchsize_s4_X", [b[0] for b in bad],
                      "the table cannot see the relative-path defect it exists to catch")

    def test_old_parent_fails_two_levels_deep(self):
        bad = table_ok("old_parent", PARENT_CASES[:3], prelude=OLD_PARENT)
        self.assertEqual([b[0] for b in bad],
                         ["working/results/batchsize_s5_X/s5c/rr_b",
                          "/home/ubuntu/b/working/results/batchsize_s5_X/s5d/rr_stamped"],
                         "old and new must agree one level deep and disagree two levels deep")

    def test_static_guard_flags_a_synthetic_offender(self):
        bad = 'aws s3 cp x "s3://b/ansh/batch-size-optimization/${D##*/working/results/}/x"\n'
        self.assertEqual(len(offending(bad)), 2)
        self.assertEqual(offending('# ${D##*/working/results/} in a comment only\n'), [])


class Scripts(unittest.TestCase):
    def test_no_script_derives_its_own_key(self):
        found = {}
        for p in sorted((REPO / "working" / "scripts").glob("*.sh")) + sorted((REPO / "working" / "harness").glob("*.sh")):
            probs = offending(p.read_text())
            if probs:
                found[p.name] = probs
        self.assertEqual(found, {})

    def test_every_uploading_script_sources_the_helper(self):
        source = re.compile(r"(?m)^\s*\. \"?[^\n]*working/harness/results_prefix\.sh")
        missing = [n for n in ("batchsize_docs_run.sh", "batchsize_video_run.sh", "batchsize_stage4_envelope.sh",
                               "batchsize_stage5_all.sh", "batchsize_stage5b_precheck.sh", "batchsize_stage5b.sh",
                               "batchsize_stage5c_smt.sh")
                   if not source.search((REPO / "working" / "scripts" / n).read_text())]
        self.assertEqual(missing, [])

    def test_helper_sources_cleanly_in_a_fresh_shell(self):
        with tempfile.TemporaryDirectory() as t:
            r = subprocess.run(["bash", "-euo", "pipefail", "-c", f'. "{HELPER}"; results_rel working/results/a/b'],
                               capture_output=True, text=True, cwd=t)
            self.assertEqual((r.returncode, r.stdout.strip()), (0, "a/b"))


if __name__ == "__main__":
    unittest.main(verbosity=1)
