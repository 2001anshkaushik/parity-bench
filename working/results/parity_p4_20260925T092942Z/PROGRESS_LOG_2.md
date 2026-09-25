# P4 progress log (part 2)

- 09:35Z Landed the pre-registration and tooling at 1fcb6ce4 (autoland: all gates, ls-remote read-back).
- 09:36Z Box started (boot ff48c148); no container present; rr:patched, rr:patched-video and li:video ids read back (unchanged); worktree `~/parity-bench-p4` created at 1fcb6ce4; the box venv imports psutil.
- 09:37Z–09:41Z The gate-control target `p4ctl_active` (not a measured leg): RocketRide, OMP_WAIT_POLICY=ACTIVE, T=4, K=2, 2 videos, stamped, on-token D0 — rc 0. Its in-process read-back shows OMP_WAIT_POLICY=ACTIVE and torch 4 threads in the detector's own environment.
- 09:42Z Gate controls (`gate_controls.json`, run 1, on the box's venv and docker): every control came out as expected (all_pass). Laptop dry run earlier had caught the G_d0 defect (fixed before commit; PROGRESS_LOG.md).
- 09:43:28Z The P4-A run launched (`p4a_run`); first leg p4a_rr16_1; deadline 14:43:28Z.
- Laptop, while the box measures: P4-B (1) and (2) computed from committed legs by `p4_analyse_b.py` into `analysis_p4b.json` (the rules were fixed in the pre-registration first); P4-B (3) design draft written (its "which reading" section written before any P4-A data); the P4-A analyser `p4_analyse_a.py` written.
