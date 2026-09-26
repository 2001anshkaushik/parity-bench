# P7 progress log (part 2)

- 09:05Z Pre-registration and tooling landed at 06a9d543 (before P7-A was computed and before any leg).
- 09:06Z P7-A computed on the laptop by `p7_frames.py` from committed exports: NOT BOUNDARY — C1 failed (on IN1002.avi frame 58 and TS3010a.avi frame 56 every detection's score differs between the banked stock run and the prototype, by up to 0.0173 and 0.0144; the one detection near the threshold, the prototype's extra 'book' at 0.3017, sits 0.0017 from it, outside ±0.001), C2 holds (every other frame of both videos: identical scores and labels), C3 NOT EVALUABLE (no committed export records boxes). Landed at ed2cb388 before any box time.
- 09:13Z SSO: role credentials valid to 11:09Z — now within 2 h of expiry and the box run would outlast them; `box.sh login` opened the authorization page and Ansh approved it (the new session, from 09:14Z, carries a refresh token).
- 09:14Z Box started (boot e80a450e): no container; rr:patched, rr:patched-video, li:video and rr:p5-infer (P5's b42c03b6…, not rebuilt) read back unchanged; microcode 0x2b000661 (recorded per leg from now on; P1-D's and P6's sessions did not record it). Worktree `~/parity-bench-p7` at ed2cb388.
- 09:15:46Z–09:18:50Z Control stage: p7ctl_cap (rr:patched-video, T=4, K=1, TS3007a.avi, --keep-detections) rc 0 — a gate-control target, not a measured leg.
- 09:19Z Gate controls on the box (`gate_controls.json`, run 1): 42 of 42 as expected, all_pass (every G_tier2 control gave its expected reading; G_detcap passed the real capture and failed a changed score and a missing file).
- 09:19:38Z Run stage launched (`p7_run`); deadline 12:19:38Z.
