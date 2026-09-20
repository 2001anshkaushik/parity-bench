"""percore_sampler — the arithmetic, on synthetic /proc/stat text, with the null controls that
must FAIL if the instrument cannot tell busy from idle (register entry 2)."""
from __future__ import annotations

import sys
import tempfile
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from harness.percore_sampler import (PerCoreSampler, busy_fractions, parse_proc_stat,  # noqa: E402
                                     summarise)


def stat(rows):
    """rows: {cpu: (busy_ticks, idle_ticks, iowait_ticks)} -> /proc/stat text."""
    out = ["cpu  0 0 0 0 0 0 0 0 0 0"]
    for c, (busy, idle, iow) in sorted(rows.items()):
        out.append(f"cpu{c} {busy} 0 0 {idle} {iow} 0 0 0 0 0")
    out.append("intr 12345")
    return "\n".join(out) + "\n"


class Parse(unittest.TestCase):
    def test_skips_aggregate_and_noise(self):
        p = parse_proc_stat(stat({0: (10, 90, 0), 1: (50, 40, 10)}))
        self.assertEqual(p, {0: (100, 90), 1: (100, 50)})

    def test_iowait_counts_as_idle(self):
        a = parse_proc_stat(stat({0: (0, 0, 0)}))
        b = parse_proc_stat(stat({0: (0, 50, 50)}))
        self.assertEqual(busy_fractions(a, b, [0]), {0: 0.0})


class Fractions(unittest.TestCase):
    def test_all_busy_all_idle_and_half(self):
        a = parse_proc_stat(stat({0: (0, 0, 0), 1: (0, 0, 0), 2: (0, 0, 0)}))
        b = parse_proc_stat(stat({0: (100, 0, 0), 1: (0, 100, 0), 2: (50, 50, 0)}))
        self.assertEqual(busy_fractions(a, b, [0, 1, 2]), {0: 1.0, 1: 0.0, 2: 0.5})

    def test_no_advance_is_none_never_idle(self):
        a = parse_proc_stat(stat({0: (5, 5, 0)}))
        self.assertIsNone(busy_fractions(a, a, [0]))

    def test_missing_core_is_none(self):
        a = parse_proc_stat(stat({0: (0, 0, 0)}))
        b = parse_proc_stat(stat({0: (1, 1, 0)}))
        self.assertIsNone(busy_fractions(a, b, [0, 7]))


class Summary(unittest.TestCase):
    CPUS = list(range(24))

    def test_null_control_all_busy_reports_zero_idle(self):
        s = summarise([{c: 1.0 for c in self.CPUS}] * 5, self.CPUS)
        self.assertEqual(s["idle_core_count_mean"], 0)
        self.assertEqual(s["idle_core_equivalents"], 0)

    def test_null_control_all_idle_reports_every_core(self):
        s = summarise([{c: 0.0 for c in self.CPUS}] * 5, self.CPUS)
        self.assertEqual(s["idle_core_count_mean"], 24)
        self.assertEqual(s["idle_core_equivalents"], 24)
        self.assertEqual(s["cores_idle_whole_leg"], 24)

    def test_the_two_idle_figures_disagree_by_design(self):
        # 24 cores at half load: no core is idle, yet 12 cores of capacity are unused.
        s = summarise([{c: 0.5 for c in self.CPUS}] * 3, self.CPUS)
        self.assertEqual(s["idle_core_count_mean"], 0)
        self.assertEqual(s["idle_core_equivalents"], 12)

    def test_twelve_flat_out_twelve_asleep(self):
        s = summarise([{c: (1.0 if c < 12 else 0.0) for c in self.CPUS}] * 3, self.CPUS)
        self.assertEqual(s["idle_core_count_mean"], 12)
        self.assertEqual(s["idle_core_equivalents"], 12)

    def test_threshold_is_strict_and_recorded(self):
        s = summarise([{0: 0.10, 1: 0.0999}], [0, 1], idle_threshold=0.10)
        self.assertEqual(s["idle_core_count_mean"], 1)
        self.assertEqual(s["idle_threshold"], 0.10)

    def test_empty_is_not_measured_never_zero(self):
        s = summarise([], self.CPUS)
        self.assertIsNone(s["idle_core_count_mean"])
        self.assertIsNone(s["idle_core_equivalents"])


class Thread(unittest.TestCase):
    def test_samples_a_changing_source_and_never_overwrites(self):
        with tempfile.TemporaryDirectory() as td:
            src, out = Path(td) / "stat", Path(td) / "o.jsonl"
            src.write_text(stat({0: (0, 0, 0), 1: (0, 0, 0)}))
            s = PerCoreSampler([0, 1], interval_s=0.05, out_path=out, source=src)
            s.start()
            for i in range(1, 6):
                time.sleep(0.06)
                src.write_text(stat({0: (100 * i, 0, 0), 1: (0, 100 * i, 0)}))
            time.sleep(0.1)
            r = s.stop()
            self.assertGreaterEqual(r["n_intervals"], 2)
            self.assertEqual(r["per_core_mean_busy"], {"0": 1.0, "1": 0.0})
            self.assertEqual(r["idle_core_count_mean"], 1)
            self.assertTrue(out.read_text().strip())
            with self.assertRaises(FileExistsError):
                open(out, "x")


if __name__ == "__main__":
    unittest.main(verbosity=1)
