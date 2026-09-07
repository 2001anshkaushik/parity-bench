# RocketRide, our figures against Shashi's — the configurations both harnesses ran

Sources: his held document `team_docs_received/VIDEO-FILMS50-RESULTS-2026-09-03.md`
(sha `467ff92f…`; run `films50-20260903T183805Z`, 50 films = the first 50 of the same
sealed corpus, 73.9 footage-hours, :3–6, :52), cited by line; ours from the landed
exports named in each row. His cores are the engine cgroup over the measured span
with the tasks live (:18–21) — the same basis as ours. Memory bases differ and are
labelled. One table, two configurations.

| | **RR 16×2 tuned — his** `rr-best-16x2-r1` (:25) | **RR 16×2 tuned — ours**, fresh-lifetime mean (`results/films500_lifetimes_…/export_rocketride_video_parity_blast_p3/p4.json`) | **RR out-of-the-box — his** `rr-oob-r1` (:30) | **RR out-of-the-box — ours**, 35-film default cell mean (`results/films_mainrun_20260901T204015Z/export_rocketride_video_default_blast*.json`) |
|---|---|---|---|---|
| frames/s | 12.52 | 11.613 (11.665 / 11.560) | 2.50 | 2.351 (2.360 / 2.342) |
| × realtime | 187.8 | 173.8 (174.62 / 173.05) | 37.5 | 35.26 (35.39 / 35.13) |
| effective cores (engine cgroup, tasks live) | 27.5 | 31.10 (31.171 / 31.038) | 6.3 | 6.41 (6.395 / 6.416) |
| CPU-s per frame | **2.198** | **2.679** (2.672 / 2.685) | 2.499 | 2.72 (2.71 / 2.739) |
| $ per 1,000 footage-hours ($1.428/h both) | 7.60 | 8.22 (8.18 / 8.25) | 38.06 | 40.50 (40.35 / 40.65) |
| peak memory | 25.54 GB — his "RSS GB" column | 53.2 / 50.9 GiB process-tree RSS peak (collector `peak_rss_bytes`); cgroup anon peak 45.5 / 43.1 GiB | 12.83 GB — his "RSS GB" column | 10.4 / 10.6 GiB process-tree RSS peak; cgroup anon peak 9.7 / 9.8 GiB |
| N films | 50 | 498 | 50 | 35 |
| footage hours | 73.9 | 675.7 (corpus; 498 measured) | 73.9 | 49.3 |
| reps | 2 (rep 1 cache-warm; rep 2 cold: 159.7×, 2.604 CPU-s/fr, :28, :203–215) | 2 fresh container lifetimes (+ one settled campaign pass agreeing: 11.609) | 1 (:225–226: "OOB cells one or two") | 2 |

## Cautions that must ride the table

- **Different N and wave regimes.** His 50 films over 16 tokens is 3.1
  waves (:165) — a span with ramp and drain in it; our 498 over 16 lanes
  is saturated (span and steady window coincide, 11.613 vs 11.649). His
  12.52 f/s is therefore not a steady-state figure against our 11.613.
  His HS side is worse off still (50 films / 32 workers = 1.56 waves,
  utilisation capped near 78%, :162–164) — the handicap he flags himself.
- **His rep 1 is cache-warm; ours are cold by construction.** His page
  reads his rep 2 as an I/O-stall environment effect (the same work in 18%
  more CPU-seconds while threads spin, :203–215) and calls rep 1 the clean
  one; our legs evict the corpus with proof before every pass and never
  entered that regime (I/O wait ≤ 1.4%, CPU-s/frame 2.672–2.685 across
  passes). The comparison above is his warm rep against our cold ones.
- **Different competitor frameworks** — Haystack there, LlamaIndex here;
  nothing in this table compares the competitors, and his RR-vs-HS 1.58×
  is not joinable to our figures.
- **The wave-independent quantity is CPU-seconds per frame: his 2.198 vs
  our 2.679 = +21.9%.** The throughput columns are wave-shaped; this row
  is not.
- **Memory is not like-for-like across N.** Our tokens retain ~50 MB per
  film served until the token ends (Ticket 6 criterion 5); over 498 films
  that is ~+27 GiB on 16 tokens, over his 50 it would be ~+3 GiB — which
  is the order of the difference between 53 GiB and 25.5 GB. His column
  is RSS; ours is the process-tree RSS peak, with the cgroup anon peak
  beside it.

## Observations worth sharing

- **The out-of-the-box RocketRide figure corroborates across three
  harnesses and three corpus sizes**: his 2.50 f/s / $38.06 at 50 films
  (:30), ours 2.35 / $40.50 at 35 films, and Leela's 2.367 f/s / $40.79 at
  498 films (her `runs/films500-sizing/report.txt` @ `3967d9f4`, RR
  "engine threads unpinned", one rep). One pipeline, ~6.3–6.9 cores, ~2.5–
  2.9 CPU-s/frame, ~$38–41 per 1k footage-hours: the default posture is a
  stable property of the engine, not of any harness.
- **The CPU-per-frame gap is now on two corpora and three harnesses, and
  it is ours to explain**: +19–20% on AMI against Leela and Shashi, +21.9%
  on films against Shashi's warm rep — with page cache excluded as the
  cause on both. The ask (a per-stage CPU split on one identical file, or
  an exchanged cgroup sampler stream) is unchanged.
- **His harness records CPU MHz and throttling; ours does not** (:208 —
  "3147 MHz, no throttling"). That is exactly the instrument our
  excluded pass-1 anomaly needed and lacked; it goes beside every leg of
  the next campaign.
- **His page-cache finding does not apply to us, and his measurement of
  it is why we could exclude it in one run**: he probed the effect live
  (11% iowait, six processes blocked on I/O, ~80% resident, :211–212) and
  gave it a signature — more CPU-seconds for the same work — that our
  minute-by-minute sampler could test directly; our runs showed neither
  the I/O wait nor the signature, and our anomaly ran the opposite way
  (fewer CPU-seconds).
