#!/usr/bin/env python3
"""Phase 2 video driver — one arm per invocation, both RR postures from one code path.

APPROVED DESIGN (2026-08-20):
  * Crossroad 9: RocketRide runs at BOTH postures, labelled side by side —
      default: 1 token, threads UNSET (engine default = CONST_DEFAULT_MAX_THREADS
               = 64, constants.py:48 — a serial detection queue with 63 waiters,
               because detect inference is under one process-local threading.Lock
               per pipeline instance);
      parity:  M tokens (M = LlamaIndex worker count unless overridden), giving
               RocketRide M independent detector instances.
    One Posture dataclass, one submit path; the posture only changes how many
    use() tokens exist and what threads= is passed. Neither posture alone is
    publishable.
  * Workload parity is MEASURED (gates_shared.char_conservation_parity, ±2% on
    sum-of-chunk-chars), chunk-count ratio reported unguarded, provenance
    chunk_size/chunk_overlap populated FROM RECORDS.
  * Arms run ONE AT A TIME: this driver refuses to drive both in one process.

Discipline carried (each with its Phase 1 defect number):
  #29 both stamps per item (enqueue_ns before admission, admit_ns inside),
      identical code path for both arms and both legs;
  #27 jsonl_stream append+flush per record, resume via read_completed;
  #37 thread pins read back from INSIDE the task process (RR: env_probe
      attached to a GENERATED variant of the measured pipe — a3_env_torch
      pattern; LI: /health per worker pid) and checked by ONE function fed by
      both arms (gates_shared.thread_pin_parity), absence fails first;
  #34 utilisation denominators come from the container's own cgroup (collector);
  #32 ttl=0 on measured legs (Crossroad 43: the 7200 idle reaper killed the
      default blast; any finite ttl is a movable cliff) + unconditional
      retry-then-escalate terminate + K=3 consecutive-failure breaker;
  #38 a gate over a leg that did not run reports NOT RUN; a leg that ran and
      produced zero records is a FAIL;
  #21-class: LI warm-up must OBSERVE every declared worker pid serving before
      the measured leg (kernel accept routing is not round-robin).

Run (box):
    python3 working/video/driver_video.py --arm rocketride --posture default \
        --leg sequential --n 5 --out-dir working/video/results/<run>
    python3 working/video/driver_video.py --cross RR.jsonl LI.jsonl
HELD: the run plan (n values, blast concurrency, parity threads) — this file
takes them as arguments and refuses to invent them.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import resource
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'working'))
sys.path.insert(0, str(ROOT / 'working' / 'video'))
sys.path.insert(0, str(ROOT / 'working' / 'video' / 'probe'))

from harness import gates_shared as gs                 # noqa: E402
from harness import provenance_leela as pvl            # noqa: E402
from harness import rr_credentials                     # noqa: E402
from harness.jsonl_stream import JsonlWriter, read_completed  # noqa: E402
import sdk_identity                                    # noqa: E402
from argtypes import bounded_float, positive_int, run_id  # noqa: E402 — entry 8
from corpus_locator import resolve_corpus_dir                # noqa: E402 — 2026-08-23
import lifetime_state                                        # noqa: E402 — 2026-09-06 fs-vs-process discriminator
# One census, one minter — the probes' own functions (stdlib-only module):
# the driver and probe_rr must count task processes and stamp project_ids the
# same way, or 'declared==measured' means different things per tool.
from probe_rr import fresh_project_pipe, task_process_census  # noqa: E402

PIPE_PATH = ROOT / 'working' / 'video' / 'benchmark_video_detect.pipe'
MANIFEST_DEFAULT = ROOT / 'working' / 'video' / 'ami_video_manifest.jsonl'
GENERATED_DIR = ROOT / 'working' / 'pipes' / 'generated'
EMBED_MODEL = 'sentence-transformers/multi-qa-MiniLM-L6-cos-v1'

# LI per-request ceiling, SIZED FOR THE 500 CORPUS (2026-09-03; was 7200).
# A per-request timeout must bound QUEUE + SERVICE, and in kernel-accept
# modes a queued film's wall can approach the whole leg span. Measured
# bases: our films-35 per-film maxima 11.7 (LI 16x2) / 8.2 (RR 16x2) /
# 27.5 (RR default) s per film-minute; the 500 corpus's longest film is
# 11,314 s = 188.6 min (Leela's committed films500 per_doc @3967d9f4,
# whose own max observed wall was 2,332 s at c32). Projections: LI 16x2
# worst film ~2.2 ks (7200 already held 3.3x); an LI-DEFAULT 500 blast's
# queue-wait can reach the leg span, ~6.4 h at a pessimistic 7 f/s ->
# 7200 and 14400 both breachable hours into a leg. 43200 = ~2x that worst
# projected span, ~20x the 16x2 worst film, and half Leela's 86,400
# whole-run envelope — kills true hangs within half a day, never a legit
# slow request. Single source: the urlopen call AND the provenance
# timeout_s record read this constant.
LI_HTTP_TIMEOUT_S = 43200
BREAKER_K = 3
THREAD_KEYS = ('OMP_NUM_THREADS', 'MKL_NUM_THREADS', 'OPENBLAS_NUM_THREADS',
               'VECLIB_MAXIMUM_THREADS', 'NUMEXPR_NUM_THREADS', 'TORCH_NUM_THREADS')


def say(msg: str) -> None:
    print(f'[driver] {msg}', flush=True)


def sha256_file(path: Path, chunk: int = 1 << 20) -> str:
    """Streaming file hash — the submitted-sha source since the streaming
    refactor (2026-08-27): the driver never holds a whole blob (blocker 2),
    so the sha comes from a chunked pass over the file. Run off the event
    loop; the pass also warms the page cache, so the streamed send that
    follows reads mostly from cache and wall_s keeps its admit->done meaning."""
    h = hashlib.sha256()
    with open(path, 'rb') as fh:
        while True:
            b = fh.read(chunk)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


# ---------------------------------------------------------------------------
# Posture — Crossroad 9, one code path
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Posture:
    name: str                 # 'default' | 'parity' (RR); 'workers' (LI, informational)
    tokens: int               # RR use() count; LI: declared workers (read back, not set here)
    threads: Optional[int]    # RR use(threads=); None = UNSET (engine default 64)

    def label(self) -> str:
        # ARM-AWARE (2026-08-22). 'workers' is the LlamaIndex arm, where this
        # dataclass is bookkeeping only: there is no use(threads=) and no
        # engine default of 64, so rendering RR vocabulary there states
        # something false about the arm being described.
        if self.name == 'workers':
            return f'workers[declared_workers={self.tokens}]'
        t = 'unset(engine-default-64)' if self.threads is None else str(self.threads)
        return f'{self.name}[tokens={self.tokens},threads={t}]'


def threads_env_expectation(name: str):
    """argparse type for the EXPECTED six-variable thread env on the RR
    container for one leg (ruling 2026-08-21): a positive int — the parity
    posture's measured optimum — or the literal 'unset' — the default posture,
    where the run declares nothing and the engine/library default is what a
    user gets. Read back declared (docker inspect) and in-process (envprobe),
    fail-closed, in preflight. Never implied by which posture is running."""
    as_int = positive_int(name, 256)

    def conv(raw: str):
        if raw == 'unset':
            return 'unset'
        return as_int(raw)
    return conv


def at_a_glance_line(export: Dict[str, Any]) -> str:
    """ONE line that makes throughput and the idle burden legible together
    (ruling 2026-08-21: M is set on measured throughput and the idle cost is
    reported BESIDE it, never subtracted — concealing it is the dishonest
    part). Built from the export itself so the sample and the box agree by
    construction; first key of every export and the last stdout line."""
    thr = export.get('throughput') or {}
    eff = export.get('efficiency') or {}
    burden = eff.get('idle_burden') or {}
    win = thr.get('steady_window') or {}
    gates = export.get('gates') or {}
    verdicts = [g.get('PASS') for g in gates.values() if isinstance(g, dict) and 'PASS' in g]
    n_pass = sum(1 for v in verdicts if v is True)
    n_fail = sum(1 for v in verdicts if v is False)
    n_notrun = sum(1 for v in verdicts if v is None)
    posture = (export.get('provenance_video') or {}).get('posture') or {}
    t_exp = posture.get('threads_env_expected')
    t_meas = posture.get('threads_env_in_process_torch')
    window = (f', steady window {win.get("window_frames_per_s")} frames/s (n={win.get("window_n")})'
              if win.get('defined') else ', steady window undefined')

    def pct(x):
        return f'{x:.1%}' if isinstance(x, (int, float)) else 'n/a'
    # Counts as recorded, no arithmetic: n_records includes any determinism-
    # repeat record on sequential legs, so a derived "ok/offered" would
    # read 6/5 and invite a false alarm.
    return (f"{export.get('arm')} {export.get('posture')} {export.get('leg')} "
            f"pass {export.get('pass')} "
            f"records {export.get('n_records')} (errors {export.get('n_errors')}) / "
            f"offered {export.get('n_offered')}"
            f" | THROUGHPUT {thr.get('total_frames_per_s')} frames/s "
            f"({thr.get('total_realtime_factor')}x realtime){window}"
            f" | SERVICE CPU {eff.get('effective_cores')} cores = {pct(eff.get('cpu_util_of_box'))} "
            f"of {eff.get('box_cpus')}"
            f" | IDLE BURDEN {burden.get('idle_cores_with_instances_live')} cores with "
            f"{burden.get('instances')} {burden.get('instance_kind')} live = "
            f"{pct(burden.get('idle_share_of_box'))} of the box before any work "
            f"(beside, never subtracted)"
            f" | thread env expected {t_exp} / in-process torch {t_meas}"
            f" | gates PASS {n_pass} · NOT RUN {n_notrun} · FAIL {n_fail}"
            f" | efficiency valid={eff.get('valid')}"
            f" | COLLECTOR {str(export.get('collector_status', 'unknown')).split(':')[0]}"
            + (f" | BOUNDARY-EXCLUDED {export['boundary_exclusions_total']} frames"
               if export.get('boundary_exclusions_total') else ""))


# ---------------------------------------------------------------------------
# Manifest
# ---------------------------------------------------------------------------

def load_manifest(path: Path) -> tuple[dict, List[dict]]:
    rows = [json.loads(l) for l in path.read_text().splitlines() if l.strip()]
    meta = rows[0].get('_meta', {}) if rows and '_meta' in rows[0] else {}
    return meta, [r for r in rows if '_meta' not in r]


def expected_frames(row: dict, interval_s: int = 15) -> Optional[int]:
    """Crossroad 23 (2026-08-21): the expectation is a MEASURED manifest
    column, never arithmetic. The old formula floor(d/15)+1 predicted 84
    where the arms' ffmpeg emitted 83 (the t=1245 slot never fires on a
    1248.3 s stream) — the duration was measured, the frame count was not.
    fetch_ami_video --build-manifest measures fps=1/15 through the same
    imageio-ffmpeg binary the arms use, per row. No fallback formula here by
    ruling: a manifest without the column predates the ruling and fails
    loudly. (interval_s kept for signature stability; the measurement fixed
    the interval at build time.)"""
    v = row.get('expected_frames_measured')
    if v is None:
        raise SystemExit(
            f"NOT DONE — manifest row {row.get('file')!r} lacks "
            "'expected_frames_measured': the manifest predates Crossroad 23. "
            'Re-cut with fetch_ami_video.py --build-manifest (measures fps=1/15 '
            "through the arms' own ffmpeg; ~12 min for 60 rows).")
    return int(v)


def verify_corpus(rows: List[dict], corpus_dir: Path) -> List[str]:
    bad = []
    for r in rows:
        p = corpus_dir / r['file']
        if not p.exists():
            bad.append(f"{r['file']}: missing")
        elif p.stat().st_size != r['bytes']:
            bad.append(f"{r['file']}: size {p.stat().st_size} != {r['bytes']}")
    return bad


# ---------------------------------------------------------------------------
# Record derivation — one shape, both arms
# ---------------------------------------------------------------------------

def frames_from_chunks(contents: List[str], max_k: int = 400) -> int:
    """Count frames from returned chunks, stripping the splitter's overlap.

    For each adjacent pair, drop the LONGEST prefix of the next chunk that is
    a suffix of the previous one (the text LangChain's 200-char overlap window
    duplicated — always whole short pieces), then count '[' over the join.
    max_k bounds the search above the overlap size; min match is 1 char
    because real duplicated pieces can be as short as '[]' (measured k=2).
    """
    if not contents:
        return 0
    parts = [contents[0]]
    for prev, cur in zip(contents, contents[1:]):
        k_found = 0
        for k in range(min(max_k, len(prev), len(cur)), 0, -1):
            if prev.endswith(cur[:k]):
                k_found = k
                break
        parts.append(cur[k_found:])
    return ''.join(parts).count('[')


def frame_arrays_from_chunks(contents: List[str], max_k: int = 400) -> Optional[List[list]]:
    """Per-frame detection ARRAYS from returned chunks: overlap-strip join,
    then sequential json raw_decode (arrays are self-delimiting, so seams that
    ate '\n' separators do not matter). Verified exact — counts, label
    multisets AND scores — across six real-shaped scenarios under engine-real
    4000/200 splits (2026-08-20). Returns None on any decode failure: an
    unparseable stream is reported, never guessed at."""
    if not contents:
        return []
    parts = [contents[0]]
    for prev, cur in zip(contents, contents[1:]):
        k_found = 0
        for k in range(min(max_k, len(prev), len(cur)), 0, -1):
            if prev.endswith(cur[:k]):
                k_found = k
                break
        parts.append(cur[k_found:])
    blob = ''.join(parts)
    dec = json.JSONDecoder()
    arrays, i, n = [], 0, len(blob)
    try:
        while i < n:
            while i < n and blob[i] in ' \t\r\n':
                i += 1
            if i >= n:
                break
            obj, end = dec.raw_decode(blob, i)
            if not isinstance(obj, list):
                return None
            arrays.append(obj)
            i = end
    except json.JSONDecodeError:
        return None
    return arrays


def record_from_rr(result: dict) -> dict:
    docs = (result or {}).get('documents') or []
    contents = [d.get('page_content') or '' for d in docs]
    lens = [len(c) for c in contents]
    hashes = [sha256_bytes(c.encode()) for c in contents]
    ids = [(d.get('metadata') or {}).get('chunkId') for d in docs]
    n = len(docs)
    arrays = frame_arrays_from_chunks(contents) if n else []
    # gs.whole_list_doubled: True = defect signature, False = clean, None =
    # indeterminate (uniform content — a static scene can produce identical
    # chunks organically; never folded into PASS or FAIL).
    doubled = gs.whole_list_doubled(hashes)
    return {
        'n_chunks': n,
        'chunk_chars': lens,
        'chunk_sha256': hashes,
        'sum_chunk_chars': sum(lens),
        # Frame read-back (overlap-aware). The detection schema has no nested
        # arrays, so '[' occurs once per frame's JSON — but the engine's
        # splitter runs at LANGCHAIN LIBRARY DEFAULTS 4000/200 (its own size
        # config is stripped by _filter_kwargs_for; proven 2026-08-20 against
        # box records: means ~3400, max 3993), and overlap DUPLICATES short
        # trailing pieces into the next chunk. frames_from_chunks strips the
        # duplicated suffix/prefix before counting; verified exact at 84 and
        # 250 frames under real 4000/200 splits. Residual ambiguity: runs of
        # byte-identical short frames straddling a boundary (content cannot
        # distinguish overlap-copy from real neighbour) — absent on real
        # footage; if it occurs the census FAILS loudly, never clamps.
        'frames_observed': frames_from_chunks(contents) if n else None,
        'frames_observed_naive_upper_bound': sum(c.count('[') for c in contents) if n else None,
        'frames_observed_method': 'bracket-count-overlap-stripped',
        # Gate-3 inputs, recovered from the measured response itself (proven
        # exact): per-frame label multisets + scores; rawdecode count is the
        # independent second method — disagreement with the bracket count is
        # flagged, never averaged.
        'frames_observed_rawdecode': (len(arrays) if arrays is not None else None),
        'frame_count_methods_agree': (arrays is not None and len(arrays) == frames_from_chunks(contents)) if n else None,
        'frame_label_multisets': ([sorted(str(d.get('label')) for d in fr) for fr in arrays]
                                  if arrays is not None else None),
        'frame_scores': ([[float(d.get('score', 0.0)) for d in fr] for fr in arrays]
                         if arrays is not None else None),
        'embed_dim': (len(docs[0].get('embedding') or []) or None) if n else None,
        'embedding_norms': ([round(sum(x * x for x in (d.get('embedding') or [])) ** 0.5, 6)
                             if d.get('embedding') else None for d in docs] if n else None),
        'chunkid_monotone': all(isinstance(i, int) for i in ids) and ids == sorted(ids),
        'whole_list_doubled': doubled,
        'n_detections': None,      # not recoverable client-side on this arm; honest None
        'stage_s': None,
        'serving_pid': None,
    }


def record_from_li(body: dict) -> dict:
    return {
        'n_chunks': body.get('n_chunks'),
        'chunk_chars': body.get('chunk_chars'),
        # Locus ruling 2026-08-25: hash the returned TEXTS here, driver-side,
        # post-response — the same place and the same formula
        # (sha256_bytes(text.encode())) as record_from_rr. Values are identical
        # to the banked in-service hashes by construction (same strings), so
        # gate 3/8 and whole_list_doubled consume unchanged values. Old-image
        # responses (no 'chunks') fall back to their in-wall hashes and say so.
        'chunk_sha256': ([sha256_bytes(c.encode()) for c in body['chunks']]
                         if body.get('chunks') is not None else body.get('chunk_sha256')),
        'hashing_locus': (body.get('hashing_locus') or
                          ('in_service_in_wall' if body.get('chunk_sha256') else None)),
        'sum_chunk_chars': sum(body.get('chunk_chars') or []),
        'frames_observed': body.get('n_frames'),
        'frames_observed_method': 'extractor-count',
        'chunkid_monotone': True,   # LI chunks arrive ordered by construction
        'whole_list_doubled': gs.whole_list_doubled(
            [sha256_bytes(c.encode()) for c in body['chunks']]
            if body.get('chunks') is not None else (body.get('chunk_sha256') or [])),
        'n_detections': body.get('n_detections'),
        'detections_per_frame': body.get('detections_per_frame'),
        'frame_label_multisets': body.get('frame_labels'),
        'frame_scores': body.get('frame_scores'),
        'embed_dim': body.get('embed_dim'),
        'embedding_norms': body.get('embedding_norms'),
        'stage_s': body.get('stage_s'),
        'serving_pid': body.get('pid'),
        'stage_s_semantics': body.get('stage_s_semantics'),
    }


# ---------------------------------------------------------------------------
# Arms — submit_one is THE single code path both arms and both legs share
# ---------------------------------------------------------------------------

class RRArm:
    name = 'rocketride_video'

    def __init__(self, port: int, posture: Posture, pipe_path: Path):
        self.port = port
        self.posture = posture
        self.pipe_path = pipe_path
        self.client = None
        self.tokens: List[str] = []
        self.project_ids: List[str] = []
        self._rr = 0

    async def start(self):
        # Measured surface (Phase 1's 40+ sites + the installed wheel's
        # signature paste, 2026-08-21): RocketRideClient BARE — credentials via
        # the harness resolver (env route, loopback-strict, provenance of the
        # source). The CLI port is operator intent, so it overrides env.
        from rocketride import RocketRideClient
        os.environ['ROCKETRIDE_URI'] = f'http://127.0.0.1:{self.port}'
        rr_credentials.resolve(strict=True)
        self.client = RocketRideClient()
        await self.client.connect(timeout=60000)
        try:
            for i in range(self.posture.tokens):
                # D3: one generated pipe with a FRESH project_id per token — the
                # engine derives the task token from (userId, project_id, source)
                # (task_server.py:1074), so M use() calls on the measured pipe's
                # fixed id are ONE task ('Pipeline is already running.' loudly,
                # or one shared instance silently). The census in amain proves
                # M distinct task processes; config is never the evidence.
                path, project_id = generate_task_pipe(f'{self.posture.name}-tok{i}')
                # CROSSROAD 43 (2026-08-24): ttl=0 = "no timeout, run until
                # explicitly stopped" (engine-documented; idle reaper is
                # task_server.py:331,365 — an IDLE timer, and it killed the
                # default-blast leg when the token crossed 2h). Any finite ttl
                # just moves the cliff: a 2.7 h serial blast crosses 7200 too.
                # The pairing obligation is stop() in the leg's finally — with
                # ttl=0 there is NO reaper behind a failed terminate, so stop()
                # retries and escalates loudly instead of shrugging.
                kwargs: Dict[str, Any] = dict(filepath=str(path), ttl=0)
                if self.posture.threads is not None:
                    kwargs['threads'] = self.posture.threads
                started = await self.client.use(**kwargs)
                self.tokens.append(started['token'])
                self.project_ids.append(project_id)
            sdk_identity.assert_unique_project_ids(
                [(f'tok{i}', p) for i, p in enumerate(self.project_ids)])
        except BaseException:
            await self.stop()   # a half-built token set must not outlive the failure
            raise
        say(f'RR: {len(self.tokens)} token(s) live, posture {self.posture.label()}, '
            f'{len(set(self.project_ids))} distinct project_id(s)')
        say('RR write path: chunked 1 MiB per write request (send_files shape, '
            'data.py:551; whole-frame single-message path retired 2026-08-24 — '
            'DIAG_M1_BLAST)')

    def _next_token(self) -> tuple[int, str]:
        i = self._rr % len(self.tokens)
        self._rr += 1
        return i, self.tokens[i]

    # 1 MiB — send_files' fixed chunk size (rocketride/mixins/data.py:551), the
    # shape PROVEN on this exact corpus by Leela's aws_videobench arm. Adopted
    # 2026-08-24 after DIAG_M1_BLAST: our send() wrote each video as ONE
    # ~248 MB DAP message; 16 of those on the shared websocket killed the
    # connection at every C tried (16, and 4). Chunks interleave fairly, so
    # pongs, responses and other sends' chunks slot between them.
    WRITE_CHUNK = 1024 * 1024

    async def process(self, path: Path, name: str) -> dict:
        idx, token = self._next_token()
        # Same primitives send() uses (pipe/open/write/close — data.py:405,
        # cleanup shape data.py:466-478), same PIPELINE_RESULT from close(),
        # same objinfo shape (_objinfo_with_size: {'name', 'size'}); write
        # granularity is N x 1 MiB requests, and since the streaming refactor
        # (Ruling 4, 2026-08-27) each chunk is READ FROM DISK per write — the
        # SDK needs bytes per chunk only (data.py:231-244) and the driver
        # never holds a whole blob. Above the 250 MiB message ceiling
        # (register entry 24) this is the only admissible upload.
        size = Path(path).stat().st_size
        # Ruling T item 7 (2026-08-31): mime from the file, not a hardcoded
        # x-msvideo — the .mp4 films corpus was mislabeled on the wire and in
        # provenance. Engine routing keys on the 'video/' prefix, so the
        # fallback stays the historical label: behavior is byte-identical for
        # every non-.mp4 input, and .mp4 now carries its true type.
        mime = {'.mp4': 'video/mp4'}.get(Path(name).suffix.lower(),
                                         'video/x-msvideo')
        pipe = await self.client.pipe(token, {'name': name, 'size': size},
                                      mime)
        await pipe.open()
        n_chunks = 0
        try:
            with open(path, 'rb') as fh:
                while True:
                    chunk = fh.read(self.WRITE_CHUNK)
                    if not chunk:
                        break
                    await pipe.write(chunk)
                    n_chunks += 1
            result = await pipe.close()
        except Exception:
            if pipe.is_opened:
                try:
                    await pipe.close()
                except Exception:  # noqa: BLE001 — cleanup mirrors send()'s
                    pass
            raise
        rec = record_from_rr(result)
        rec['token_index'] = idx
        rec['write_path'] = f'chunked-1MiB x {n_chunks}'
        rec['upload_source'] = 'file-streamed'
        return rec

    async def stop(self):
        if not self.client:
            return
        # Phase 1 pattern: terminate BEFORE disconnect, per token, contained.
        # Not optional (ruling 2026-08-21) — and STRICTER under Crossroad 43:
        # tokens are ttl=0 now, so NO reaper stands behind a failed terminate.
        # A leaked ttl=0 task idle-spins ~1 core (Ticket 4) FOREVER, inside the
        # same cgroup the collector reads for the next leg's utilization
        # denominators (run_plan keeps rr up across a posture's legs). So:
        # retry once with a longer deadline, and if the token still cannot be
        # terminated, say exactly what leaked and what it poisons — a quiet
        # leak here is a corrupted next leg, not a tidiness issue.
        for tok in self.tokens:
            last_exc = None
            for attempt, deadline in ((1, 120), (2, 300)):
                try:
                    await asyncio.wait_for(self.client.terminate(tok), timeout=deadline)
                    last_exc = None
                    break
                except Exception as exc:  # noqa: BLE001 — retried, then escalated
                    last_exc = exc
                    say(f'terminate {str(tok)[:16]} attempt {attempt}: {exc!r}')
            if last_exc is not None:
                say(f'WARNING — token {str(tok)[:16]} could NOT be terminated and is ttl=0: '
                    f'a task process may be running INDEFINITELY in the rr container, '
                    f'burning ~1 idle core inside the cgroup the next leg measures. '
                    f'Verify before the next leg: docker exec rr ls /proc | grep -c "^[0-9]" '
                    f'(and compare the task census); a container restart clears it.')
        self.tokens = []
        try:
            await self.client.disconnect()
        except Exception as exc:  # noqa: BLE001
            say(f'disconnect: {exc!r} (recorded)')
        self.client = None


class LIArm:
    name = 'llamaindex_video'

    # BALANCED MODE (ruling 2026-08-25, LI_SERVING_SKEW.md): several
    # single-worker instances on distinct ports, and THE DRIVER round-robins
    # ports per send — the structural twin of RR token round-robin, replacing
    # kernel accept (which skewed one worker to 48 of 168 videos). One port =
    # the historical default posture; both go through the same code.

    def __init__(self, ports):
        self.ports = [ports] if isinstance(ports, int) else list(ports)
        self.port = self.ports[0]           # compat: single-port callers
        self._rp = 0
        self.declared_workers: Optional[int] = None

    def _next_port(self) -> int:
        p = self.ports[self._rp % len(self.ports)]
        self._rp += 1
        return p

    async def health_of(self, port: int) -> dict:
        import urllib.request
        return await asyncio.to_thread(
            lambda: json.load(urllib.request.urlopen(
                f'http://127.0.0.1:{port}/health', timeout=30)))

    async def health(self) -> dict:
        """Aggregate across instances: warm_workers/declared_workers SUM, so the
        Crossroad-41 marker gate and the census work unchanged in both modes."""
        docs = [await self.health_of(p) for p in self.ports]
        agg = dict(docs[0])
        agg['warm_workers'] = sum(int(d.get('warm_workers') or 0) for d in docs)
        agg['declared_workers'] = sum(int(d.get('declared_workers') or 0) for d in docs)
        agg['per_port'] = {p: {'warm_workers': d.get('warm_workers'),
                               'declared_workers': d.get('declared_workers'),
                               'pid': d.get('pid')} for p, d in zip(self.ports, docs)}
        return agg

    async def start(self):
        health = await self.health()
        self.declared_workers = health.get('declared_workers')
        if len(self.ports) > 1:
            bad = {p: v for p, v in health['per_port'].items()
                   if int(v.get('declared_workers') or 0) != 1}
            if bad:
                raise SystemExit(
                    f'NOT DONE — balanced mode expects SINGLE-worker instances; '
                    f'ports declaring != 1 worker: {bad}. 8 ports x W=8 would be 64 '
                    'workers wearing an 8-worker label.')
        say(f'LI: warm_workers={health.get("warm_workers")} '
            f'declared={self.declared_workers} over {len(self.ports)} instance(s) '
            f'{self.ports if len(self.ports) > 1 else ""} '
            f'detect_impl={health.get("detect_impl")}')
        if len(self.ports) > 1:
            say('LI balanced mode: driver round-robins ports per send '
                '(kernel accept replaced — LI_SERVING_SKEW.md ruling)')

    async def process(self, path: Path, name: str) -> dict:
        import urllib.request
        port = self._next_port()
        # Streamed upload (Ruling 4, 2026-08-27): the body is an open FILE
        # with an explicit Content-Length — http.client reads file-likes in
        # blocks, so no whole blob exists driver-side; the service streams
        # the body to its spool (request.stream(), Ruling A).
        size = Path(path).stat().st_size

        def _post():
            with open(path, 'rb') as fh:
                req = urllib.request.Request(
                    f'http://127.0.0.1:{port}/process_video',
                    data=fh, method='POST',
                    headers={'Content-Type': 'application/octet-stream',
                             'Content-Length': str(size)})
                with urllib.request.urlopen(req, timeout=LI_HTTP_TIMEOUT_S) as resp:
                    return json.load(resp)

        body = await asyncio.to_thread(_post)
        if 'error' in body:
            raise RuntimeError(f'LI service error: {body}')
        rec = record_from_li(body)
        rec['serving_port'] = port
        return rec

    async def stop(self):
        pass


# ---------------------------------------------------------------------------
# Read-backs (preflight; fail-closed, absence first)
# ---------------------------------------------------------------------------

def generate_task_pipe(tag: str) -> tuple[Path, str]:
    """Measured pipe + a FRESH project_id, nothing else changed (Phase 1's
    pattern — minimal/rr/client.py, smoke_phase2.py; the why lives on
    probe_rr.fresh_project_pipe). The measured identity stays PIPE_PATH's
    sha256; the per-token project_id is recorded in provenance."""
    cfg = fresh_project_pipe(PIPE_PATH, f'video-{tag}')
    GENERATED_DIR.mkdir(parents=True, exist_ok=True)
    out = GENERATED_DIR / f'video_task_{tag}_{os.getpid()}.pipe'
    out.write_text(json.dumps(cfg, indent=1))
    return out, cfg['project_id']


def generate_envprobe_pipe() -> tuple[Path, str]:
    """Measured pipe + env_probe + response_text (a3_env_torch pattern).
    Same task process as the loaded video nodes, so the rfdetr import predicate
    and the thread pins are read where they matter. Fresh project_id (D3):
    smoke_phase2:318 always re-stamped it; the first video version copied the
    base id, which shares a derived task token with the leg's own use()."""
    base = fresh_project_pipe(PIPE_PATH, 'envprobe')
    base['components'].append({'id': 'envprobe_1', 'provider': 'env_probe', 'config': {},
                               'input': [{'lane': 'text', 'from': 'webhook_1'}]})
    base['components'].append({'id': 'resp_env', 'provider': 'response_text',
                               'config': {'laneName': 'envprobe'},
                               'input': [{'lane': 'text', 'from': 'envprobe_1'}]})
    GENERATED_DIR.mkdir(parents=True, exist_ok=True)
    out = GENERATED_DIR / f'video_envprobe_{os.getpid()}.pipe'
    out.write_text(json.dumps(base, indent=1))
    return out, base['project_id']


# The env_probe response contract (2026-08-22). A field the current node
# emits but a STALE baked node does not is an ABSENT read-back — a broken
# instrument — which must be a different, louder verdict than a field the
# node set to a negative value (rfdetr_import_ok=False = a real import
# failure). `.get()` collapses the two to None, and `None is not True` reads
# absence AS failure today and is one config change from reading it as
# success. Same class as the census blindness, one layer down.
ENVPROBE_SCHEMA_MIN = 2
ENVPROBE_REQUIRED = ('env_probe_schema', 'env', 'torch_num_threads',
                     'rfdetr_import_ok', 'python_version', 'package_versions')


def assert_envprobe_complete(info: dict, source: str) -> None:
    """Absence fails before any value is read (register: absence fails before
    agreement). Raises SystemExit naming the missing fields and the fix; the
    caller may then trust every required key is PRESENT, so a later
    `rfdetr_import_ok is not True` genuinely means False, never absent."""
    if not isinstance(info, dict) or not info:
        raise SystemExit(f'NOT DONE — {source} env_probe returned no data (empty '
                         'response): the node did not run, or the response lane is wrong.')
    missing = [k for k in ENVPROBE_REQUIRED if k not in info]
    ver = info.get('env_probe_schema')
    stale = missing or (isinstance(ver, int) and ver < ENVPROBE_SCHEMA_MIN)
    if stale:
        raise SystemExit(
            f'NOT DONE — {source} env_probe is a STALE INSTRUMENT, not a negative '
            f'read-back: missing {missing or "no keys"}, schema {ver!r} '
            f'(need >= {ENVPROBE_SCHEMA_MIN}); present {sorted(info)}. The node that '
            'ran predates these fields — the baked image carries an old '
            'working/nodes/env_probe. Rebuild rr:patched (docker/Dockerfile.rocketride '
            'COPYs the node) THEN re-bake rr:patched-video, and confirm the node inside '
            'the image matches the repo: '
            "docker run --rm rr:patched-video sh -c 'md5sum "
            "/opt/rocketride/engine/nodes/env_probe/IInstance.py' vs md5sum on the repo file. "
            'A missing field read as a value is one config change from reading as success.')


async def rr_readback(port: int) -> dict:
    # Measured surface (Phase 1 + installed-wheel paste, 2026-08-21).
    from rocketride import RocketRideClient
    os.environ['ROCKETRIDE_URI'] = f'http://127.0.0.1:{port}'
    rr_credentials.resolve(strict=True)
    pipe, project_id = generate_envprobe_pipe()
    client = RocketRideClient()
    await client.connect(timeout=60000)
    token = None
    try:
        started = await client.use(filepath=str(pipe), ttl=600)
        token = started['token']
        result = await client.send(token, 'readback probe',
                                   mimetype='text/plain')
        texts = (result or {}).get('envprobe') or []
        info = json.loads(texts[0]) if texts else {}
    finally:
        if token:
            try:  # terminate: the envprobe task must be GONE before the leg's
                  # own use() and before the census baseline (Ticket 4 + D3)
                await asyncio.wait_for(client.terminate(token), timeout=60)
            except Exception as exc:  # noqa: BLE001
                say(f'envprobe terminate: {exc!r} (recorded; ttl=600 reaps)')
        await client.disconnect()
    info['_envprobe_project_id'] = project_id
    return info


# RULING L (2026-08-30) — the films comparison basis: LI runs 4000/0/chars.
# ONE copy of the expectation (entry 6): the sweep probe imports it from here
# (probe_films_curve.check_li_chunk_config) and the leg preflight checks it
# below (Ruling T item 3, 2026-08-31). The operative value is the image env
# (docker/Dockerfile.llamaindex-video) parsed by li_video/service.py; this
# constant exists so a stale li:video image can never measure a leg.
EXPECTED_LI_CHUNK = {'chunk_size': 4000, 'chunk_overlap': 0,
                     'split_unit': 'chars'}


def li_chunk_mismatches(per_worker: Dict[str, dict]) -> Dict[str, dict]:
    """Workers whose /health chunk config does not read back as RULING L.
    An absent field is ABSENCE, never agreement (register discipline)."""
    return {k: {f: v.get(f) for f in EXPECTED_LI_CHUNK}
            for k, v in per_worker.items()
            if {f: v.get(f) for f in EXPECTED_LI_CHUNK} != EXPECTED_LI_CHUNK}


async def li_readbacks(arm: LIArm, timeout_s: float = 120) -> Dict[str, dict]:
    """Sample /health until every declared worker pid has answered (or timeout —
    which is an ABSENCE failure downstream, never a shrug)."""
    per_worker: Dict[str, dict] = {}
    declared = arm.declared_workers or 0
    deadline = time.monotonic() + timeout_s
    # Multi-instance (balanced mode): pids are per-container namespaces and can
    # collide (single-worker uvicorn serves in-process, often pid 1 everywhere),
    # so worker identity is (port, pid), never pid alone.
    while len(per_worker) < declared and time.monotonic() < deadline:
        for port in arm.ports:
            h = await arm.health_of(port)
            per_worker[f'li_worker_{port}_{h["pid"]}'] = {
            'env': h.get('thread_env') or {},
            'torch_num_threads': h.get('torch_num_threads'),
            'detect_impl': h.get('detect_impl'),
            'python_version': h.get('python_version'),
            'versions': h.get('versions') or {},
            # RULING L read-back inputs (the values the serving process LOADED)
            'chunk_size': h.get('chunk_size'),
            'chunk_overlap': h.get('chunk_overlap'),
            'split_unit': h.get('split_unit'),
        }
    return per_worker


def _total_own_cpu_s() -> float:
    """CPU seconds burned by THIS process and every child it has reaped —
    which includes the corpus verifier, every `docker` CLI call, and the
    collector once stopped."""
    s = resource.getrusage(resource.RUSAGE_SELF)
    c = resource.getrusage(resource.RUSAGE_CHILDREN)
    return s.ru_utime + s.ru_stime + c.ru_utime + c.ru_stime


_CPU_SAMPLES: List[tuple] = [(time.monotonic(), _total_own_cpu_s())]


def own_cores_recent(window_s: float = 60.0) -> float:
    """OUR OWN contribution to load1, as cores, over the last `window_s` —
    the same time constant load1 itself uses (2026-08-22).

    Why this exists: the quiet-box gate subtracted the CONTAINERS' cgroup rate
    and nothing else, so every process of ours on the host — this driver, the
    smoke, `docker` invocations, the console tee, and above all run_plan's
    step 0 `fetch_ami_video.py --verify` (a full-corpus sha256, ~1 core for
    tens of seconds, finishing shortly before the first leg reads load1) —
    registered as FOREIGN load. The gate was measuring our own tail and
    charging it to a hog. Attributing what is ours makes 'foreign' mean
    foreign. Approximation stated plainly: this is CPU-seconds/window, while
    load1 also counts uninterruptible-sleep tasks, so it is a lower bound on
    our contribution and never an exact subtraction."""
    now, cpu = time.monotonic(), _total_own_cpu_s()
    _CPU_SAMPLES.append((now, cpu))
    cutoff, ref = now - window_s, _CPU_SAMPLES[0]
    for sample in _CPU_SAMPLES:
        if sample[0] <= cutoff:
            ref = sample
        else:
            break
    dt = now - ref[0]
    return max(0.0, (cpu - ref[1]) / dt) if dt > 0.5 else 0.0


def _host_cpu_snapshot():
    """(total_ticks, idle_ticks) from /proc/stat's aggregate cpu line, or None
    where unreadable (macOS syntax checks, an unexpected format). idle counts
    idle+iowait: a box blocked on I/O is not a box competing for our cores."""
    try:
        with open('/proc/stat') as fh:
            parts = fh.readline().split()
        if not parts or parts[0] != 'cpu':
            return None
        vals = [int(x) for x in parts[1:]]
        return sum(vals), vals[3] + (vals[4] if len(vals) > 4 else 0)
    except Exception:  # noqa: BLE001 — absence degrades to the load1 basis, recorded
        return None


def quiet_box(containers: List[str], max_foreign: float,
              settle_deadline_s: float = 90.0, sample_s: float = 4.0) -> dict:
    """Is FOREIGN work running on this box RIGHT NOW? One reader for the driver
    and the smoke.

    **load1 is the wrong instrument for that question and this gate used to ask
    it anyway** (found 2026-08-22, before the first multi-leg run). load1 is a
    ~60 s exponentially-damped average, so it reports history, and OUR OWN
    history dominates it: a blast leg runs the box at ~23 of 32 cores, and
    after it ends load1 needs ~150 s to decay under 2.0 (23·e^(−t/60)). The next
    leg's preflight reads it ~15 s later. Legs 2–9 of the campaign would each
    have failed a gate whose whole purpose is catching someone ELSE's hog —
    aborting an 80-minute run at leg two, on a path no dry pass exercises
    because a dry pass has no leg big enough to leave a tail.

    So the gated number is INSTANTANEOUS: host busy cores (from /proc/stat over
    the same window) minus our containers' cgroup rate minus our own process
    tree's rate. No history, no decay, no self-inflicted failure. The
    load1-based figure is still computed and recorded beside it (`foreign_by_load1`)
    because it is what Phase 1 recorded and what caught the 18-Aug hog, and it
    becomes the gate only where /proc/stat cannot be read.

    A snapshot still cannot tell a transient burst from a sustained hog, so a
    first reading over threshold triggers a bounded re-read loop and the record
    carries the SEQUENCE plus a trend — DECAYING / SUSTAINED / RISING.

    A SNAPSHOT CANNOT TELL A TAIL FROM A HOG, so this does not take one. When
    the first reading is over the threshold it re-reads on a bounded settle
    loop and records the sequence: **a decaying tail falls, a hog does not.**
    That trend is the discriminator (load1's time constant is ~60 s, so a
    process killed 40 minutes ago contributes e^-40 ≈ 0 — 'it is still
    decaying' is only ever true of the last minute or two, and now we measure
    it instead of arguing it). Costs nothing on a quiet box: the loop is only
    entered when the gate would otherwise fail."""
    readings: List[dict] = []
    ncpu = os.cpu_count() or 32

    def take() -> dict:
        # ONE window for every source, so the three rates are subtractable.
        running = [c for c in containers
                   if docker_inspect(c, '{{.State.Running}}') == 'true']
        t0 = time.monotonic()
        c0 = {c: container_cpu_usage_usec(c) for c in running}
        h0, o0 = _host_cpu_snapshot(), _total_own_cpu_s()
        time.sleep(sample_s)
        t1 = time.monotonic()
        c1 = {c: container_cpu_usage_usec(c) for c in running}
        h1, o1 = _host_cpu_snapshot(), _total_own_cpu_s()
        dt = max(t1 - t0, 1e-6)
        per_c = {}
        for c in running:
            a, b = c0.get(c), c1.get(c)
            per_c[c] = (round((b - a) / 1e6 / dt, 3)
                        if a is not None and b is not None else None)
        attributed = sum(v for v in per_c.values() if v is not None)
        own_now = (o1 - o0) / dt
        host_busy = None
        if h0 and h1:
            hz = os.sysconf('SC_CLK_TCK') or 100
            busy = ((h1[0] - h0[0]) - (h1[1] - h0[1])) / hz / dt
            if -0.5 <= busy <= ncpu * 1.5:      # implausible -> unavailable, never clamped
                host_busy = round(busy, 2)
        load1 = os.getloadavg()[0]
        foreign_now = (round(host_busy - attributed - own_now, 2)
                       if host_busy is not None else None)
        foreign_load1 = round(load1 - attributed - own_cores_recent(), 2)
        r = {'load1': round(load1, 2),
             'host_busy_cores': host_busy,
             'container_idle_cores': per_c,        # current rate, not a historical idle
             'container_attributed': round(attributed, 2),
             'own_process_cores': round(own_now, 3),
             'foreign_now': foreign_now,
             'foreign_by_load1': foreign_load1,
             # THE GATED NUMBER: instantaneous when /proc/stat is readable,
             # load1-based only as a fallback.
             'foreign_excess': foreign_now if foreign_now is not None else foreign_load1,
             'basis': ('instantaneous (/proc/stat busy − containers − ours)'
                       if foreign_now is not None
                       else 'load1 − containers − ours (LAGGING ~60s; /proc/stat unreadable)')}
        readings.append(r)
        return r

    t0 = time.monotonic()
    r = take()
    while r['foreign_excess'] > max_foreign:
        remaining = settle_deadline_s - (time.monotonic() - t0)
        if remaining <= 0:
            break
        say(f'quiet-box: foreign {r["foreign_excess"]:.2f} > {max_foreign} — re-reading '
            f'(a tail decays, a hog does not; {remaining:.0f}s of budget left)')
        time.sleep(min(15.0, remaining))   # bounded: never overshoot the budget
        r = take()
    first, last = readings[0]['foreign_excess'], readings[-1]['foreign_excess']
    trend = ('SINGLE READING' if len(readings) == 1 else
             'DECAYING' if last < first - 0.15 else
             'RISING' if last > first + 0.15 else 'SUSTAINED')
    return {'PASS': last <= max_foreign, 'threshold': max_foreign,
            'readings': readings, 'n_readings': len(readings),
            'trend': trend, 'settle_wall_s': round(time.monotonic() - t0, 1),
            # Last reading promoted to the top level — EVERY field of it, so a
            # consumer never has to reach into readings[-1] for one stray key.
            **{k: v for k, v in readings[-1].items()},
            'note': ('foreign = load1 minus our containers minus our own process tree; '
                     'own_process_cores is CPU-seconds/window (a lower bound — load1 '
                     'also counts uninterruptible sleep)')}


def quiet_box_line(qb: dict) -> str:
    """THE one-and-only formatter for a quiet_box result — driver and smoke,
    pass and fail (2026-08-22).

    Born from its own defect: quiet_box's return shape changed and TWO callers
    kept formatting the old keys, in the PASS branch each, so the happy path
    crashed on a KeyError while the failure path stayed fine. That is entry 6
    (a provenance change follows the value to every consumer) with the twist
    that the second copy was not in another file — it was the OTHER BRANCH of
    the same feature, which the change that broke it never ran. The cure is
    structural: one formatter, so there is no second copy to drift, and a
    self-test that calls producer and formatter together (make_sample_export)
    so a future key change breaks a test rather than a 2 a.m. leg."""
    verdict = 'PASS' if qb.get('PASS') else 'FAIL'
    return (f'{verdict} foreign {qb.get("foreign_excess")} vs threshold '
            f'{qb.get("threshold")} — host busy {qb.get("host_busy_cores")} − containers '
            f'{qb.get("container_attributed")} {qb.get("container_idle_cores")} − ours '
            f'{qb.get("own_process_cores")} [{qb.get("basis")}]; load1 {qb.get("load1")} '
            f'(lagging, by-load1 foreign {qb.get("foreign_by_load1")}); '
            f'{qb.get("n_readings")} reading(s) over {qb.get("settle_wall_s")}s, '
            f'trend {qb.get("trend")}')


def container_cpu_usage_usec(container: str, timeout_s: int = 15) -> Optional[int]:
    """The container cgroup's OWN CPU accounting (cpu.stat usage_usec) — the
    one reader behind the quiet-box idle baseline, the idle-with-instances-live
    sample (Ticket 4 burden) and the per-leg CPU bracket (#34: utilisation
    denominators come from the container, never the driver; the probes read
    this same file the same way, so leg figures and sweep points are one
    quantity). None when unreadable — each caller decides whether absence
    fails; none of them dresses None as 0."""
    try:
        out = subprocess.run(['docker', 'exec', container, 'cat', '/sys/fs/cgroup/cpu.stat'],
                             capture_output=True, text=True, timeout=timeout_s).stdout
        return int([l for l in out.splitlines() if l.startswith('usage_usec')][0].split()[1])
    except Exception:
        return None


def container_idle_cores(container: str, sample_s: float = 4.0) -> Optional[float]:
    """The arm's OWN idle CPU burn, measured from its cgroup over a short
    window (usage_usec delta / wall). Exists because the engine idles at ~1.002
    cores (measured 2026-08-21, box otherwise idle) — an absolute load gate
    would trip on the system under test by existing. Returns None when the
    cgroup is unreadable; the quiet-box caller treats None as zero-attributed
    (foreign excess then reads HIGH, which fails closed in the right
    direction); the idle-burden caller refuses the leg."""
    a = container_cpu_usage_usec(container)
    if a is None:
        return None
    time.sleep(sample_s)
    b = container_cpu_usage_usec(container)
    if b is None:
        return None
    return round((b - a) / 1e6 / sample_s, 3)


def total_detections(records: List[dict]) -> Optional[int]:
    """Detections across a leg, TYPE-CHECKED per source because the two arms
    record it differently: the LI arm carries n_detections / detections_per_frame
    as a list, while the RR arm cannot recover a client-side count and carries
    frame_label_multisets (the multiset length IS the count). Returns None when
    no record carries either — absent, never 0."""
    total, seen = 0, False
    for r in records:
        n = r.get('n_detections')
        if isinstance(n, int):
            total += n; seen = True; continue
        dpf = r.get('detections_per_frame')
        if isinstance(dpf, list) and all(isinstance(x, (int, float)) for x in dpf):
            total += int(sum(dpf)); seen = True; continue
        fls = r.get('frame_label_multisets')
        if isinstance(fls, list) and all(isinstance(x, list) for x in fls):
            total += sum(len(x) for x in fls); seen = True
    return total if seen else None


def efficiency_block(service_cpu_s: Optional[float], leg_wall_s: float,
                     ok_frames: int, ok_video_s: float, n_ok: int,
                     idle_burden: Optional[dict], ncpu: int,
                     n_detections: Optional[int] = None, n_chunks: Optional[int] = None,
                     usd_per_hour: float = 1.428) -> dict:
    """The CPU-efficiency family for one leg from the container cgroup bracket
    — with the Ticket-4 idle burden BESIDE it. Measured 2026-08-21 (RR
    concurrency sweep, T=8): the engine idles at ~1.0 core + ~0.26 cores per
    live token (PARTIAL — neither per-server nor per-token); at M=4 that is
    2.02 cores, 6.3% of the box, before any work. The burden is REPORTED next
    to every figure and never subtracted: whether the spin is additive under
    load is unmeasured, and a subtracted figure would be arithmetic wearing a
    measurement's clothes (register entry 5). The two `_if_additive` values are
    labeled as exactly that. `valid` is False whenever a read was absent or a
    value is impossible — absence fails before agreement; nothing is clamped
    (#34)."""
    have_cpu = service_cpu_s is not None and leg_wall_s > 0
    idle_live = (idle_burden or {}).get('idle_cores_with_instances_live')
    eff_cores = (service_cpu_s / leg_wall_s) if have_cpu else None
    blk: Dict[str, Any] = {
        'valid': bool(have_cpu and idle_live is not None),
        'source': ('container cgroup cpu.stat usage_usec bracketed around the leg — the '
                   'same reader as the probes (#34: denominators from the container, '
                   'never the driver)'),
        'service_cpu_s': round(service_cpu_s, 1) if have_cpu else None,
        'effective_cores': round(eff_cores, 3) if eff_cores is not None else None,
        'cpu_util_of_box': (round(eff_cores / ncpu, 4)
                            if eff_cores is not None and ncpu else None),
        'box_cpus': ncpu,
        'cpu_s_per_footage_min': (round(service_cpu_s / (ok_video_s / 60), 3)
                                  if have_cpu and ok_video_s else None),
        'cpu_s_per_frame': (round(service_cpu_s / ok_frames, 3)
                            if have_cpu and ok_frames else None),
        'cpu_s_per_video': (round(service_cpu_s / n_ok, 1)
                            if have_cpu and n_ok else None),
        # Adopted from Leela's V-suite so the four-way table assembles without
        # gaps (2026-08-23). All three derive from data we already collect; being
        # a superset of her metric set costs nothing.
        'cpu_s_per_detection': (round(service_cpu_s / n_detections, 4)
                                if have_cpu and n_detections else None),
        'cpu_s_per_chunk': (round(service_cpu_s / n_chunks, 3)
                            if have_cpu and n_chunks else None),
        'n_detections': n_detections,
        'n_chunks': n_chunks,
        'usd_per_1k_footage_hours': (
            round(usd_per_hour / (ok_video_s / leg_wall_s) * 1000, 2)
            if leg_wall_s and ok_video_s else None),
        'usd_per_hour_basis': (f'{usd_per_hour} (instance on-demand $/h; '
                               'cost = $/h / x_realtime * 1000, her V5 definition)'),
        'idle_burden': dict(idle_burden) if idle_burden else None,
        'policy': ('idle_burden is reported beside every figure above and never '
                   'subtracted — additivity under load is unmeasured (Ticket 4)'),
    }
    if eff_cores is not None and ncpu and eff_cores > ncpu:
        blk['impossible_value'] = (f'effective_cores {eff_cores:.2f} > box_cpus {ncpu}: '
                                   'flagged, never clamped (#34)')
        blk['valid'] = False
    if idle_live is not None and have_cpu:
        blk['idle_burden']['idle_cpu_s_over_leg_if_additive'] = round(idle_live * leg_wall_s, 1)
        blk['idle_burden']['idle_share_of_service_cpu_if_additive'] = (
            round(idle_live * leg_wall_s / service_cpu_s, 4) if service_cpu_s else None)
    if not blk['valid'] and 'impossible_value' not in blk:
        blk['absent'] = [k for k, v in (('service_cpu_s', service_cpu_s),
                                        ('idle_cores_with_instances_live', idle_live))
                         if v is None]
    return blk


def settled_census(container: str, tries: int = 10, interval_s: float = 3.0) -> list:
    """probe_rr.task_process_census, once STABLE (two consecutive equal counts).
    The engine reaps a terminated task's subprocess asynchronously, and
    preflight's envprobe was terminated moments before the census baseline —
    an instant snapshot could still see the corpse and shift the delta."""
    prev = task_process_census(container)
    for _ in range(tries):
        time.sleep(interval_s)
        cur = task_process_census(container)
        if len(cur) == len(prev):
            return cur
        prev = cur
    return prev


# rfdetr 1.5.2 assets/model_weights.py:192-196 — RFDETRBase's default weights
# 'rf-detr-base.pth' download from storage.googleapis.com/rfdetr/rf-detr-base-coco.pth,
# md5-validated by the package itself. This constant IS the pinned weight lineage;
# the read-back below proves the bytes each arm serves match it.
RFDETR_BASE_MD5 = 'b4d3ce46099eaed50626ede388caf979'
RFDETR_PATHS = {'rr': '/opt/rocketride/engine/cache', 'li': '/opt/rfdetr-cache'}


def rfdetr_checkpoint_md5(container: str, search_root: str) -> Optional[str]:
    """md5 of rf-detr-base.pth inside a running container; None if absent."""
    try:
        out = subprocess.run(
            ['docker', 'exec', container, 'sh', '-c',
             f"find {search_root} -name 'rf-detr-base*.pth' -exec md5sum {{}} \\; | head -1"],
            capture_output=True, text=True, timeout=60).stdout.strip()
        return out.split()[0] if out else None
    except Exception:
        return None


def container_declared_threads(container: str) -> Dict[str, str]:
    """The six variables as DECLARED on the container (docker inspect env) —
    the 'declared' side of Crossroad 17's declared-vs-measured check."""
    raw = docker_inspect(container, '{{range .Config.Env}}{{println .}}{{end}}') or ''
    out = {}
    for line in raw.splitlines():
        if '=' in line:
            k, v = line.split('=', 1)
            if k in THREAD_KEYS:
                out[k] = v
    return out


def docker_inspect(container: str, fmt: str) -> Optional[str]:
    try:
        out = subprocess.run(['docker', 'inspect', '-f', fmt, container],
                             capture_output=True, text=True, timeout=15)
        return out.stdout.strip() if out.returncode == 0 else None
    except Exception:
        return None


def lifetime_state_glance(state: dict) -> str:
    """One log line per lifetime-state reading: docker-root free space, the
    fragmentation proxy, and per-container spool + memory — the numbers the
    lifetime pre-registration reads, visible in the run log as they land."""
    h = state.get('host', {})
    dr = (h.get('df') or {}).get('docker_root') or {}
    mb = (h.get('frag') or {}).get('mb_groups') or {}
    bits = [(f"docker_root free {dr.get('free_bytes', 0) / 2**30:.1f} GiB"
             if dr.get('state') == 'measured' else f"docker_root df {dr.get('state')}"),
            (f"frag avg-extent {mb.get('avg_free_extent_kb')} KiB, >=4MiB share "
             f"{mb.get('free_share_in_extents_ge_4mib_lower_bound')}"
             if mb.get('state') == 'measured' else f"frag {mb.get('state')}")]
    conts = state.get('containers', {})
    for c, rec in list(conts.items())[:2]:
        sp = next(iter((rec.get('spool') or {}).values()), {})
        pr = rec.get('procs') or {}
        cg = rec.get('cgroup') or {}
        bits.append(f"{c}: spool du {sp.get('du_kb')} KiB/{sp.get('n_files')} files, layer "
                    f"{(rec.get('layer') or {}).get('size')}, cg anon "
                    f"{(cg.get('anon') or 0) / 2**30:.2f} GiB, procs {pr.get('n')} rss "
                    f"{(pr.get('vmrss_kb') or 0) / 2**20:.2f} GiB")
    if len(conts) > 2:
        bits.append(f'(+{len(conts) - 2} more containers in the export)')
    return ' | '.join(bits)


class _ConsumedContainerArg:
    """After service-set resolution, the raw args.{rr,li}_container attributes
    are REPLACED with this: any use (str, format, ==, bool, hash) RAISES.
    Structural, not a comment — the li_video-default bug shipped twice
    (preflight flags 2026-08-25, LI weights md5 2026-08-26) because raw reads
    after resolution compiled fine. Now they cannot run."""
    _MSG = ('raw args container attribute read AFTER service-set resolution — '
            'use args._svc_containers (class fix 2026-08-26; the raw default '
            'was the dead-li_video bug, twice)')

    def _boom(self, *a, **k):
        raise RuntimeError(self._MSG)
    __str__ = __format__ = __eq__ = __bool__ = __hash__ = _boom

    def __repr__(self):
        return '<consumed container arg>'


def containers_rfdetr_md5(containers: List[str], path: str) -> Dict[str, Optional[str]]:
    """Weights identity for EVERY instance. A mixed set is exactly the failure
    this check exists to catch (one stale container serving old weights inside
    a balanced set) — the caller refuses on ANY mismatch, naming per-instance."""
    return {c: rfdetr_checkpoint_md5(c, path) for c in containers}


def containers_declared_threads(containers: List[str]) -> Dict[str, Any]:
    """Declared -e thread env per instance; instances are started by ONE loop,
    so disagreement means a mixed set — refuse, naming each."""
    per = {c: container_declared_threads(c) for c in containers}
    vals = {json.dumps(v, sort_keys=True) for v in per.values()}
    if len(vals) > 1:
        raise SystemExit('NOT DONE — declared thread env DISAGREES across the service set '
                         f'(mixed containers): { {c: v for c, v in per.items()} }')
    return next(iter(per.values()))


def resolve_service_containers(arm: str, rr_container: Optional[str],
                               li_container: Optional[str],
                               li_containers_spec: Optional[str],
                               n_li_ports: int) -> List[str]:
    """The container set the efficiency family samples — ALL of the service or
    none of it (2026-08-25 ruling). A multi-instance posture sampled from one
    container reported one-Nth of the service as the service; that number was
    quotable and wrong, which is the worst kind. FAIL CLOSED here."""
    if arm == 'rocketride':
        return [rr_container]
    if li_containers_spec:
        names = [x.strip() for x in li_containers_spec.split(',') if x.strip()]
        if len(names) != len(set(names)) or not names:
            raise SystemExit(f'NOT DONE — --li-containers {li_containers_spec!r} empty/duplicates')
        if len(names) != n_li_ports:
            raise SystemExit(f'NOT DONE — {n_li_ports} LI port(s) but {len(names)} '
                             'container(s); every instance must be sampled or efficiency '
                             'is unquotable (one container per port, same order)')
        return names
    if n_li_ports > 1:
        raise SystemExit(f'NOT DONE — balanced mode ({n_li_ports} ports) requires '
                         '--li-containers naming ALL instances: a single-container sample '
                         f'reports one-{n_li_ports}th of the service as the service. '
                         'Refusing to compute efficiency from it (fail closed).')
    return [li_container]


def containers_cpu_usage_usec(containers: List[str]) -> Optional[int]:
    """Sum of the service's cgroups. None if ANY member is unreadable — a
    partial sum dressed as a total is worse than absence (#34)."""
    total = 0
    for c in containers:
        v = container_cpu_usage_usec(c)
        if v is None:
            return None
        total += v
    return total


def containers_idle_cores(containers: List[str], sample_s: float = 4.0) -> Optional[float]:
    """Idle burn summed across the service's containers, ONE shared wall window
    (not N serial windows). None if any cgroup is unreadable."""
    t0 = time.monotonic()
    a = {c: container_cpu_usage_usec(c) for c in containers}
    time.sleep(sample_s)
    wall = time.monotonic() - t0
    b = {c: container_cpu_usage_usec(c) for c in containers}
    if any(a[c] is None or b[c] is None for c in containers):
        return None
    return round(sum(b[c] - a[c] for c in containers) / 1e6 / wall, 3)


def image_provenance(container: str, lineage: Optional[str]) -> dict:
    """WHICH IMAGE this leg ran, as measured facts plus a declared lineage
    (Crossroad 33, 2026-08-22). The tag is not the identity: `rr:patched-video`
    now means "docker/Dockerfile.rocketride build PLUS one documented derived
    layer" (the env_probe instrument fix), because a full rebuild would
    re-resolve the floating ubuntu:22.04 base, the unpinned apt libs the engine
    ELF links, and the bootcheck constraints cache — replacing the image every
    RR number and gate 3's arming were measured on. A tag can be retagged; the
    image ID and layer count cannot, so both are recorded, and the deviation
    travels with every result rather than living only in a doc."""
    image_id = docker_inspect(container, '{{.Image}}')
    layers = None
    if image_id:
        try:
            out = subprocess.run(['docker', 'image', 'inspect', '-f',
                                  '{{len .RootFS.Layers}}', image_id],
                                 capture_output=True, text=True, timeout=30)
            if out.returncode == 0 and out.stdout.strip().isdigit():
                layers = int(out.stdout.strip())
        except Exception:  # noqa: BLE001 — recorded as None, never guessed
            layers = None
    return {
        'container': container,
        'requested_tag': docker_inspect(container, '{{.Config.Image}}'),
        'image_id': image_id,
        'rootfs_layer_count': layers,
        'labels': docker_inspect(container, '{{json .Config.Labels}}'),
        'lineage_declared': lineage,
        'lineage_is_declared': lineage is not None,
        'lineage_note': ('a declared string, not a measurement — it states how this image '
                         'was produced; the image_id and layer count are the measured '
                         'facts it must be read against'),
    }


def preflight_containers(rr_container: Optional[str], li_container: Optional[str],
                         li_containers: Optional[List[str]] = None) -> List[str]:
    """No cpuset on either arm this phase, no CFS quota ever (rule C1), and the
    RR container must BE the patched Phase 2 image — the box still carries the
    Phase 1 rr/li containers (2 days up, WITH cpuset), so name collisions fail
    here instead of contaminating a leg."""
    problems = []
    li_set = li_containers if li_containers else [li_container]
    for c in filter(None, [rr_container, *li_set]):
        running = docker_inspect(c, '{{.State.Running}}')
        if running != 'true':
            problems.append(f'{c}: not running (State.Running={running!r}) — refusing to '
                            'proceed against a dead or defaulted container name')
            continue
        cpuset = docker_inspect(c, '{{.HostConfig.CpusetCpus}}')
        nano = docker_inspect(c, '{{.HostConfig.NanoCpus}}')
        if cpuset is None:
            problems.append(f'{c}: docker inspect failed')
            continue
        if cpuset != '':
            problems.append(f'{c}: cpuset set ({cpuset}) — this phase runs uncpuset '
                            f'(a Phase 1 leftover container?)')
        if nano not in ('0', None):
            problems.append(f'{c}: NanoCpus={nano} — --cpus must never be set (rule C1)')
        # Crossroad 22 (instance seven): both arms run --network host —
        # docker-proxy inserts a userspace hop into every message (latency is
        # a measured quantity) and silently defeats TCP readiness checks. A
        # bridged container here would deviate from the configuration Phase
        # 1's numbers came from; the mode is measured, never trusted.
        net = docker_inspect(c, '{{.HostConfig.NetworkMode}}')
        if net != 'host':
            problems.append(f"{c}: NetworkMode={net!r}, not 'host' (Crossroad 22)")
    if rr_container:
        patched = docker_inspect(
            rr_container,
            '{{index .Config.Labels "benchmark.rocketride.duplication_patch_applied"}}')
        if patched != '1':
            problems.append(f'{rr_container}: duplication_patch_applied label is '
                            f'{patched!r}, not "1" — wrong image (label is an assertion; '
                            f'the PDF fixture in the held smoke is the measurement)')
    return problems


async def preflight(args, arm, rr_arm_active: bool) -> dict:
    say('preflight: manifest')
    meta, rows = load_manifest(Path(args.manifest))
    # WHERE the corpus is: never this file's default (2026-08-23 — three tools
    # carried three copies of corpus/ami/video and the campaign died at step 0
    # on ami_full). Explicit must agree with the manifest meta; absent derives
    # from it; a manifest that records none REFUSES. One resolver for all three.
    corpus_dir, corpus_src = resolve_corpus_dir(args.corpus_dir, meta, Path(args.manifest),
                                                'driver_video')
    args.corpus_dir = str(corpus_dir)
    say(f'preflight: corpus_dir={corpus_dir} [{corpus_src}]')
    bad = verify_corpus(rows, corpus_dir)
    if bad:
        raise SystemExit('NOT DONE — corpus does not match manifest:\n  ' + '\n  '.join(bad))

    say('preflight: container flags')
    # THE SERVICE SET IS RESOLVED HERE, BEFORE ANY NAME IS CHECKED (2026-08-25:
    # leg 2 died because preflight running-checked the default li_video while
    # the real instances were li_bal_0..7 — the resolution existed but ran
    # AFTER preflight). One resolution, stashed on args, reused by the CPU
    # bracket/collector below — one copy, no drift.
    args._svc_containers = resolve_service_containers(
        args.arm, args.rr_container, args.li_container,
        getattr(args, 'li_containers', None),
        len(getattr(arm, 'ports', [0])) if args.arm == 'llamaindex' else 1)
    # STRUCTURAL GUARD (2026-08-26): from here on, the raw attributes cannot be
    # used — any str/==/format/bool on them raises. Twice a site below read the
    # dead default; the third time is now a loud crash at the read site.
    _rr_name = args.rr_container
    args.rr_container = args.li_container = _ConsumedContainerArg()
    problems = preflight_containers(_rr_name if rr_arm_active else None,
                                    None,
                                    li_containers=(args._svc_containers
                                                   if not rr_arm_active else None))
    if problems:
        raise SystemExit('NOT DONE — container flags:\n  ' + '\n  '.join(problems))
    # Crossroad 22: network mode is a RECORDED value in provenance, not an
    # implicit flag (the check itself is in preflight_containers, fail-closed).
    network_mode = {c: docker_inspect(c, '{{.HostConfig.NetworkMode}}')
                    for c in args._svc_containers}
    say(f'preflight: network mode {network_mode} (Crossroad 22: host, both arms)')

    # Quiet-box gate — born from the 18-Aug finding: every sampler that day
    # carried a rock-steady +8 load1 floor from an unpinned background loop
    # (detected after the fact via system_tick.load1). Refuse to start a leg
    # on a box that is already busy; the collector still samples load1
    # throughout as the in-run detector.
    # Gate on EXCESS over the arms' own measured idle baselines, never an
    # absolute: the engine idles at ~1 core by existing (Ticket 4), and a
    # parity posture with live tokens may legitimately idle higher. Foreign
    # load = load1 minus what our containers' cgroups account for.
    qb = quiet_box(list(dict.fromkeys(filter(None, args._svc_containers))),
                   args.max_preleg_load1)
    if not qb['PASS'] and not args.allow_noisy_box:
        raise SystemExit(
            f'NOT DONE — pre-leg quiet box {quiet_box_line(qb)}\n'
            f'  readings: {json.dumps(qb["readings"])}\n'
            f'  A DECAYING trend means a tail (run_plan step 0 --verify sha256s the '
            f'corpus in a SIBLING process we cannot attribute — see the settle note); '
            f'SUSTAINED or RISING means a real hog: ps aux --sort=-%cpu | head. '
            f'Override with --allow-noisy-box (recorded).')
    say(f'preflight: quiet box {quiet_box_line(qb)}')
    pf_extra = {'preleg_load1': qb['load1'],
                'preleg_container_idle_cores': qb['container_idle_cores'],
                'preleg_own_process_cores': qb['own_process_cores'],
                'preleg_foreign_excess': qb['foreign_excess'],
                'preleg_quiet_box': qb}

    say('preflight: read-backs (absence fails before agreement)')
    readbacks: Dict[str, dict] = {}
    identity: Dict[str, Any] = {}
    if rr_arm_active:
        # SDK identity FIRST (instance six): names AND parameters verified
        # against the installed wheel before anything calls them. Null-controlled.
        identity['sdk'] = sdk_identity.readback(strict=True)
        say(f"preflight: SDK rocketride {identity['sdk']['package_version']} at "
            f"{identity['sdk']['module_path']} — entry points verified, null control fired")
        info = await rr_readback(args.rr_port)
        # Absence fails before agreement: a missing field is a stale-node
        # verdict, distinct from a field the node set to a negative value.
        assert_envprobe_complete(info, 'RR task')
        identity['envprobe_project_id'] = info.get('_envprobe_project_id')
        identity['env_probe_schema'] = info.get('env_probe_schema')
        readbacks['rr_task'] = {'env': info.get('env') or {},
                                'torch_num_threads': info.get('torch_num_threads')}
        identity['rr'] = {'rfdetr_import_ok': info.get('rfdetr_import_ok'),
                          'python_version': info.get('python_version'),
                          'python_executable': info.get('python_executable'),
                          'versions': info.get('package_versions') or {}}
        # PRESENT-and-not-True now genuinely means False (a real import
        # failure), never absent — assert_envprobe_complete guaranteed presence.
        if info['rfdetr_import_ok'] is not True:
            raise SystemExit('NOT DONE — RR task process reports rfdetr_import_ok='
                             f'{info["rfdetr_import_ok"]!r} '
                             f'({info.get("rfdetr_import_error")!r}): a REAL import '
                             'failure (the field is present) — the engine would '
                             'silently serve RT-DETR, a different model. Refusing to run.')
        md5 = rfdetr_checkpoint_md5(args._svc_containers[0], RFDETR_PATHS['rr'])
        identity['rr']['rfdetr_checkpoint_md5'] = md5
        identity['rr']['rfdetr_checkpoint_md5_ok'] = md5 == RFDETR_BASE_MD5
        if md5 != RFDETR_BASE_MD5:
            raise SystemExit(f'NOT DONE — RR rf-detr-base.pth md5 {md5!r} != registry '
                             f'{RFDETR_BASE_MD5} (rfdetr 1.5.2 lineage): wrong or absent weights.')
    else:
        identity['sdk'] = {'skipped': 'LI leg — the rocketride SDK is not on this path'}
        per_worker = await li_readbacks(arm)
        if len(per_worker) < (arm.declared_workers or 1):
            raise SystemExit(f'NOT DONE — only {len(per_worker)}/{arm.declared_workers} LI '
                             'workers answered /health: absent workers fail before agreement.')
        readbacks.update({k: {'env': v['env'], 'torch_num_threads': v['torch_num_threads']}
                          for k, v in per_worker.items()})
        impls = {v['detect_impl'] for v in per_worker.values()}
        identity['li'] = {'detect_impl': sorted(impls),
                          'python_version': next(iter(per_worker.values())).get('python_version'),
                          'versions': next(iter(per_worker.values()))['versions']}
        if impls != {'rfdetr'}:
            raise SystemExit(f'NOT DONE — LI detect_impl read back as {impls}, not rfdetr.')
        # RULING L leg read-back (Ruling T item 3, 2026-08-31): the sweeps'
        # probe refused a stale-config point; the LEGS were uncovered until
        # here. Null controls fire first, every preflight (register pattern) —
        # a check that cannot catch a 200 image checks nothing.
        if li_chunk_mismatches({'w': dict(EXPECTED_LI_CHUNK)}) != {}:
            raise SystemExit('NOT DONE — li_chunk_mismatches null control (pass) broken')
        if 'w' not in li_chunk_mismatches(
                {'w': {**EXPECTED_LI_CHUNK, 'chunk_overlap': 200}}):
            raise SystemExit('NOT DONE — li_chunk_mismatches null control (refuse) broken')
        bad_chunk = li_chunk_mismatches(per_worker)
        if bad_chunk:
            raise SystemExit(
                f'NOT DONE — LI chunk-config read-back does not match RULING L '
                f'(expected {EXPECTED_LI_CHUNK}) on {len(bad_chunk)}/{len(per_worker)} '
                f'worker(s): {bad_chunk} — stale li:video image? Rebuild + verify '
                'per probe/run_ruling_l_box.sh.')
        identity['li']['chunk_config_readback'] = {
            'expected': EXPECTED_LI_CHUNK,
            'per_worker': {k: {f: v.get(f) for f in EXPECTED_LI_CHUNK}
                           for k, v in per_worker.items()}}
        # EVERY instance's weights, not one container's (2026-08-26: this site
        # read the dead li_video default and failed a healthy 8-instance set;
        # and a MIXED set — one instance on other weights — is exactly what
        # this check exists to catch).
        md5s = containers_rfdetr_md5(args._svc_containers, RFDETR_PATHS['li'])
        identity['li']['rfdetr_checkpoint_md5_by_container'] = md5s
        identity['li']['rfdetr_checkpoint_md5_ok'] = all(
            v == RFDETR_BASE_MD5 for v in md5s.values())
        bad = {c: v for c, v in md5s.items() if v != RFDETR_BASE_MD5}
        if bad:
            raise SystemExit(f'NOT DONE — LI rf-detr-base.pth md5 mismatch vs registry '
                             f'{RFDETR_BASE_MD5} on {len(bad)}/{len(md5s)} instance(s): {bad} '
                             '(a mixed set is the exact failure this check exists for)')

    # Crossroad 17: per-arm declared-vs-measured; asymmetry across arms is a
    # recorded value, never a failure. Undeclared drift (#37) still fails.
    # Ruling 2026-08-21 (per-posture thread env): the RR leg states what it
    # EXPECTS on the container — an int (parity: the measured optimum) or
    # 'unset' (default posture: nothing declared, the engine default is what
    # a user gets; torch's own count is read back and recorded). The null
    # controls for both modes fire first, every preflight.
    gs.thread_pins_self_test()
    arm_label = 'rr' if rr_arm_active else 'li'
    expected = {'rr': args.rr_threads_env} if rr_arm_active else None
    pins = gs.thread_pins_by_arm({arm_label: readbacks},
                                 {arm_label: containers_declared_threads(args._svc_containers)},
                                 expected_by_arm=expected)
    if pins['PASS'] is not True:
        raise SystemExit(f'NOT DONE — thread pins (declared vs measured vs expected '
                         f'{expected}, per arm): {json.dumps(pins)}')
    if rr_arm_active:
        say(f"preflight: RR thread env expected {args.rr_threads_env!r} — declared "
            f"{pins['arms']['rr'].get('declared')}, in-process torch "
            f"{pins['cross_arm_values'].get('rr')} (read back, fail-closed)")

    return pf_extra | {'manifest_meta': meta, 'rows': rows, 'readbacks': readbacks,
            'identity': identity, 'thread_pin_parity': pins,
            'network_mode': network_mode,
            'pipe_sha256': sha256_bytes(PIPE_PATH.read_bytes()),
            'corpus_dir': str(corpus_dir), 'corpus_dir_source': corpus_src,
            'manifest_sha256': sha256_bytes(Path(args.manifest).read_bytes())}


# ---------------------------------------------------------------------------
# Legs — one submit path; stamps per #29
# ---------------------------------------------------------------------------

async def run_leg(arm, rows: List[dict], leg: str, concurrency: int,
                  corpus_dir: Path, writer: JsonlWriter, done: set,
                  interval_s: int) -> dict:
    sem = asyncio.Semaphore(1 if leg == 'sequential' else concurrency)
    consecutive_failures = 0
    stop = asyncio.Event()
    # Since the streaming refactor (Ruling 4, 2026-08-27) no whole blob is
    # ever resident — this counts in-flight STREAMS holding a slot after the
    # sha pass; the read-back below proves the cap held.
    resident = max_resident = 0

    async def one(row):
        nonlocal consecutive_failures, resident, max_resident
        if row['file'] in done or stop.is_set():
            return
        enqueue_ns = time.monotonic_ns()          # stamped BEFORE admission (#29)
        async with sem:
            if stop.is_set():
                return
            # STREAMING REFACTOR (Ruling 4, 2026-08-27): the driver never
            # holds a whole blob. The sha pass below (off the loop, after
            # admission — the DIAG_M1_BLAST discipline unchanged) streams the
            # file in 1 MiB chunks and warms the page cache; the send then
            # streams from disk (RRArm: per-write reads; LIArm: file body).
            # admit_ns stamps AFTER the sha pass so wall_s (admit->done)
            # keeps measuring the arm; read_s is the sha pass, recorded
            # BESIDE it — its basis changed from read+sha to sha-over-file
            # (same bytes touched once either way).
            path = corpus_dir / row['file']
            t_read = time.monotonic()
            submitted_sha = await asyncio.to_thread(sha256_file, path)
            read_s = round(time.monotonic() - t_read, 3)
            resident += 1
            max_resident = max(max_resident, resident)
            admit_ns = time.monotonic_ns()        # stamped at admission (#29)
            rec = {'video': row['file'], 'role': row['role'],
                   'submitted_sha256': submitted_sha, 'bytes': path.stat().st_size,
                   'read_s': read_s, 'read_s_basis': 'sha256 streaming pass (refactor 2026-08-27)',
                   'expected_frames': expected_frames(row, interval_s),
                   'video_s_manifest': row.get('video_s'),
                   'enqueue_ns': enqueue_ns, 'admit_ns': admit_ns}
            try:
                body = await arm.process(path, row['file'])
                rec.update(body)
                rec['done_ns'] = time.monotonic_ns()
                rec['wall_s'] = round((rec['done_ns'] - admit_ns) / 1e9, 2)
                consecutive_failures = 0
            except Exception as exc:  # noqa: BLE001 — recorded, never masked
                rec['error'] = repr(exc)
                rec['done_ns'] = time.monotonic_ns()
                consecutive_failures += 1
                say(f'FAIL {row["file"]}: {exc!r} ({consecutive_failures} consecutive)')
                if consecutive_failures >= BREAKER_K:
                    say(f'breaker: {BREAKER_K} consecutive failures — aborting leg (#32)')
                    stop.set()
            finally:
                resident -= 1
            writer.write(rec)

    if leg == 'sequential':
        for row in rows:
            await one(row)
        # Gate 8: resend the first measured video once; recorded under
        # '<file>::repeat' so resume-by-key cannot collide with the original.
        if rows and not stop.is_set():
            rep = dict(rows[0])
            rep_key = f"{rep['file']}::repeat"
            if rep_key not in done:
                enqueue_ns = time.monotonic_ns()
                async with sem:
                    # same discipline as one(): sha pass once admitted, off-loop;
                    # no whole blob (streaming refactor 2026-08-27)
                    rep_path = corpus_dir / rep['file']
                    rep_sha = await asyncio.to_thread(sha256_file, rep_path)
                    admit_ns = time.monotonic_ns()
                    rec = {'video': rep_key, 'role': 'determinism_repeat',
                           'submitted_sha256': rep_sha, 'bytes': rep_path.stat().st_size,
                           'expected_frames': expected_frames(rep, interval_s),
                           'enqueue_ns': enqueue_ns, 'admit_ns': admit_ns}
                    try:
                        rec.update(await arm.process(rep_path, rep['file']))
                        rec['done_ns'] = time.monotonic_ns()
                        rec['wall_s'] = round((rec['done_ns'] - admit_ns) / 1e9, 2)
                    except Exception as exc:  # noqa: BLE001
                        rec['error'] = repr(exc)
                        rec['done_ns'] = time.monotonic_ns()
                    writer.write(rec)
    else:
        await asyncio.gather(*[one(row) for row in rows])
    say(f'stream residency: max {max_resident} concurrent in-flight (cap = '
        f'{1 if leg == "sequential" else concurrency}); sha pass off-loop via to_thread; '
        'no whole blob held (streaming refactor 2026-08-27, DIAG_M1_BLAST discipline kept)')
    return {'aborted_by_breaker': stop.is_set(), 'max_inflight_streams': max_resident}


def leg_gates(records: List[dict], rows: List[dict], arm_name: str,
              interval_s: int, liveness_min_fraction: Optional[float] = None) -> dict:
    ok_records = [r for r in records if 'error' not in r
                  and '::repeat' not in str(r.get('video'))]
    repeats = {str(r['video']).replace('::repeat', ''): r
               for r in records if '::repeat' in str(r.get('video')) and 'error' not in r}
    expected = {r['file']: expected_frames(r, interval_s) for r in rows}
    gates: Dict[str, Any] = {}
    if not records:
        gates['frames_census'] = gs.not_run('frames_census', offered=len(rows),
                                            reason='leg produced no records file')
    else:
        gates['frames_census'] = gs.frames_census(ok_records, expected, arm_name)
        n_err = sum(1 for r in records if 'error' in r)
        gates['errors'] = {'PASS': n_err == 0, 'n_errors': n_err}
        dup_rows = [gs.self_duplication([{'doc': r['video'],
                                          'chunk_sha256': r.get('chunk_sha256') or []}])
                    for r in ok_records]
        gates['self_duplication_any'] = {
            'PASS': not any(r.get('whole_list_doubled') is True for r in ok_records),
            'doubled_videos': [r['video'] for r in ok_records
                               if r.get('whole_list_doubled') is True] or None,
            'indeterminate_videos': [r['video'] for r in ok_records
                                     if r.get('whole_list_doubled') is None] or None,
            'detector_rows': len(dup_rows)}
        eligible = [r for r in ok_records if (r.get('n_chunks') or 0) >= 64]
        if not eligible:
            gates['duplication_trigger'] = gs.not_run(
                'duplication_trigger', offered=len(ok_records),
                reason='no record reached the 64-chunk flush threshold organically '
                       '(approved: NOT RUN, never PASS)')
        else:
            gates['duplication_trigger'] = {
                'PASS': not any(r.get('whole_list_doubled') is True for r in eligible),
                'n_trigger_eligible': len(eligible),
                'n_indeterminate': sum(1 for r in eligible
                                       if r.get('whole_list_doubled') is None)}
        gates['chunkid_monotone'] = {
            'PASS': all(r.get('chunkid_monotone') for r in ok_records),
            'violations': [r['video'] for r in ok_records if not r.get('chunkid_monotone')] or None}
        # Gate 5 — threshold is probe-derived and REQUIRED; absent -> NOT RUN,
        # never a guessed default (ruling 2026-08-20).
        if liveness_min_fraction is None:
            gates['detection_liveness'] = gs.not_run(
                'detection_liveness', offered=len(ok_records),
                reason='--liveness-min-fraction not provided; value comes from probe data')
        else:
            gates['detection_liveness'] = gs.detection_liveness(ok_records, liveness_min_fraction)
        # Gate 7 — embed integrity over every vector in the leg.
        dims = [r.get('embed_dim') for r in ok_records for _ in (r.get('embedding_norms') or [None])]
        norms = [x for r in ok_records for x in (r.get('embedding_norms') or [None])]
        gates['embed_integrity'] = gs.embed_integrity(dims, norms)
        # Gate 8 — determinism repeat (sequential leg sends measured[0] twice).
        if repeats:
            first_by = {r['video']: r for r in ok_records}
            checks = {v: gs.determinism_repeat((first_by.get(v) or {}).get('chunk_sha256') or [],
                                               rep.get('chunk_sha256') or [])
                      for v, rep in repeats.items()}
            gates['determinism_repeat'] = {
                'PASS': all(c['PASS'] is True for c in checks.values()), 'per_video': checks}
        else:
            gates['determinism_repeat'] = gs.not_run(
                'determinism_repeat', reason='no ::repeat record in this leg '
                '(sequential legs produce one; blast legs report NOT RUN)')
        # RR frame-count method cross-check: two independent recoveries must agree.
        method_flags = [r.get('frame_count_methods_agree') for r in ok_records]
        if any(f is not None for f in method_flags):
            gates['frame_count_methods_agree'] = {
                'PASS': all(f is not False for f in method_flags),
                'disagreeing': [r['video'] for r in ok_records
                                if r.get('frame_count_methods_agree') is False] or None}
    return gates


# ---------------------------------------------------------------------------
# Cross-arm mode
# ---------------------------------------------------------------------------

def steady_window(records: List[dict], concurrency: int) -> dict:
    """In-flight window metrics — ALWAYS present in exports (defined: false
    with a reason when not computable). Load-bearing at 6x duration spread:
    one 48-min video holds the total span open, so span throughput and
    window throughput are different quantities and both get labelled.
    window_n rides in the same dict so it cannot be omitted separately."""
    ok = [r for r in records if 'error' not in r and r.get('admit_ns') and r.get('done_ns')
          and '::repeat' not in str(r.get('video'))]
    if concurrency <= 1:
        return {'defined': False, 'reason': 'sequential leg — no saturation window'}
    if len(ok) < concurrency:
        return {'defined': False,
                'reason': f'{len(ok)} records < concurrency {concurrency} — never saturated'}
    events = sorted([(r['admit_ns'], 1) for r in ok] + [(r['done_ns'], -1) for r in ok])
    inflight = 0
    t_first = t_last = None
    for t, d in events:
        inflight += d
        if inflight >= concurrency:
            if t_first is None:
                t_first = t
            t_last = t
    if t_first is None or t_last is None or t_last <= t_first:
        return {'defined': False, 'reason': 'saturation never reached or zero-width'}
    inside = [r for r in ok if t_first <= r['done_ns'] <= t_last]
    frames = sum(r.get('frames_observed') or 0 for r in inside)
    video_s = sum(r.get('video_s_manifest') or 0 for r in inside)
    wall = (t_last - t_first) / 1e9
    return {'defined': True, 'window_start_ns': t_first, 'window_end_ns': t_last,
            'window_wall_s': round(wall, 1),
            'window_n': len(inside),
            'window_frames': frames,
            'window_frames_per_s': round(frames / wall, 3) if wall else None,
            'window_realtime_factor': round(video_s / wall, 2) if wall and video_s else None,
            'note': 'window = [first in-flight==C, last in-flight>=C]; completions inside'}


def cross_gates(rr_path: Path, li_path: Path, tol: float,
                gate3_armed: Optional[str] = None) -> dict:
    rr, _, _ = read_completed(rr_path, key='video')
    li, _, _ = read_completed(li_path, key='video')
    rr_ok = [r for r in rr if 'error' not in r and '::repeat' not in str(r.get('video'))]
    li_ok = [r for r in li if 'error' not in r and '::repeat' not in str(r.get('video'))]
    li_by = {r['video']: r for r in li_ok}
    pairs = [{'video': r['video'], 'rr_chars': r.get('sum_chunk_chars'),
              'li_chars': (li_by.get(r['video']) or {}).get('sum_chunk_chars')}
             for r in rr_ok if r['video'] in li_by]
    # Gate 3 first (priority order, ruling 2026-08-20): STRICT label-multiset
    # agreement, armed ONLY once the probe's ES2002a comparison confirmed —
    # the arming argument carries the probe run id into provenance.
    if gate3_armed:
        per_video = {}
        for r in rr_ok:
            mate = li_by.get(r['video'])
            if not mate:
                continue
            per_video[r['video']] = gs.label_multiset_agreement(
                r.get('frame_label_multisets') or [], mate.get('frame_label_multisets') or [],
                scores_a=r.get('frame_scores'), scores_b=mate.get('frame_scores'))
        agreement = {'PASS': bool(per_video) and all(v['PASS'] is True for v in per_video.values()),
                     'armed_by_probe_run': gate3_armed,
                     'n_videos': len(per_video),
                     'failing': [v for v, g in per_video.items() if g['PASS'] is not True] or None,
                     'per_video': per_video}
        if agreement['failing']:
            # Diagnostic triage only — never a verdict (only a human downgrades,
            # in writing, with the reason; first hypothesis is a REAL difference).
            # ON DIVERGENCE, CHECK THE RECORDED VALUES IN THIS ORDER: the arms'
            # interpreter versions (identity_readback.*.python_version — the
            # engine embeds its own CPython, distinct from the container's PATH
            # python), then rfdetr/torch versions, then checkpoint md5.
            v = agreement['failing'][0]
            r = next(x for x in rr_ok if x['video'] == v)
            m = li_by[v]
            agreement['score_triage_first_failure'] = gs.score_triage(
                r.get('frame_scores') or [], m.get('frame_scores') or [])
    else:
        agreement = gs.not_run(
            'cross_detection_agreement',
            reason='awaiting probe confirmation — pass --gate3-armed <probe_run_id> '
                   'after the staged ES2002a comparison passes')
    out = {
        'cross_detection_agreement': agreement,
        'char_conservation': (gs.char_conservation_parity(pairs, tol=tol) if pairs
                              else gs.not_run('char_conservation',
                                              reason='no overlapping videos')),
        # Crossroad 39: the boundary-exclusion count is surfaced at the top of
        # the cross file, not buried per video — it can never be silent.
        'boundary_exclusions_total': (
            sum(v.get('n_boundary_excluded') or 0 for v in (agreement.get('per_video') or {}).values())
            if isinstance(agreement.get('per_video'), dict) else None),
        'chunk_count_ratio': gs.chunk_count_ratio(rr_ok, li_ok),
        'n_rr': len(rr_ok), 'n_li': len(li_ok), 'n_paired': len(pairs),
    }
    # Provenance chunk config FROM RECORDS, never the config literal (approved).
    for label, recs in (('rr', rr_ok), ('li', li_ok)):
        lens = [c for r in recs for c in (r.get('chunk_chars') or [])]
        out[f'{label}_chunk_config_measured'] = (
            {'chunk_size_max_observed': max(lens), 'chunk_chars_median': sorted(lens)[len(lens) // 2]}
            if lens else None)
    return out


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

async def run_warmup(args, arm, posture, warm, pf, out_dir, stem) -> None:
    """Driver-side warm-up: disjoint warm rows, coverage proven per instance,
    per-send ledger written before any verdict. Module-level so the Crossroad-40
    distribution logic is testable without a box (test_warmup_distribution.py);
    amain() calls it and nothing else does."""
    say(f'warm-up: {len(warm)} disjoint items')
    seen_pids, seen_tokens = set(), set()
    ledger: List[dict] = []

    async def warm_one(row):
        entry = {'i': len(ledger), 'row': row['file'], 'serving_pid': None,
                 'serving_port': None, 'token_index': None, 'wall_s': None, 'error': None}
        ledger.append(entry)
        warm_path = Path(args.corpus_dir) / row['file']
        t0 = time.monotonic()
        try:
            rec = await arm.process(warm_path, row['file'])
            entry['serving_pid'] = rec.get('serving_pid')
            entry['serving_port'] = rec.get('serving_port')
            entry['token_index'] = rec.get('token_index')
            if rec.get('serving_pid'):
                # identity = (port, pid): balanced-mode containers have their own
                # pid namespaces, so pid alone collides across instances
                seen_pids.add((rec.get('serving_port'), rec['serving_pid']))
            if rec.get('token_index') is not None:
                seen_tokens.add(rec['token_index'])
        except Exception as exc:  # noqa: BLE001
            entry['error'] = repr(exc)
            say(f'warm-up failure on {row["file"]}: {exc!r} (recorded, continuing)')
        finally:
            entry['wall_s'] = round(time.monotonic() - t0, 3)

    if args.arm == 'rocketride':
        # Tokens are DRIVER-ADDRESSED round-robin (_next_token): a
        # sequential top-up reaches a NEW token every send, so coverage is
        # by construction and kernel accept plays no part. This arithmetic
        # is the Corner-banked one (2 first batch + top-ups) — Crossroad 40
        # is about the LI arm and changes nothing here.
        conc_i = max(1, posture.tokens)
        sem = asyncio.Semaphore(conc_i)

        async def sem_warm(row):
            async with sem:
                await warm_one(row)

        first_batch = warm[:min(len(warm), 2 * conc_i)]
        await asyncio.gather(*[sem_warm(r) for r in first_batch])
        budget = 2 * max(conc_i, len(warm))
        extra, pos = 0, len(first_batch)
        while warm and len(seen_tokens) < posture.tokens and extra < budget:
            await warm_one(warm[pos % len(warm)])
            pos += 1
            extra += 1
        used = len(first_batch) + extra
        policy = (f'{len(first_batch)} first batch + {extra} top-up; rows re-sent when '
                  'exhausted — Crossroad 32; tokens round-robin (addressed, not accepted)')
        say(f'warm-up consumed {used} send(s) over {len(warm)} warm rows ({policy})')
    else:
        # CROSSROAD 40 (2026-08-23): LI warm-up goes CONCURRENT, in waves of
        # max(2 x declared workers, the leg's own concurrency). uvicorn
        # workers are KERNEL-SELECTED at accept, and low-concurrency traffic
        # does not distribute — measured: 8 concurrent posts into W=8
        # reached 6/8 (iid predicts ~5.25); 8 into W=4 reached 4/4; 32 into
        # W=8 reached 8/8 reliably (the Corner discriminator). The old
        # top-up sent ONE post at a time — the worst point of that curve —
        # and 18 sends reaching 6/8 killed the campaign at leg 2. Two waves
        # max = cumulative 4 x workers, the discriminator's proven load.
        # The coverage rule is UNCHANGED (an unwarmed worker serving its
        # first inference inside the measured window inflates the LI arm —
        # our own comparison arm); what changed is the distribution.
        workers = arm.declared_workers or 1
        leg_c = (args.blast_concurrency or 1) if args.leg == 'blast' else 1
        wave_n = max(2 * workers, leg_c)
        max_waves = 2
        sem = asyncio.Semaphore(wave_n)

        async def sem_warm(row):
            async with sem:
                await warm_one(row)

        waves = 0
        while warm and waves < max_waves and len(seen_pids) < workers:
            wave = [warm[(waves * wave_n + k) % len(warm)] for k in range(wave_n)]
            await asyncio.gather(*[sem_warm(r) for r in wave])
            waves += 1
            say(f'warm-up wave {waves}/{max_waves}: {wave_n} concurrent sends over '
                f'{len(warm)} warm rows -> {len(seen_pids)}/{workers} worker pids observed')
        used = len(ledger)
        policy = (f'{waves} wave(s) x {wave_n} concurrent (max(2 x {workers} workers, '
                  f'leg concurrency {leg_c})) — Crossroad 40; warm SET re-sent per '
                  'Crossroad 32; warmth gated on warm markers, Crossroad 41')
        say(f'warm-up consumed {used} send(s) over {len(warm)} warm rows ({policy})')

    # THE LEDGER IS WRITTEN BEFORE ANY VERDICT (2026-08-23). The leg-2 failure
    # printed only a count — 6/8 — and discarded which pids served and how many
    # sends each drew, so "distribution or dead workers?" was unanswerable from
    # the record. The failing run now carries its own diagnosis (entry 10).
    def _worker_ident(key: str):
        # 'li_worker_<pid>' (pre-2026-08-25) -> (None, pid);
        # 'li_worker_<port>_<pid>' (balanced-era) -> (port, pid)
        parts = key[len('li_worker_'):].split('_')
        return (None, int(parts[0])) if len(parts) == 1 else (int(parts[0]), int(parts[1]))
    declared_pids = (sorted(_worker_ident(k) for k in pf['readbacks']
                            if k.startswith('li_worker_'))
                     if args.arm == 'llamaindex' else [])
    per_pid: Dict[str, int] = {}
    for e in ledger:
        if e['serving_pid'] is not None:
            k = (f"{e.get('serving_port')}:{e['serving_pid']}" if e.get('serving_port')
                 else str(e['serving_pid']))
            per_pid[k] = per_pid.get(k, 0) + 1

    # CROSSROAD 41 (2026-08-23) — GATE ON THE WARM MARKERS, NOT RESPONSE PIDS.
    # Three attempts failed the old gate with DIFFERENT unserved pids each time
    # (6/8 [6,7]; 5/8 [10,11,13]; 6/8 [8,10]), which by the failure message's own
    # discriminator rules out workers that never draw work and leaves scheduling —
    # severe scheduling: one worker took 12 of 32 sends, another took 1. The old
    # gate was unachievable BY CONSTRUCTION: /process_video is async and offloads
    # the model call to a threadpool, so a worker's event loop never blocks and one
    # worker can accept unbounded concurrent connections. Concurrency raises the
    # odds of distribution; nothing the client does can compel it.
    #
    # THIS IS NOT A RELAXATION. The property the gate exists to enforce is "no
    # worker serves its first inference inside the measured window", and the
    # service proves it directly: every worker loads its model in lifespan and
    # writes a warm marker, /health reports the marker count, and wait_ready
    # --workers W already blocked on it before the driver posted anything.
    # Response-pid counting measured uvicorn's SCHEDULING — a property we neither
    # control nor need. Lowering the threshold to 75% WOULD have been the
    # relaxation: it accepts cold workers serving measured traffic. This asserts
    # the SAME property by its direct instrument instead of a proxy that three
    # runs prove unachievable.
    warm_markers = warm_declared = None
    if args.arm == 'llamaindex':
        try:
            h = await arm.health()
            warm_markers = h.get('warm_workers')
            warm_declared = h.get('declared_workers') or arm.declared_workers
        except Exception as exc:  # noqa: BLE001 — absence fails, never shrugs
            raise SystemExit(
                f'NOT DONE — warm-up could not read /health to verify warm markers '
                f'({exc!r}). Absence of the instrument is not evidence of warmth.')

    # Distribution is REPORTED, never gated — and it is a real observation about
    # the LI arm worth publishing: kernel accept skew under concurrent load,
    # measured on our own comparison arm.
    counts = sorted(per_pid.values(), reverse=True)
    skew = {
        'distinct_response_pids': len(seen_pids),
        'declared_workers': warm_declared or (arm.declared_workers
                                              if args.arm == 'llamaindex' else None),
        'sends': len(ledger),
        'per_pid_send_counts': per_pid or None,
        'busiest_worker_sends': counts[0] if counts else None,
        'quietest_serving_worker_sends': counts[-1] if counts else None,
        'unserved_declared_pids': [x for x in declared_pids
                                   if x not in {(y if isinstance(y, tuple) else (None, y))
                                                for y in seen_pids}
                                   and (None, x[1]) not in {(y if isinstance(y, tuple) else (None, y))
                                                            for y in seen_pids}] or None,
        'note': ('REPORTED, NOT GATED (Crossroad 41). uvicorn workers are selected by the '
                 'kernel at accept and /process_video does not block its event loop, so '
                 'response-pid spread measures scheduling, not warmth. Warmth is gated on '
                 'the service warm markers.'),
    }
    warm_path = out_dir / f'warmup_{stem}.json'
    warm_path.write_text(json.dumps({
        'arm': arm.name, 'leg': args.leg, 'posture': posture.name, 'policy': policy,
        'gate': {'rule': 'warm markers via /health (Crossroad 41)',
                 'warm_workers': warm_markers, 'declared_workers': warm_declared,
                 'tokens_seen': sorted(seen_tokens) or None},
        'sends': ledger,
        'response_pid_distribution': skew,
        'declared_worker_pids': declared_pids or None,
        'note': ('pid identity is only comparable within ONE container lifetime '
                 '(defect #23: pid reuse across restarts)')}, indent=1))
    say(f'warm-up ledger: {warm_path.name}')

    if args.arm == 'rocketride' and len(seen_tokens) < posture.tokens:
        raise SystemExit(f'NOT DONE — warm-up touched {len(seen_tokens)}/{posture.tokens} '
                         f'tokens; every instance must be warm before timing. '
                         f'Ledger: {warm_path.name}')
    if args.arm == 'llamaindex':
        if warm_markers is None or warm_declared is None:
            raise SystemExit(
                'NOT DONE — /health reported no warm_workers/declared_workers, so warmth '
                'cannot be proven. Absence fails first; do not fall back to the response-pid '
                f'count. Ledger: {warm_path.name}')
        if warm_markers < warm_declared:
            raise SystemExit(
                f'NOT DONE — only {warm_markers}/{warm_declared} workers have written a warm '
                f'marker (Crossroad 41). A worker without a marker has not loaded its model and '
                f'would serve its first inference inside the measured window, inflating THIS '
                f'arm. This is not the scheduling skew (reported, not gated): a missing marker '
                f'means a worker is genuinely not ready — read the container log and wait_ready. '
                f'Ledger: {warm_path.name}')
        say(f'warm-up gate: {warm_markers}/{warm_declared} warm markers present (Crossroad 41)')
        say(f'warm-up distribution (REPORTED, not gated): {len(seen_pids)}/{warm_declared} '
            f'distinct response pids over {len(ledger)} sends; busiest '
            f'{skew["busiest_worker_sends"]}, quietest {skew["quietest_serving_worker_sends"]} '
            '— kernel accept skew, published')
    say(f'warm-up complete: tokens={sorted(seen_tokens) or "n/a"} '
        f'worker_pids={len(seen_pids) or "n/a"}')


async def amain() -> int:
    # allow_abbrev=False + value-validated types (register entry 8): a guard
    # that checks presence rather than plausibility cannot fail for the case
    # it was built for.
    ap = argparse.ArgumentParser(allow_abbrev=False)
    ap.add_argument('--arm', choices=['rocketride', 'llamaindex'])
    ap.add_argument('--posture', choices=['default', 'parity'], default='default',
                    help='RocketRide only; Crossroad 9 runs BOTH, one at a time')
    ap.add_argument('--leg', choices=['sequential', 'blast'])
    ap.add_argument('--pass', dest='pass_n', type=positive_int('pass', 100), default=1,
                    help='blast pass number (run_plan PASSES). Pass >1 suffixes EVERY per-leg '
                         'artifact (records, export, collector, docker log, preflight) with '
                         '_p<N>: without it the second pass RESUMED from the first pass\'s '
                         'records and measured nothing (found 2026-08-21; the dry pass now '
                         'runs two passes so the composition proves it)')
    ap.add_argument('--n', type=positive_int('n', 10000),
                    help='measured videos (prefix of manifest measured rows)')
    ap.add_argument('--blast-concurrency', type=positive_int('blast-concurrency', 4096))
    ap.add_argument('--tokens', type=positive_int('tokens', 64),
                    help='parity posture M (default: LI declared_workers)')
    ap.add_argument('--rr-threads-env', type=threads_env_expectation('rr-threads-env'),
                    default=None,
                    help='EXPECTED six-var BLAS/OMP env on the RR container for THIS leg: an '
                         'int (parity posture: the measured optimum) or the literal "unset" '
                         '(default posture: nothing declared — the engine default is what a '
                         'user gets; ruling 2026-08-21). Required for --arm rocketride; read '
                         'back declared + in-process, fail-closed, recorded in the export.')
    ap.add_argument('--threads', type=positive_int('threads', 256),
                    help='parity posture per-token threads= (default: unset)')
    ap.add_argument('--manifest', default=str(MANIFEST_DEFAULT))
    ap.add_argument('--corpus-dir', default=None,
                    help='no default (2026-08-23): derived from the manifest meta, or explicit '
                         'and checked against it — corpus_locator.py')
    ap.add_argument('--interval-s', type=positive_int('interval-s', 3600), default=15)
    ap.add_argument('--rr-port', type=positive_int('rr-port', 65535), default=5565)
    ap.add_argument('--li-port', type=positive_int('li-port', 65535), default=8802)
    ap.add_argument('--li-containers', default=None,
                    help='balanced mode: comma list of the N single-worker containers, one '
                         'per --li-ports entry in the same order. REQUIRED when li-ports > 1 '
                         '(the collector and CPU bracket must sample ALL of the service).')
    ap.add_argument('--li-ports', default=None,
                    help='balanced mode (ruling 2026-08-25): "8802-8809" or comma list — '
                         'several SINGLE-worker instances, driver round-robins ports per '
                         'send (structural twin of RR token round-robin). Omit = one '
                         'endpoint on --li-port = the historical default posture')
    ap.add_argument('--rr-container', default='rr')
    ap.add_argument('--li-container', default='li_video')
    ap.add_argument('--out-dir', default=None)
    ap.add_argument('--skip-cache-drop', action='store_true',
                    help='wiring tests only — measured runs must evict and prove it')
    ap.add_argument('--preflight-only', action='store_true',
                    help='run the FULL real preflight (containers, weights, pins, quiet box, '
                         'readbacks) against live containers, then stop cleanly — the '
                         'minute-zero plan check runs this so a leg cannot die at minute 40 '
                         'on a preflight the plan check never exercised (2026-08-26)')
    ap.add_argument('--skip-warmup', action='store_true',
                    help='resume aid ONLY — a fresh container without warm-up is not measurable')
    ap.add_argument('--no-collector', action='store_true')
    ap.add_argument('--char-tol', type=bounded_float('char-tol', 1e-6, 0.5), default=0.02)
    ap.add_argument('--max-preleg-load1', type=bounded_float('max-preleg-load1', 0.1, 64.0),
                    default=2.0,
                    help='quiet-box gate: refuse to start with load1 above this '
                         '(hygiene bound, not probe-derived — idle box is <1)')
    ap.add_argument('--allow-noisy-box', action='store_true',
                    help='override the quiet-box gate; the override is recorded in the export')
    ap.add_argument('--liveness-min-fraction',
                    type=bounded_float('liveness-min-fraction', 1e-9, 1.0), default=None,
                    help='gate 5 threshold — PROBE-DERIVED, no default; absent = gate NOT RUN; '
                         'a fraction, so (0, 1] — impossible values are refused, never clamped')
    ap.add_argument('--gate3-armed', type=run_id('gate3-armed'), default=None,
                    metavar='PROBE_RUN_ID',
                    help='arm strict cross-arm detection agreement; the id names the probe '
                         'run whose ES2002a comparison confirmed — absent = gate NOT RUN')
    ap.add_argument('--usd-per-hour', type=bounded_float('usd-per-hour', 0.0001, 1000.0),
                    default=1.428,
                    help='instance on-demand $/hour for the cost metric (default 1.428, '
                         'c7i.8xlarge us-east-1 — the same basis Leela uses)')
    ap.add_argument('--image-lineage', default=None,
                    help='Crossroad 33: how the active arm\'s image was produced, recorded '
                         'VERBATIM in provenance beside the measured image id — e.g. the '
                         'derived-layer deviation on rr:patched-video. A tag is not an '
                         'identity.')
    ap.add_argument('--container-lifetime', default=None,
                    help='2026-09-06 (films-500 lifetime passes): a JSON object recorded '
                         'verbatim in provenance_video.container_lifetime — the serving '
                         'container(s)\' created time, AGE AT LEG START in seconds, and '
                         'the pass index within this lifetime. The within-lifetime drift '
                         '(RR degrades ~5%, LI improves ~8% across a first pass, then both '
                         'plateau) makes container age a measured variable, not a confound.')
    ap.add_argument('--spool-paths', default='/tmp',
                    help='2026-09-06 TASK 1: comma-separated IN-CONTAINER paths the arm spools '
                         'to (both arms /tmp: engine reader.py:425 media_*, LI service.py:164 '
                         'ws1v_spool_*). Read at leg start and leg end into '
                         'export.lifetime_state — df/du/file count/mounts of the spool, cgroup '
                         'memory, per-process RSS/RssAnon/VmData, writable-layer size, host free '
                         'space, the ext4 free-space fragmentation proxy, diskstats — the '
                         'filesystem-vs-process discriminator for the within-lifetime drift.')
    ap.add_argument('--fs-sample-s', type=bounded_float('fs-sample-s', 0.0, 300.0), default=5.0,
                    help='period of the host-filesystem statvfs stream under the leg '
                         '(fsstream_<stem>.jsonl; 0 disables) — spool high-water at the '
                         'filesystem level, the one the churn hypothesis acts on')
    ap.add_argument('--cross-label', default=None,
                    help='basis string stamped into the cross output (e.g. the default '
                         'posture is equal-work gates only, not a cross-arm performance '
                         'comparison — Crossroad 27 / ruling 2026-08-21)')
    ap.add_argument('--cross', nargs=2, metavar=('RR_JSONL', 'LI_JSONL'),
                    help='cross-arm gates over two completed record files; no run')
    args = ap.parse_args()

    if args.arm == 'rocketride' and args.rr_threads_env is None:
        raise SystemExit('NOT DONE — --rr-threads-env is required for the rocketride arm '
                         '(an int or "unset"): the thread env is a declared, read-back value '
                         'per leg, never implied by the posture (ruling 2026-08-21).')
    if args.cross:
        out = cross_gates(Path(args.cross[0]), Path(args.cross[1]), args.char_tol,
                          gate3_armed=args.gate3_armed)
        if args.cross_label:
            # Ruling 2026-08-21: the DEFAULT posture is an RR-internal ratio
            # (Crossroad 27), not a cross-arm performance comparison; its cross
            # file carries equal-work gates only. Stamp the basis so the
            # artifact says which it is — a reader can't mistake a gates file
            # for a performance claim.
            out = {'basis': args.cross_label} | out
        print(json.dumps(out, indent=1))
        ok = out['char_conservation'].get('PASS')
        return 0 if (ok is True or out['char_conservation'].get('verdict') == 'NOT RUN') else 1

    if not (args.arm and args.leg and args.n):
        ap.error('--arm, --leg and --n are required for a run (or use --cross)')
    if args.leg == 'blast' and not args.blast_concurrency:
        ap.error('--blast-concurrency is required for the blast leg (run plan sets it; '
                 'this driver refuses to invent it)')

    out_dir = Path(args.out_dir or (ROOT / 'working' / 'video' / 'results' /
                                    time.strftime('%Y%m%dT%H%M%SZ', time.gmtime())))
    out_dir.mkdir(parents=True, exist_ok=True)

    # ONE DRIVER PER ARM, STRUCTURALLY (2026-08-24): two drivers against one
    # container voided a probe tonight. Per-arm flock, held for the whole run;
    # released by the OS on any exit. --cross mode returned above — it touches
    # no container and takes no lock.
    import fcntl
    lock_path = Path(os.environ.get('TMPDIR', '/tmp')) / f'driver_video_{args.arm}.lock'
    lock_fh = open(lock_path, 'a+')
    try:
        fcntl.flock(lock_fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        lock_fh.seek(0)
        holder = lock_fh.read().strip() or 'unknown'
        raise SystemExit(f'NOT DONE — another driver_video ({args.arm}) holds {lock_path} '
                         f'(pid {holder}). Two drivers on one container corrupt both runs; '
                         'refusing. A dead holder frees the lock on its own exit.')
    lock_fh.truncate(0)
    lock_fh.write(f'{os.getpid()}\n')
    lock_fh.flush()
    say(f'driver lock held: {lock_path} (pid {os.getpid()})')

    # ---- arm + posture ----------------------------------------------------
    li_ports = [args.li_port]
    if args.li_ports:
        spec = args.li_ports
        if '-' in spec and ',' not in spec:
            a, b = spec.split('-', 1)
            li_ports = list(range(int(a), int(b) + 1))
        else:
            li_ports = [int(x) for x in spec.split(',') if x.strip()]
        if len(li_ports) != len(set(li_ports)) or not li_ports:
            raise SystemExit(f'NOT DONE — --li-ports {spec!r} has duplicates or is empty')
    li_probe = LIArm(li_ports)
    if args.arm == 'llamaindex':
        arm = li_probe
        await arm.start()
        posture = Posture('workers', arm.declared_workers or 1, None)
    else:
        # Parity M defaults to the LI service's declared workers — the whole
        # point of the posture. If LI is not up to answer, --tokens is required.
        if args.posture == 'parity':
            m = args.tokens
            if m is None:
                try:
                    await li_probe.start()
                    m = li_probe.declared_workers
                except Exception:
                    m = None
                if not m:
                    raise SystemExit('NOT DONE — parity posture needs M: LI /health is not '
                                     'answering and --tokens was not given.')
            posture = Posture('parity', m, args.threads)
        else:
            posture = Posture('default', 1, None)
        arm = RRArm(args.rr_port, posture, PIPE_PATH)

    pf = await preflight(args, arm if args.arm == 'llamaindex' else li_probe,
                         rr_arm_active=(args.arm == 'rocketride'))

    if args.preflight_only:
        say('PREFLIGHT-ONLY PASS — containers, weights (every instance), pins, quiet box '
            f'and readbacks all green for {args.arm}; stopping cleanly (no warm-up, no leg).')
        await arm.stop()
        return 0
    rows_all = pf['rows']
    measured = [r for r in rows_all if r['role'] == 'measured'][:args.n]
    warm = [r for r in rows_all if r['role'] == 'warm']
    if len(measured) < args.n:
        raise SystemExit(f'NOT DONE — manifest has {len(measured)} measured rows, --n {args.n}')

    if args.arm == 'rocketride':
        if posture.name == 'parity' and len(warm) < posture.tokens:
            # Crossroad 32 (2026-08-21): not a refusal. Warm rows may be
            # re-sent across tokens — warm-vs-MEASURED disjointness is the
            # invariant, not warm-vs-warm — and coverage (every token observed
            # serving) is gated below, where it always was.
            say(f'warm rows ({len(warm)}) < tokens ({posture.tokens}): rows will be re-sent '
                'until every token has served (Crossroad 32; coverage gated)')
        # CENSUS ASSERTION (D3, ruling 2026-08-21: goes in regardless of how
        # use_existing reads). M tokens declared -> M NEW task processes
        # measured, or the leg refuses: a parity posture whose tokens share a
        # task is a queue wearing a parity label. Config is never the evidence.
        census_before = settled_census(args._svc_containers[0])
        await arm.start()
        census_after = task_process_census(args._svc_containers[0])
        before_pids = {p['pid'] for p in census_before}
        new_procs = [p for p in census_after if p['pid'] not in before_pids]
        if len(new_procs) != posture.tokens:
            await arm.stop()
            raise SystemExit(
                f'NOT DONE — declared {posture.tokens} token(s) but measured '
                f'{len(new_procs)} NEW task process(es) in {args._svc_containers[0]} '
                f'(census {len(census_before)} -> {len(census_after)}, new pids '
                f'{[p["pid"] for p in new_procs]}). Tokens sharing a task process '
                f'would make every parity number a queue measurement (D3).')
        pf['task_census'] = {
            'declared_tokens': posture.tokens,
            'census_before': len(census_before), 'census_after': len(census_after),
            'new_task_pids': [p['pid'] for p in new_procs],
            'project_ids': arm.project_ids}
        say(f'census: {posture.tokens} token(s) -> {len(new_procs)} new task '
            f'process(es) {[p["pid"] for p in new_procs]} (declared==measured)')

    # TICKET 4 BURDEN (2026-08-21): the engine idles at ~1.0 core + ~0.26 cores
    # per live token (PARTIAL; probe_concurrency T=8 sweep, M=1..16). The
    # quiet-box baseline in preflight was sampled BEFORE arm.start() created
    # the tokens, so for the parity posture it holds the server spin only.
    # Sample the quantity the probe measured — idle cores with every instance
    # live, before any work — through the same reader, both arms, and carry it
    # into the export's efficiency block. An absent read refuses the leg: an
    # efficiency figure that cannot name its idle burden is not quotable.
    svc_containers = args._svc_containers   # resolved ONCE, before preflight
    svc_container = svc_containers[0]   # image identity only — instances share one image
    instances = posture.tokens if args.arm == 'rocketride' else (arm.declared_workers or 1)
    idle_sample_s = 6.0
    idle_live = containers_idle_cores(svc_containers, sample_s=idle_sample_s)
    if idle_live is None:
        await arm.stop()
        raise SystemExit(f'NOT DONE — cannot read cgroup cpu.stat across {svc_containers!r} for the '
                         'idle-with-instances-live sample (Ticket 4 burden); the leg\'s '
                         'efficiency figures would have no idle burden to carry.')
    ncpu = os.cpu_count() or 32
    _pre = pf.get('preleg_container_idle_cores') or {}
    _vals = [_pre.get(c) for c in svc_containers]
    idle_before = (round(sum(_vals), 3) if all(v is not None for v in _vals) else None)
    pf['idle_burden'] = {
        'instances': instances,
        'instance_kind': 'rr_tokens' if args.arm == 'rocketride' else 'li_workers',
        'idle_cores_before_instances': idle_before,
        'idle_cores_with_instances_live': idle_live,
        'sample_s': idle_sample_s,
        'idle_share_of_box': round(idle_live / ncpu, 4),
        'box_cpus': ncpu,
        # RR only: tokens were created between the two samples, so the
        # difference per token is a marginal. LI workers pre-exist the driver
        # (both samples see them live) — probe_li_workers holds LI's curve.
        'marginal_cores_per_instance': (
            round((idle_live - idle_before) / instances, 3)
            if args.arm == 'rocketride' and idle_before is not None and instances else None),
        'baseline_note': ('RR: before = server only (tokens not yet created); '
                          'LI: workers already live in both samples'),
        'reference': ('Ticket 4, measured 2026-08-21: ~1.0 server + ~0.26 cores/token at '
                      'T=8, PARTIAL — probe_concurrency ticket4_idle_answer is the curve'),
    }
    say(f'idle burden: {idle_live:.2f} cores with {instances} instance(s) live = '
        f'{idle_live / ncpu:.1%} of the box before any work '
        f'(pre-instance baseline {idle_before})')

    # Per-(arm, posture, leg, pass) artifact names. Pass 1 keeps the bare
    # name; pass N>1 gets _pN. Posture is in every name: collector and
    # docker-log files used to be per leg only and the parity leg silently
    # overwrote the default leg's (same class as the PASSES defect).
    sfx = '' if args.pass_n == 1 else f'_p{args.pass_n}'
    stem = f'{arm.name}_{posture.name}_{args.leg}{sfx}'
    (out_dir / f'preflight_{stem}.json').write_text(json.dumps(
        {k: v for k, v in pf.items() if k != 'rows'}
        | {'posture': posture.label(), 'pass': args.pass_n}, indent=1))
    say(f'preflight PASSED — {arm.name} {posture.label()} leg={args.leg} n={args.n}')

    # ---- page cache: evict corpus before the arm (settled decision 4) -----
    # fadvise(DONTNEED) + behavioral proof — works without sudo (box ssm-user
    # sudo is unverified). --skip-cache-drop exists for wiring tests only.
    if not args.skip_cache_drop:
        helper = ROOT / 'working' / 'video' / 'probe' / 'drop_cache_fadvise.py'
        files = [str(Path(args.corpus_dir) / r['file']) for r in rows_all]
        r = subprocess.run([sys.executable, str(helper), *files],
                           capture_output=True, text=True)
        say(f'cache eviction: rc={r.returncode} {r.stdout.strip().splitlines()[-1] if r.stdout else ""}')
        if r.returncode != 0:
            raise SystemExit('NOT DONE — corpus page-cache eviction not proven '
                             f'(rc={r.returncode}): {r.stderr.strip() or r.stdout.strip()}')

    # ---- warm-up: driver-side, disjoint (role=warm), coverage proven ------
    if not args.skip_warmup:
        await run_warmup(args, arm, posture, warm, pf, out_dir, stem)

    # ---- the leg, under the collector -------------------------------------
    rec_path = out_dir / f'records_{stem}.jsonl'
    prior, done_keys, torn = read_completed(rec_path, key='video')
    # AN ERRORED RECORD IS NOT A COMPLETED ONE (2026-08-23). read_completed keys
    # on 'video', and the failure path writes {'video': …, 'error': …} — so a leg
    # that died with 16 errored rows would, on resume, treat those 16 videos as
    # DONE and measure 152 of 168 while reporting success. Silent under-measurement
    # is worse than the crash that caused it. Errored keys are dropped here and
    # re-run; the rows stay in the file as the record of what happened, and the
    # post-loop reader takes the LAST record per video.
    errored = {r['video'] for r in prior if 'video' in r and 'error' in r}
    done_keys -= errored
    if prior:
        say(f'resume: {len(done_keys)} videos already recorded'
            + (f'; {len(errored)} errored row(s) will be RE-RUN, not skipped' if errored else '')
            + (f' (torn last line tolerated: {torn})' if torn else ''))
        if errored:
            say(f'resume: re-running after error: {sorted(errored)[:10]}'
                + (' ...' if len(errored) > 10 else ''))

    collector = None
    if not args.no_collector:
        from harness.collector_proc import ProcessCollector
        # ALL of the service's containers (2026-08-25): a multi-instance
        # posture sampled from one container is one-Nth of the service.
        root_pids = []
        for container in svc_containers:
            root_pid = docker_inspect(container, '{{.State.Pid}}')
            if not (root_pid and root_pid.isdigit() and int(root_pid) > 0):
                raise SystemExit(f'NOT DONE — cannot resolve container root pid for '
                                 f'{container!r}; the collector must sample the WHOLE '
                                 'service or nothing is quotable.')
            root_pids.append(int(root_pid))
        roles = {'driver': {'pids': [os.getpid()]},
                 'service': {'pids': root_pids}}
        collector = ProcessCollector(out_dir / f'collector_{stem}.jsonl',
                                     roles, interval_s=0.5)
        collector.start()

    # CPU bracket around the leg from the service container's own cgroup — the
    # efficiency family's numerator, read by the same function as the idle
    # samples and the probes. Read BEFORE arm.stop(): terminate() ends the
    # tokens whose burn the bracket is measuring.
    cg_leg1: Optional[int] = None
    collector_summary: Optional[dict] = None
    say(f'service CPU bracket: summing {len(svc_containers)} container cgroup(s): '
        f'{svc_containers if len(svc_containers) > 1 else svc_containers[0]}')
    # Lifetime-state readings (ruling 2026-09-06, TASK 1): the spool filesystem
    # and the process side at leg START, outside the CPU bracket, then a
    # statvfs stream under the leg; the END reading is taken after the bracket
    # closes and BEFORE arm.stop() ends the tokens whose memory it reads. A
    # fresh container on the same dirty filesystem starts slow if the
    # persisting slowdown is the filesystem, fast if it is process state.
    spool_paths = [p for p in args.spool_paths.split(',') if p.strip()]
    host_paths = {'corpus': str(args.corpus_dir), 'host_tmp': '/tmp', 'out_dir': str(out_dir)}
    ls_start = lifetime_state.read_state(svc_containers, spool_paths, host_paths, 'leg_start')
    say(f'lifetime_state leg_start: {lifetime_state_glance(ls_start)}')
    ls_end = None
    fs_sampler = None
    if args.fs_sample_s > 0:
        fs_sampler = lifetime_state.FsSampler(
            {**host_paths, 'docker_root': ls_start['host'].get('docker_root') or '/var/lib/docker'},
            out_dir / f'fsstream_{stem}.jsonl', args.fs_sample_s)
        fs_sampler.start()
    cg_leg0 = containers_cpu_usage_usec(svc_containers)
    t_leg0 = time.monotonic()
    dr0 = resource.getrusage(resource.RUSAGE_SELF)
    try:
        with JsonlWriter(rec_path) as writer:
            leg_meta = await run_leg(arm, measured, args.leg,
                                     args.blast_concurrency or 1,
                                     Path(args.corpus_dir), writer, done_keys,
                                     args.interval_s)
        leg_wall = time.monotonic() - t_leg0
        cg_leg1 = containers_cpu_usage_usec(svc_containers)
        dr1 = resource.getrusage(resource.RUSAGE_SELF)
        # bracket closed, tokens still alive: the END reading sees their memory
        try:
            ls_end = lifetime_state.read_state(svc_containers, spool_paths, host_paths, 'leg_end')
            say(f'lifetime_state leg_end: {lifetime_state_glance(ls_end)}')
        except Exception as exc:   # a reading must never cost a 3.7 h leg its export
            ls_end = {'phase': 'leg_end', 'state': f'unavailable: {exc!r}'}
            say(f'WARNING: lifetime_state leg_end reading failed: {exc!r}')
    finally:
        # stop() terminates every token BEFORE disconnect (Ticket 4): a leg
        # that dies mid-flight must not leave tokens idle-spinning in the
        # cgroup the next leg's collector and quiet-box baseline read — and
        # under Crossroad 43 they are ttl=0, so nothing reaps what this misses.
        if collector:
            collector_summary = collector.stop()   # its own summary, kept in the export
        await arm.stop()
    fs_stream = await fs_sampler.stop() if fs_sampler else None
    mem_traj = lifetime_state.service_memory_trajectory(out_dir / f'collector_{stem}.jsonl')
    service_cpu_s = ((cg_leg1 - cg_leg0) / 1e6
                     if cg_leg0 is not None and cg_leg1 is not None else None)
    # Collector health as a first-class, LOUD value (ruling 2026-08-22).
    if args.no_collector:
        collector_status = ('DISABLED (--no-collector): NO per-role resource sampling in '
                            'this leg — every memory/CPU-by-role figure is ABSENT, not zero')
        collector_summary = {'DISABLED': collector_status}
        say(f'WARNING: {collector_status}')
    elif isinstance(collector_summary, dict) and collector_summary.get('error'):
        collector_status = f'ERROR: {collector_summary["error"]}'
        say(f'WARNING: collector {collector_status}')
    elif not (isinstance(collector_summary, dict) and collector_summary.get('roles')):
        collector_status = 'EMPTY: collector ran but recorded no roles'
        say(f'WARNING: collector {collector_status}')
    else:
        collector_status = 'ok'

    # ---- gates + export ---------------------------------------------------
    records, _, _ = read_completed(rec_path, key='video')
    gates = leg_gates(records, measured, arm.name, args.interval_s,
                      liveness_min_fraction=args.liveness_min_fraction)
    # Gate 2 attribution (RR): capture the container log and scrape for the
    # detect node's drop warning — with a channel-liveness marker so a dead
    # log can never read as 'no drops'. Detector = gate 1; this ATTRIBUTES.
    if args.arm == 'rocketride':
        log_file = out_dir / f'dockerlog_{args._svc_containers[0]}_{posture.name}_{args.leg}{sfx}.txt'
        try:
            log_text = subprocess.run(['docker', 'logs', args._svc_containers[0]],
                                      capture_output=True, text=True, timeout=60
                                      ).stdout or ''
        except Exception:
            log_text = ''
        log_file.write_text(log_text[-2_000_000:])
        gates['dropped_frame_attribution'] = gs.log_attribution(
            log_text, '[entrypoint] RocketRide engine')
    driver_cpu_s = (dr1.ru_utime + dr1.ru_stime) - (dr0.ru_utime + dr0.ru_stime)
    driver_share = driver_cpu_s / leg_wall / (os.cpu_count() or 32) if leg_wall else None

    ok_records = [r for r in records if 'error' not in r]
    lens = [c for r in ok_records for c in (r.get('chunk_chars') or [])]
    measured_chunk_size = max(lens) if lens else None
    prov = pvl.build(
        arm=arm.name, mode=args.leg, corpus_sha=pf['manifest_sha256'],
        corpus_n=len(measured),
        offered_concurrency=(args.blast_concurrency if args.leg == 'blast' else 1),
        configured_concurrency=(posture.tokens if args.arm == 'rocketride'
                                else (arm.declared_workers or None)),
        warmup_policy=(f'driver-side, {len(warm)} disjoint manifest warm rows, coverage '
                       'proven per instance; LI sends concurrent in waves of '
                       'max(2 x workers, leg concurrency) (Crossroad 40), RR tokens '
                       'round-robin; per-send ledger in warmup_<stem>.json'),
        timeout_s=LI_HTTP_TIMEOUT_S,
        parser=f'ffmpeg fps=1/{args.interval_s} + rfdetr(RF-DETR base, thr 0.3)',
        chunk_size=measured_chunk_size or -1,   # FROM RECORDS; -1 = no records, unmissable
        chunk_overlap=0,
        embedding_model=EMBED_MODEL,
        container=','.join(svc_containers),
        splitter=('RecursiveCharacterTextSplitter' if args.arm == 'rocketride'
                  else 'SentenceSplitter(native, char length function supplied)'),
    )
    window = steady_window(records, args.blast_concurrency or 1)
    ok_frames = sum(r.get('frames_observed') or 0 for r in ok_records)
    ok_video_s = sum(r.get('video_s_manifest') or 0 for r in ok_records)
    export = {
        'arm': arm.name, 'posture': posture.label(), 'leg': args.leg, 'pass': args.pass_n,
        'submission_order': ('manifest-seq: deterministic by meeting id, identical both '
                             'arms; NOT longest-first — sorting to shorten the drain tail '
                             'would benchmark our scheduler, not the frameworks '
                             '(ruling 2026-08-20)'),
        'throughput': {
            'total_span_s': round(leg_wall, 1),
            'total_frames': ok_frames,
            'total_frames_per_s': round(ok_frames / leg_wall, 3) if leg_wall else None,
            'total_realtime_factor': round(ok_video_s / leg_wall, 2) if leg_wall else None,
            'steady_window': window,
        },
        # Ticket 4 (2026-08-21): the efficiency family carries the measured
        # idle burden with instances live — beside, never subtracted.
        'efficiency': efficiency_block(
            service_cpu_s, leg_wall, ok_frames, ok_video_s, len(ok_records),
            pf.get('idle_burden'), ncpu,
            n_detections=total_detections(ok_records),
            n_chunks=sum(r.get('n_chunks') or 0 for r in ok_records) or None,
            usd_per_hour=args.usd_per_hour),
        # Blocker-1/2 instrumentation (2026-08-27): the driver's OWN peak,
        # measured not assumed — proves the streaming refactor emptied the
        # driver of blobs. Basis stated; container-side memory is mem_watch's
        # job (cgroup anon vs page cache, per instance).
        'driver_memory': {
            'ru_maxrss_kb': resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
            'basis': 'getrusage(RUSAGE_SELF).ru_maxrss at export time — the '
                     'driver process peak over the whole leg (KiB on Linux)'},
        # A leg with no per-role sampling is DEGRADED, not merely quiet: every
        # memory/CPU-by-role figure is ABSENT, and a null summary beside nine
        # passing gates is the silent degradation this campaign has spent two
        # days deleting everywhere else. Say it in the record and in the
        # one-line summary (ruling 2026-08-22).
        'collector_status': collector_status,
        'collector_summary': collector_summary,
        # 2026-09-06 TASK 1: the filesystem-vs-process discriminator, leg start
        # and leg end, plus the fs stream under the leg and the service role's
        # memory trajectory from the collector stream (per-token growth vs
        # persistent server growth — top_by_rss names which).
        'lifetime_state': {
            'basis': lifetime_state.BASIS,
            'spool_paths': spool_paths,
            'leg_start': ls_start,
            'leg_end': ls_end,
            'fs_stream': fs_stream,
            'service_memory_trajectory': mem_traj,
        },
        'n_offered': len(measured), 'n_records': len(records),
        'n_errors': len(records) - len(ok_records),
        'leg_wall_s': round(leg_wall, 1),
        'aborted_by_breaker': leg_meta['aborted_by_breaker'],
        'wall_s_order_stats': sorted(round(r['wall_s'], 1) for r in ok_records
                                     if r.get('wall_s') is not None),
        'latency_normalized': (lambda ln: {
            'wall_s_per_video_minute': ln,
            'note': 'raw per-video wall_s and video_s_manifest are in every record; '
                    'this normalization keeps the 6x duration confound visible',
            'p50': ln[len(ln) // 2] if ln else None,
            'max': ln[-1] if ln else None,
            'n': len(ln),
            'percentile_policy': 'p50/max/n only below n=50 (no dressed percentiles)',
        })(sorted(round(r['wall_s'] / (r['video_s_manifest'] / 60), 2)
                  for r in ok_records
                  if r.get('wall_s') is not None and r.get('video_s_manifest'))),
        'preleg_load1': pf.get('preleg_load1'),
        'preleg_container_idle_cores': pf.get('preleg_container_idle_cores'),
        'preleg_foreign_excess': pf.get('preleg_foreign_excess'),
        'quiet_box_override': args.allow_noisy_box or None,
        'driver_cpu': {'cpu_s': round(driver_cpu_s, 1),
                       'share_of_box': round(driver_share, 4) if driver_share else None,
                       'over_1pct': (driver_share or 0) > 0.01},
        'gates': gates,
        'provenance_leela': prov,
        'provenance_video': {
            'pipe_sha256': pf['pipe_sha256'],
            'manifest_sha256': pf['manifest_sha256'],
            # ARM-AWARE (2026-08-22): threads_config / threads_note describe
            # RocketRide's use(threads=) and its engine default. Emitting them
            # on a LlamaIndex leg put an RR constant WITH AN RR SOURCE CITATION
            # (constants.py:48) into that arm's provenance — false about the
            # thing it describes, and exactly what makes a reviewer stop
            # trusting the rest of the record. The LI arm reports what it
            # actually has: declared uvicorn workers and the measured
            # per-worker torch count.
            'posture': ({'name': posture.name, 'tokens': posture.tokens,
                         'threads_config': posture.threads,
                         'threads_note': ('unset -> engine CONST_DEFAULT_MAX_THREADS=64 '
                                          '(constants.py:48)' if posture.threads is None else
                                          'explicit use(threads=)'),
                         # Ruling 2026-08-21: the six-var env is per POSTURE —
                         # expected by the operator, read back declared and
                         # in-process; 'unset' = the engine default a user gets.
                         'threads_env_expected': args.rr_threads_env,
                         'threads_env_in_process_torch': (
                             (pf['thread_pin_parity'].get('cross_arm_values') or {}).get('rr')),
                         } if args.arm == 'rocketride' else {
                         'name': posture.name,
                         'declared_workers': posture.tokens,
                         'threads_env_in_process_torch': (
                             (pf['thread_pin_parity'].get('cross_arm_values') or {}).get('li')),
                         'note': ('LlamaIndex arm: uvicorn worker PROCESSES. No use(threads=) '
                                  'and no engine thread default exist here — the thread '
                                  'configuration is the six BLAS/OMP variables, read back '
                                  'in-process from every worker; threads_config/threads_note '
                                  'are RocketRide fields and are deliberately absent.')}),
            'identity_readback': pf['identity'],
            'thread_pins_by_arm': pf['thread_pin_parity'],
            'task_census': pf.get('task_census'),
            'network_mode': pf.get('network_mode'),
            'image': image_provenance(svc_container, args.image_lineage),
            'container_lifetime': (json.loads(args.container_lifetime)
                                   if args.container_lifetime else None),
            'interval_s': args.interval_s,
            'rr_write_path': ('chunked-1MiB (2026-08-24, DIAG_M1_BLAST; the banked RR '
                              'default SEQUENTIAL leg ran the whole-frame path — wall_s '
                              'definition unchanged, wire shape differs and is disclosed)'
                              if args.arm == 'rocketride' else None),
            'frames_observed_method': ('bracket-count' if args.arm == 'rocketride'
                                       else 'extractor-count'),
            'chunk_config_source': 'measured from records (config literal never exported)',
        },
    }
    # Ruling 2026-08-21: throughput and idle burden legible TOGETHER, at a
    # glance — first key of the export, last line of stdout.
    glance = at_a_glance_line(export)
    export = {'at_a_glance': glance} | export
    # Structural guard: a blast export without window_n must be impossible.
    assert 'steady_window' in export['throughput'] and (
        export['throughput']['steady_window'].get('defined') is False
        or 'window_n' in export['throughput']['steady_window']), 'window_n missing'
    export_path = out_dir / f'export_{stem}.json'
    export_path.write_text(json.dumps(export, indent=1))
    say(f'export: {export_path}')
    say(f'AT A GLANCE: {glance}')
    if driver_share and driver_share > 0.01:
        say(f'WARNING: driver CPU share {driver_share:.1%} > 1% — report it; '
            'pinning gets reinstated if this holds (environment rule)')

    hard = [k for k, g in gates.items()
            if isinstance(g, dict) and g.get('PASS') is False]
    if not export['efficiency']['valid']:
        # The export is written (forensics) and the leg fails loudly: a CPU
        # figure with an absent read or an impossible value is not quotable.
        hard.append('efficiency(valid=False: '
                    + (export['efficiency'].get('impossible_value')
                       or f"absent {export['efficiency'].get('absent')}") + ')')
    if hard:
        say(f'GATES FAILED: {hard}')
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(asyncio.run(amain()))
