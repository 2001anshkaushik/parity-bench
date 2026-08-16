# working/results — DO NOT QUOTE ANY NUMBER IN HERE

Everything committed to this directory is **wiring validation, not a measurement.**

Every `smoke50_parser_in__*.json` here carries `metrics.publishable: false` — 19 of 19,
checked. Six are stamped `Darwin/arm64` and the rest predate the platform stamp. **The pinned
target is Linux x86_64**; throughput, latency and cost from any other platform prove only that
the harness is wired up.

The publishable records live on the box under `working/results/run10k/` and are mirrored to
`s3://rocketride-benchmark-data/ansh/run10k/`. They are not in git.

## Before quoting anything from a run in here or on the box

Read `publishable/STATE.md` §0a first. It carries a **never-quote list** and three rules that
invalidate most naive readings of these files:

1. **Scale is not comparable across `n`.** A 200-document throughput figure is structurally
   biased low against a 10,000-document one *for the same engine* — the slowest 1 % of GovDocs1
   documents carry 58.6 % of all service seconds, so a short run's span is governed by maxima
   rather than means. Simulated 9.44× at C=32. Never put figures from different `n` in one table.
2. **Blast latency written before `79ad702` is invalid** (defect #29). The two arms started the
   latency clock at different points. Throughput from the same records is unaffected and stands.
3. **Summed RSS is not a memory footprint** (defects #26, #30, #31), and any `cgroup anon` from
   before `d8edb17` is a post-leg point sample, not a peak.

## What the subdirectories are

* `smoke_metrics_<stamp>/` — per-document JSONL (`perdoc_<arm>_<leg>.jsonl`) and sampler streams
  (`sampler_<arm>_<leg>.jsonl` + `.summary.json`) for one run. These are the raw evidence; the
  `smoke50_parser_in__*.json` beside them is the derived report.
* `corpus_manifest.jsonl` — the 10,000-document corpus definition (name, sha256, bytes, pages,
  extracted chars). `fetch_govdocs.py` verifies against this; `DONE` means verified.

## Tools that read these files

    working/scripts/analyze_sampler.py        process fan-out and memory trajectory
    working/scripts/throughput_ramp.py        why n=200 and n=10k disagree
    working/scripts/blast_latency_salvage.py  service latency from pre-fix blast records
