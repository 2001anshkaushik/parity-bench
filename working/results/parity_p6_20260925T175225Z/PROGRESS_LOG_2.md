# P6 progress log (part 2)

- 17:52Z Landed the pre-registration and tooling at 8e4cf34a; 17:55Z addendum 1 (the drift-note rule) at c0af3f83, before any measured leg.
- 17:53Z Box started (boot eb83839f); no container; rr:patched, rr:patched-video, li:video and rr:p5-infer (P5's sha256:b42c03b6…, not rebuilt) read back; worktree `~/parity-bench-p6` at 8e4cf34a.
- 17:54Z–18:15Z Control stage (gate-control targets, not measured legs): p6ctl_p5t16 (rr:p5-infer, six vars unset — the on-token read-back reported torch 16 threads, one LWDETR), p6ctl_lit16 (li:video T=16), p6ctl_warm_rr and p6ctl_warm_li (T=4, --warm-sends 2 --warm-concurrency 2) — all rc 0.
- 18:15Z Gate controls (gate_controls.json, run 1, on the box): every control as expected, all_pass.
- 18:15:37Z The run stage launched (`p6_run`); deadline 02:15:37Z. The new SSO session (approved 17:44Z) outlasts it.
