# Phase 2 video dataflow — what happens, and where every number is read

**Audience:** Shashi, Leela — same assumption as `samples/README.md`: technical,
no knowledge of the build conversation, ten minutes. This document is
**descriptive**: what happens to one video on each arm, and where each exported
number is physically measured. The *why* behind each design choice lives in
`samples/README.md` (metrics, gates, postures, deliberate absences) and
`METHODOLOGY_REGISTER.md` (lessons); decisions are not re-argued here.

The workload in one line: AMI meeting videos (AVI, 470–2905 s each) → one
frame per 15 s → RF-DETR object detection per frame → detections serialized as
JSON text → accumulated and split into ~4000-char chunks → MiniLM embeddings →
returned to the driver, which writes one record per video.

---

## 1. One video's journey, per arm

Both arms start identically: the driver reads the `.avi` bytes off disk
(sha256 recorded as `submitted_sha256`), submits in manifest order, and stamps
`enqueue_ns` before admission and `admit_ns` at admission. Everything below
happens between `admit_ns` and `done_ns`.

### RocketRide arm (engine 3.3.1, container `rr`, port 5565, host networking)

| Stage | Component | What happens |
|---|---|---|
| transport | `RocketRideClient` (SDK, websocket) | `use(filepath=…, ttl=7200)` loads a generated variant of the measured pipe (fresh `project_id`; content otherwise byte-identical — base pipe sha256 is the recorded identity). The engine spawns **one task subprocess per token**; node code runs on the CPython 3.12.13 embedded in the engine binary, not the container's PATH python. `send(token, avi_bytes, mimetype='video/x-msvideo')` delivers the video. |
| decode → frames | `frame_grabber_1` (profile `interval`, interval 15 s) | The engine's bundled ffmpeg (imageio-ffmpeg, pinned) runs `fps=1/15`; PNG frames on the image lane. |
| detection | `detect_1` (profile `rfdetr`, threshold 0.3) | `RFDETRBase.predict` per frame. Inference is serialized by a **per-process device lock** — one detector instance per task subprocess. Output per frame: a JSON array of `{label, score, box{x1,y1,x2,y2}, centroid{x,y}}` on the text lane. |
| accumulate → split | `preprocessor_1` (`preprocessor_langchain`) | Per-frame text accumulates for the whole video, then splits **once** at close, via LangChain `RecursiveCharacterTextSplitter` running at **library defaults 4000/200 chars** (the node's own size configuration is inert — measured from records; see the register). |
| embed | `embedding_1` (profile `miniLM`) | `sentence-transformers/multi-qa-MiniLM-L6-cos-v1`, 384-dim vector per chunk. |
| response | `response_1` (`response_documents`) | Reply: `{'documents': [{page_content, embedding, metadata{chunkId}}, …]}`. |

### LlamaIndex arm (FastAPI service, container `li_video`, port 8802, host networking)

| Stage | Component | What happens |
|---|---|---|
| transport | `POST /process_video` (octet-stream body = the same bytes) | uvicorn runs **W worker processes** (`WS1V_WORKERS`); the kernel's accept routing picks the worker (not round-robin — every response carries the serving `pid`). |
| decode → frames | `pipeline._extract_frames` | The **same ffmpeg binary** (same imageio-ffmpeg pin ⇒ byte-identical executable) with the **identical filter** `fps=1/15`, PNG via image2pipe, split on the PNG signature. Per-frame `frame_png_sha16` recorded. |
| detection | `pipeline._detect_frame` | `RFDETRBase().predict(image, threshold=0.3)` under a **per-worker lock** (mirror of the engine's device lock). Detections serialized to the same canonical dict, `json.dumps` per frame. No fallback: if rfdetr fails to import, this arm refuses to serve. |
| accumulate → split | `pipeline.process` | Per-frame JSON joined with `'\n'` (+ trailing newline), split **once per video** by LlamaIndex-native `SentenceSplitter(chunk_size=4000, chunk_overlap=200, tokenizer=char-length)` — different algorithm by design, same size semantics (characters). |
| embed | `HuggingFaceEmbedding` | Same model string, `device=cpu`, 384-dim. |
| response | `ProcessVideoResponse` (JSON) | Full field list in §3 — workload plus per-response read-backs. |

### Where the arms genuinely differ

1. **Serving topology**: engine task subprocesses addressed by token, vs a
   uvicorn worker pool addressed by the kernel. (Physically the same shape —
   §4.)
2. **Transport**: persistent websocket + task tokens, vs one HTTP request per
   video.
3. **Splitter algorithm**: LangChain `RecursiveCharacterTextSplitter` vs
   LlamaIndex `SentenceSplitter` — both at 4000/200 characters. Chunk *hashes*
   are therefore per-arm truths; the cross-arm truths are characters conserved
   and detections agreeing.
4. **Response richness**: LlamaIndex returns per-frame/per-chunk read-backs
   directly; on RocketRide the equivalents are **recovered client-side from
   the returned chunk text** (the chunks *contain* the per-frame JSON — see
   §2), which is proven exact for counts, labels, and scores.
5. **Failure identity**: the engine silently falls back to a different model
   if rfdetr cannot import; the LI arm refuses to serve instead. Both arms are
   protected the same way — per-run identity read-backs, not trust.

Everything else — weights, packages, ffmpeg, sampling interval, threshold,
embedder, split size — is pinned identical and verified per run (§5).

---

## 2. Where every measurement is taken

Every number in an export comes from exactly one of the sources below. A
reviewer holding any export field can find its origin here; the export's
`provenance_video` block names the read-back values recorded for that run.

| Source | Read how | Fields it produces |
|---|---|---|
| **Manifest** (`ami_video_manifest.jsonl`) | loaded at preflight; corpus bytes re-hashed against it | `video_s_manifest`, `expected_frames` (duration ÷ 15 arithmetic), measured/warm roles, corpus sha256s, `manifest_sha256` |
| **The records** (driver-stamped per video) | stamps taken in the driver at submit and response; contents computed from the returned payload | `enqueue_ns`/`admit_ns`/`done_ns`, `wall_s` (= done − admit), `submitted_sha256`, `bytes`; `n_chunks`, `chunk_chars`, `chunk_sha256`, `sum_chunk_chars`; RR `frames_observed` (overlap-stripped bracket count over chunk text, cross-checked by an independent JSON decode — `frame_count_methods_agree`), LI `frames_observed` (extractor count); `frame_label_multisets` + `frame_scores` (RR: recovered from chunk JSON; LI: response fields); `embed_dim`; `embedding_norms` (RR: computed by the driver from returned vectors; LI: computed in the worker, carried in the response); `token_index` (RR), `serving_pid` + `stage_s` (LI) |
| **Derived from records at export** | pure arithmetic over the record file | throughput blocks, `steady_window` (in-flight reconstruction from admit/done stamps, with `window_n`), `latency_normalized` (= `wall_s` ÷ minutes of `video_s_manifest`), `wall_s_order_stats` |
| **Container cgroup** (`docker exec cat /sys/fs/cgroup/…`) | the container's *own* accounting, never the driver's | collector samples every 0.5 s during a leg (CPU `usage_usec`, memory — the utilization denominators and per-arm memory); `preleg_container_idle_cores` (quiet-box baseline); probe per-send CPU/`memory.peak`/anon/io deltas; idle-at-M / idle-at-W |
| **Inside the serving process** | RR: the `env_probe` node attached to a generated variant of the measured pipe — read in the *same kind of task process* that serves; LI: `/health` per worker pid, plus every response | the six thread variables as the process sees them, `torch_num_threads`, torch/rfdetr/package versions, `python_version` + executable (the embedded 3.12.13 on RR), rfdetr import predicate (RR), `detect_impl` + `model_names` (LI) |
| **Docker inspect** (declared side) | `docker inspect` | declared thread env (compared against in-process measured — never merged), image labels (patch identity), `NetworkMode` (must read `host`; recorded), container root pid (collector anchor) |
| **The host** | `os.getloadavg()`, collector system ticks | `preleg_load1`, `preleg_foreign_excess` (= load1 − container idle baselines), in-run load series |
| **Process census** (`docker exec ps` + `/proc/<pid>/stat`) | counting and CPU-delta attribution | task-subprocess census (M tokens declared ⇒ M new task processes measured, fail-closed), serving-instance proof in the probes (which pids actually burned CPU) |
| **In-container artifacts** | `find`+`md5sum`, dist-info listing, `pip freeze` | rf-detr-base.pth md5 vs the pinned registry value (both arms, per run), baked package versions (bake read-back), `li_image_freeze.txt` (the LI image's full resolved stack, per run) |
| **The wire itself** | a real SDK `connect()` / `/health` round-trip | `ready_wall_s` (container readiness), probe `use()` wall times |

Two rules visible throughout: **declared and measured values are recorded
separately and compared, never merged** (thread env is the canonical case);
and where one arm cannot measure something, the field is `null`/absent with
its reason — never imputed (RR has no client-visible `stage_s`; LI has no
`token_index`).

---

## 3. The wire contract

### RocketRide

Submitted: `use(filepath=<generated pipe>, ttl=7200[, threads=N])` →
`{'token': …}` once per serving instance; then per video
`send(token, avi_bytes, objinfo={'name': <file>}, mimetype='video/x-msvideo')`.
Credentials ride in the environment (`ROCKETRIDE_URI`, `ROCKETRIDE_APIKEY`),
resolved and fingerprinted by the harness — never inline. Every token is
`terminate()`d before disconnect.

Returned: `{'documents': [{page_content: <chunk text>, embedding: [384
floats], metadata: {chunkId: int}}, …]}`. The read-backs **ride inside the
payload**: chunk text *is* the concatenated per-frame detection JSON, so frame
count, per-frame label multisets, and scores are recovered exactly from what
came back; `chunkId` ordering proves accumulate-then-split; vector norms are
recomputed driver-side. Probe-only pipe variants add extra response lanes
(`envprobe` text, `frames` documents) without touching the measured pipe.

### LlamaIndex

Submitted: `POST /process_video`, `Content-Type: application/octet-stream`,
body = the same bytes.

Returned (`ProcessVideoResponse`): workload — `n_frames`, `n_detections`,
`detections_per_frame`, `total_chars`, `n_chunks`, `chunk_chars`,
`chunk_sha256`, `embed_dim`, `embedding_norms`, `frame_labels`,
`frame_scores`, `frame_png_sha16`; timings — `stage_s`
(extract/detect/split/embed), `wall_s`; identity riding on **every response**
— `pid`, `detect_impl`, `model_names`, `torch_num_threads`, `versions`.
`GET /health` adds per-worker warm state (`warm`, `warm_workers`,
`declared_workers`), `python_version`, the six-variable `thread_env`, and the
splitter's declared semantics (`split_unit`, `chunk_size`, `chunk_overlap`,
`interval_s`). Errors return `{error, pid, detail}` — attributed, never
silent.

---

## 4. The two postures, as dataflow

**Default (1 token):** one `use()` ⇒ the engine spawns **one task
subprocess** holding one RF-DETR instance, one embedder, one device lock. The
task's internal worker pool (engine default: 64 threads) can admit many videos
concurrently, but every detection passes through the single lock — physically,
a serial detection queue behind a wide front door.

**Parity (M tokens):** M `use()` calls, each loading its own generated pipe
(distinct `project_id` — the engine derives task identity from it) ⇒ **M task
subprocesses**, M model instances, M locks ⇒ M-way detection parallelism, at
the cost of M copies of the models in memory. The driver round-robins videos
across tokens (`token_index` in every record). Two proofs run before any
number is produced: the process census (M new task subprocesses, counted
inside the container) and warm-up coverage (every token observed serving).

**LlamaIndex (W workers)** is the same physical shape as parity: W OS
processes, each one model behind one lock, with the kernel doing the routing
instead of the driver — proven per run by distinct response pids plus
per-process CPU deltas.

So the comparison is: *one process with a wide intake* (default) vs *N
processes* (parity / workers). Nothing else changes between postures — same
pipe content, same corpus, same order, same gates.

---

## 5. What could make these arms incomparable — and what stops it

| Divergence risk | Pinned by | Measured per run by |
|---|---|---|
| Different detector weights | one artifact: `rf-detr-base.pth`, registry md5 | md5 of the file **inside both containers** checked against the pinned constant |
| Different package versions | `engine_pins.txt` extracted *from the rr image* and installed identically in the LI image and the probe floor | in-process `versions` (env_probe / every LI response), bake dist-info listing, `li_image_freeze.txt` for the LI serving stack |
| Different interpreters | — (not assumed equal) | read back per run: engine-embedded CPython from inside the task process; LI `python_version` from `/health`; recorded as declared values |
| Different frame extraction | same imageio-ffmpeg pin ⇒ byte-identical ffmpeg; identical filter string | per-video frame census vs manifest expectation on both arms; PNG byte-identity (`frame_png_sha16`) proven at probe scope |
| Different detection behaviour | same weights, threshold, input frames | strict per-frame **label multiset equality** across arms (staged on one video at the probe, then armed for runs); black-fixture null control |
| Different text workload after splitting | both splitters at 4000/200 characters | char conservation ±2% (sum of chunk chars per video, RR vs LI); chunk-count ratio reported |
| Different embedding | same model string both arms | dim == 384 and unit-norm (±1e-3) gates on every vector, both arms |
| Environment drift (threads, network, load, task topology) | container env + `--network host` on both arms | declared-vs-measured thread values per arm; `NetworkMode` read back; quiet-box foreign-excess values; task census + `project_id` uniqueness; SDK surface verified at preflight |

The chain has no trusted link: every row's right-hand column is something
*read from the running system*, not from configuration. Where a link cannot
be verified for a given leg, the corresponding gate reports NOT RUN rather
than passing — the verdict vocabulary, and the reasons behind each choice,
are in `samples/README.md`.
