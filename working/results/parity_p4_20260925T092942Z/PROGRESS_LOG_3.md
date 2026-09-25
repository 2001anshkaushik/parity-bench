# P4 progress log (part 3)

- 09:43:28Z–13:27:07Z The P4-A chain ran all ten legs in the pre-registered order, each alone and each rc 0. After every leg G_d0 read CLEAN and G_cell PASS; G_memstat passed after the first leg; G_correct_active PASSED at chain end. No retry was needed and nothing was NOT RUN. The chain finished before the 14:43:28Z deadline. rr:patched, rr:patched-video and li:video ids were unchanged at start and end.
- Monitoring: the first two laptop monitors tailed the box log over SSM and delivered nothing after their first poll. Part of the cause was that grep treated the log as binary and dropped later matches (fixed with `grep -a`); even after that fix the SSM tail stayed silent. The watch moved to S3 listings (the chain uploads each leg and gate record as it completes). That worked; the chain itself was never affected.
- 13:28Z Box logs uploaded to S3 and copied; all S3 objects of the campaign checked present locally with equal sizes.
- 13:29Z Box: no container, no chain process, protected ids unchanged; `box.sh stop`; read back `stopped`, "User initiated (2026-09-25 13:29:24 GMT)" at 13:30:36Z.
- Analysis: `p4_analyse_a.py` -> analysis_p4a.json (R1 and R2/R3 by the pre-registered rules); `p4_posthoc_a.py` -> analysis_p4a_posthoc.json (POST-HOC: the drift between rounds, per-round readings, ACTIVE's cost); `p4_facts.py` regenerated with the P4-A rows; `p4_write_specs.py` builds every prose figure from the analysis files; `p4_report.py` -> P4_REPORT.md.
- Register entries 61 (a gate that read the record before its writer finished it) and 62 (a session that drifted between its rounds) added.
- Next: blind recomputation with planted figures, then the deliverable landing.
