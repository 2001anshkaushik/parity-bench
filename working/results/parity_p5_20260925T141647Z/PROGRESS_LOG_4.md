# P5 progress log (part 4)

- 17:21Z Landed the P5 raw data at e82ceab2.
- Report generated (p5_write_specs.py formats every prose figure from analysis_p5a.json and analysis_p5_drift.json; p5_report.py; the CTO brief from p4_facts.json and analysis_p5a.json). Register entry 64 added.
- Blind recomputation round 1: three independent verifiers, one planted figure each (the readings and cells; the per-leg D1, queue depth, canary and drift note; the gates, controls and the brief's citations), the plant key kept in the session scratchpad until all had finished. Every plant caught; no other mismatch -> PASS. One out-of-scope note from verifier C (the build row's image id) was checked against the report and the build record and found to be a misreading; nothing changed.
- The final report differs from the verified copy only in its generation time and the recomputation line.
- The box has been stopped since 17:20:16 GMT (read back `stopped`, "User initiated", at 17:20:48Z).
