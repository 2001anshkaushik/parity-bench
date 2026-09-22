"""batchsize_analyse_s5ef — on synthetic legs whose answer is known. Null controls: a leg whose
in-process read-back contradicts its declared posture must be EXCLUDED (never averaged in), and a
posture effect inside the noise must read as NOT readable."""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "batchsize_analyse_s5ef.py"
SIX = ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS", "VECLIB_MAXIMUM_THREADS",
       "NUMEXPR_NUM_THREADS", "TORCH_NUM_THREADS")


def mk(d: Path, name: str, dps: float, env_val, torch: int, c: int = 32) -> None:
    ld = d / name
    ld.mkdir(parents=True)
    n = 100
    span = n / dps
    rows = [{"doc": f"d{i}", "ok": True, "submit_ns": 0, "completion_ns": int((i + 1) / n * span * 1e9)} for i in range(n)]
    (ld / f"perdoc_rr_refc{c}_x.jsonl").write_text("\n".join(json.dumps(r) for r in rows) + "\n")
    (ld / f"leg_rr_refc{c}_x.json").write_text(json.dumps({
        "verdict": "OK", "reference_c": c, "throughput": {"docs_per_s": dps, "span_s": span},
        "documents": {"ok": n}, "cost": {"cpu_s_per_doc": 5.0, "engine_container_cores": 10.0},
        "percore_host": {"idle_core_equivalents": 20.0}}))
    exp = d / f"exp_{name}.json"
    env = {k: env_val for k in SIX} if env_val is not None else {k: None for k in SIX}
    exp.write_text(json.dumps({"data": {"posture": {"thread_env_expected": env_val,
                                                    "in_process_readback": {"env": env, "torch_num_threads": torch}}}}))
    (ld / "export_path.txt").write_text(f"/box/working/results/{exp.name}\n")


def run(d: Path) -> dict:
    r = subprocess.run([sys.executable, str(SCRIPT), str(d)], capture_output=True, text=True)
    return json.loads(r.stdout)


class S5EF(unittest.TestCase):
    def test_effect_beyond_the_noise_is_readable(self):
        with tempfile.TemporaryDirectory() as t:
            d = Path(t)
            mk(d, "rr_env1_a", 2.40, "1", 1); mk(d, "rr_env1_b", 2.41, "1", 1)
            mk(d, "rr_unset_a", 2.10, None, 16); mk(d, "rr_unset_b", 2.11, None, 16)
            r = run(d)["s5e"]["docs_per_s"]
            self.assertTrue(r["readable"])
            self.assertLess(r["unset_vs_env1"], -0.1)

    def test_null_control_an_effect_inside_the_noise_is_not_readable(self):
        with tempfile.TemporaryDirectory() as t:
            d = Path(t)
            mk(d, "rr_env1_a", 2.40, "1", 1); mk(d, "rr_env1_b", 2.44, "1", 1)
            mk(d, "rr_unset_a", 2.41, None, 16); mk(d, "rr_unset_b", 2.43, None, 16)
            self.assertFalse(run(d)["s5e"]["docs_per_s"]["readable"])

    def test_null_control_a_leg_whose_readback_contradicts_its_posture_is_excluded(self):
        with tempfile.TemporaryDirectory() as t:
            d = Path(t)
            mk(d, "rr_env1_a", 2.40, "1", 1); mk(d, "rr_env1_b", 2.41, "1", 1)
            mk(d, "rr_unset_a", 2.10, None, 16); mk(d, "rr_unset_b", 2.11, "1", 1)   # declared unset, ran =1
            out = run(d)
            self.assertEqual([e["leg"] for e in out["excluded"]], ["rr_unset_b"])
            self.assertIsNone(out["s5e"]["docs_per_s"]["unset"])     # one valid run: no pair, no effect


if __name__ == "__main__":
    unittest.main(verbosity=1)
