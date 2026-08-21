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
  #32 ttl=7200 explicit + K=3 consecutive-failure breaker;
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

from harness import gates_shared as gs                 # noqa: E402
from harness import provenance_leela as pvl            # noqa: E402
from harness.jsonl_stream import JsonlWriter, read_completed  # noqa: E402

PIPE_PATH = ROOT / 'working' / 'video' / 'benchmark_video_detect.pipe'
MANIFEST_DEFAULT = ROOT / 'working' / 'video' / 'ami_video_manifest.jsonl'
GENERATED_DIR = ROOT / 'working' / 'pipes' / 'generated'
EMBED_MODEL = 'sentence-transformers/multi-qa-MiniLM-L6-cos-v1'
BREAKER_K = 3
THREAD_KEYS = ('OMP_NUM_THREADS', 'MKL_NUM_THREADS', 'OPENBLAS_NUM_THREADS',
               'VECLIB_MAXIMUM_THREADS', 'NUMEXPR_NUM_THREADS', 'TORCH_NUM_THREADS')


def say(msg: str) -> None:
    print(f'[driver] {msg}', flush=True)


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
        t = 'unset(engine-default-64)' if self.threads is None else str(self.threads)
        return f'{self.name}[tokens={self.tokens},threads={t}]'


# ---------------------------------------------------------------------------
# Manifest
# ---------------------------------------------------------------------------

def load_manifest(path: Path) -> tuple[dict, List[dict]]:
    rows = [json.loads(l) for l in path.read_text().splitlines() if l.strip()]
    meta = rows[0].get('_meta', {}) if rows and '_meta' in rows[0] else {}
    return meta, [r for r in rows if '_meta' not in r]


def expected_frames(row: dict, interval_s: int = 15) -> Optional[int]:
    """Manifest-derived expectation for `-vf fps=1/interval`: frames at
    t = 0, interval, 2*interval, ... strictly below the video duration.
    The PROBE pins this formula against reality (84 on ES2002a.Corner)
    before any gate consumes it."""
    dur, fps = row.get('video_s'), row.get('fps')
    if not dur or not fps:
        return None
    return int(dur // interval_s) + 1 if dur % interval_s else int(dur // interval_s)


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
        'chunk_sha256': body.get('chunk_sha256'),
        'sum_chunk_chars': sum(body.get('chunk_chars') or []),
        'frames_observed': body.get('n_frames'),
        'frames_observed_method': 'extractor-count',
        'chunkid_monotone': True,   # LI chunks arrive ordered by construction
        'whole_list_doubled': gs.whole_list_doubled(body.get('chunk_sha256') or []),
        'n_detections': body.get('n_detections'),
        'detections_per_frame': body.get('detections_per_frame'),
        'frame_label_multisets': body.get('frame_labels'),
        'frame_scores': body.get('frame_scores'),
        'embed_dim': body.get('embed_dim'),
        'embedding_norms': body.get('embedding_norms'),
        'stage_s': body.get('stage_s'),
        'serving_pid': body.get('pid'),
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
        self._rr = 0

    async def start(self):
        from rocketride import RocketRide
        self.client = RocketRide(uri=f'ws://127.0.0.1:{self.port}/task/service',
                                 apikey='local-dev')
        await self.client.connect()
        for _ in range(self.posture.tokens):
            kwargs: Dict[str, Any] = dict(filepath=str(self.pipe_path), ttl=7200)
            if self.posture.threads is not None:
                kwargs['threads'] = self.posture.threads
            started = await self.client.use(**kwargs)
            self.tokens.append(started['token'])
        say(f'RR: {len(self.tokens)} token(s) live, posture {self.posture.label()}')

    def _next_token(self) -> tuple[int, str]:
        i = self._rr % len(self.tokens)
        self._rr += 1
        return i, self.tokens[i]

    async def process(self, blob: bytes, name: str) -> dict:
        idx, token = self._next_token()
        result = await self.client.send(token, blob, objinfo={'name': name},
                                        mimetype='video/x-msvideo')
        rec = record_from_rr(result)
        rec['token_index'] = idx
        return rec

    async def stop(self):
        if self.client:
            await self.client.disconnect()


class LIArm:
    name = 'llamaindex_video'

    def __init__(self, port: int):
        self.port = port
        self.declared_workers: Optional[int] = None

    async def start(self):
        health = await self.health()
        self.declared_workers = health.get('declared_workers')
        say(f'LI: warm_workers={health.get("warm_workers")} '
            f'declared={self.declared_workers} detect_impl={health.get("detect_impl")}')

    async def health(self) -> dict:
        import urllib.request
        return await asyncio.to_thread(
            lambda: json.load(urllib.request.urlopen(
                f'http://127.0.0.1:{self.port}/health', timeout=30)))

    async def process(self, blob: bytes, name: str) -> dict:
        import urllib.request
        req = urllib.request.Request(f'http://127.0.0.1:{self.port}/process_video',
                                     data=blob, method='POST',
                                     headers={'Content-Type': 'application/octet-stream'})

        def _post():
            with urllib.request.urlopen(req, timeout=7200) as resp:
                return json.load(resp)

        body = await asyncio.to_thread(_post)
        if 'error' in body:
            raise RuntimeError(f'LI service error: {body}')
        return record_from_li(body)

    async def stop(self):
        pass


# ---------------------------------------------------------------------------
# Read-backs (preflight; fail-closed, absence first)
# ---------------------------------------------------------------------------

def generate_envprobe_pipe() -> Path:
    """Measured pipe + env_probe + response_text (a3_env_torch pattern).
    Same task process as the loaded video nodes, so the rfdetr import predicate
    and the thread pins are read where they matter. Measured pipe untouched."""
    base = json.loads(PIPE_PATH.read_text())
    base['components'].append({'id': 'envprobe_1', 'provider': 'env_probe', 'config': {},
                               'input': [{'lane': 'text', 'from': 'webhook_1'}]})
    base['components'].append({'id': 'resp_env', 'provider': 'response_text',
                               'config': {'laneName': 'envprobe'},
                               'input': [{'lane': 'text', 'from': 'envprobe_1'}]})
    GENERATED_DIR.mkdir(parents=True, exist_ok=True)
    out = GENERATED_DIR / f'video_envprobe_{os.getpid()}.pipe'
    out.write_text(json.dumps(base, indent=1))
    return out


async def rr_readback(port: int) -> dict:
    from rocketride import RocketRide
    pipe = generate_envprobe_pipe()
    client = RocketRide(uri=f'ws://127.0.0.1:{port}/task/service', apikey='local-dev')
    await client.connect()
    try:
        started = await client.use(filepath=str(pipe), ttl=600)
        result = await client.send(started['token'], 'readback probe',
                                   mimetype='text/plain')
        texts = (result or {}).get('envprobe') or []
        info = json.loads(texts[0]) if texts else {}
    finally:
        await client.disconnect()
    return info


async def li_readbacks(arm: LIArm, timeout_s: float = 120) -> Dict[str, dict]:
    """Sample /health until every declared worker pid has answered (or timeout —
    which is an ABSENCE failure downstream, never a shrug)."""
    per_worker: Dict[str, dict] = {}
    declared = arm.declared_workers or 0
    deadline = time.monotonic() + timeout_s
    while len(per_worker) < declared and time.monotonic() < deadline:
        h = await arm.health()
        per_worker[f'li_worker_{h["pid"]}'] = {
            'env': h.get('thread_env') or {},
            'torch_num_threads': h.get('torch_num_threads'),
            'detect_impl': h.get('detect_impl'),
            'versions': h.get('versions') or {},
        }
    return per_worker


def container_idle_cores(container: str, sample_s: float = 4.0) -> Optional[float]:
    """The arm's OWN idle CPU burn, measured from its cgroup over a short
    window (usage_usec delta / wall). Exists because the engine idles at ~1.002
    cores (measured 2026-08-21, box otherwise idle) — an absolute load gate
    would trip on the system under test by existing. Returns None when the
    cgroup is unreadable; the caller treats None as zero-attributed (foreign
    excess then reads HIGH, which fails closed in the right direction)."""
    def usage_usec() -> Optional[int]:
        try:
            out = subprocess.run(['docker', 'exec', container, 'cat', '/sys/fs/cgroup/cpu.stat'],
                                 capture_output=True, text=True, timeout=15).stdout
            return int([l for l in out.splitlines() if l.startswith('usage_usec')][0].split()[1])
        except Exception:
            return None
    a = usage_usec()
    if a is None:
        return None
    time.sleep(sample_s)
    b = usage_usec()
    if b is None:
        return None
    return round((b - a) / 1e6 / sample_s, 3)


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


def preflight_containers(rr_container: Optional[str], li_container: Optional[str]) -> List[str]:
    """No cpuset on either arm this phase, no CFS quota ever (rule C1), and the
    RR container must BE the patched Phase 2 image — the box still carries the
    Phase 1 rr/li containers (2 days up, WITH cpuset), so name collisions fail
    here instead of contaminating a leg."""
    problems = []
    for c in filter(None, [rr_container, li_container]):
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
    bad = verify_corpus(rows, Path(args.corpus_dir))
    if bad:
        raise SystemExit('NOT DONE — corpus does not match manifest:\n  ' + '\n  '.join(bad))

    say('preflight: container flags')
    problems = preflight_containers(args.rr_container if rr_arm_active else None,
                                    args.li_container if not rr_arm_active else None)
    if problems:
        raise SystemExit('NOT DONE — container flags:\n  ' + '\n  '.join(problems))

    # Quiet-box gate — born from the 18-Aug finding: every sampler that day
    # carried a rock-steady +8 load1 floor from an unpinned background loop
    # (detected after the fact via system_tick.load1). Refuse to start a leg
    # on a box that is already busy; the collector still samples load1
    # throughout as the in-run detector.
    # Gate on EXCESS over the arms' own measured idle baselines, never an
    # absolute: the engine idles at ~1 core by existing (Ticket 4), and a
    # parity posture with live tokens may legitimately idle higher. Foreign
    # load = load1 minus what our containers' cgroups account for.
    baselines = {}
    for c in filter(None, [args.rr_container if rr_arm_active else None,
                           args.rr_container if not rr_arm_active else None,
                           args.li_container]):
        if c not in baselines and docker_inspect(c, '{{.State.Running}}') == 'true':
            baselines[c] = container_idle_cores(c)
    attributed = sum(v for v in baselines.values() if v is not None)
    load1 = os.getloadavg()[0]
    excess = load1 - attributed
    if excess > args.max_preleg_load1 and not args.allow_noisy_box:
        raise SystemExit(f'NOT DONE — pre-leg FOREIGN load {excess:.1f} '
                         f'(load1={load1:.1f} minus container idle {attributed:.1f} '
                         f'{baselines}) > {args.max_preleg_load1}. A background hog '
                         f'contaminated the 18-Aug runs; find and kill it, or override '
                         f'with --allow-noisy-box (recorded).')
    say(f'preflight: quiet box (load1={load1:.2f}, container idle {attributed:.2f} '
        f'{baselines}, foreign excess {excess:.2f})')
    pf_extra = {'preleg_load1': round(load1, 2),
                'preleg_container_idle_cores': baselines,
                'preleg_foreign_excess': round(excess, 2)}

    say('preflight: read-backs (absence fails before agreement)')
    readbacks: Dict[str, dict] = {}
    identity: Dict[str, Any] = {}
    if rr_arm_active:
        info = await rr_readback(args.rr_port)
        readbacks['rr_task'] = {'env': info.get('env') or {},
                                'torch_num_threads': info.get('torch_num_threads')}
        identity['rr'] = {'rfdetr_import_ok': info.get('rfdetr_import_ok'),
                          'versions': info.get('package_versions') or {}}
        if info.get('rfdetr_import_ok') is not True:
            raise SystemExit('NOT DONE — RR task process cannot import rfdetr '
                             f'({info.get("rfdetr_import_error")!r}): the engine would '
                             'silently serve RT-DETR, a different model. Refusing to run.')
        md5 = rfdetr_checkpoint_md5(args.rr_container, RFDETR_PATHS['rr'])
        identity['rr']['rfdetr_checkpoint_md5'] = md5
        identity['rr']['rfdetr_checkpoint_md5_ok'] = md5 == RFDETR_BASE_MD5
        if md5 != RFDETR_BASE_MD5:
            raise SystemExit(f'NOT DONE — RR rf-detr-base.pth md5 {md5!r} != registry '
                             f'{RFDETR_BASE_MD5} (rfdetr 1.5.2 lineage): wrong or absent weights.')
    else:
        per_worker = await li_readbacks(arm)
        if len(per_worker) < (arm.declared_workers or 1):
            raise SystemExit(f'NOT DONE — only {len(per_worker)}/{arm.declared_workers} LI '
                             'workers answered /health: absent workers fail before agreement.')
        readbacks.update({k: {'env': v['env'], 'torch_num_threads': v['torch_num_threads']}
                          for k, v in per_worker.items()})
        impls = {v['detect_impl'] for v in per_worker.values()}
        identity['li'] = {'detect_impl': sorted(impls),
                          'versions': next(iter(per_worker.values()))['versions']}
        if impls != {'rfdetr'}:
            raise SystemExit(f'NOT DONE — LI detect_impl read back as {impls}, not rfdetr.')
        md5 = rfdetr_checkpoint_md5(args.li_container, RFDETR_PATHS['li'])
        identity['li']['rfdetr_checkpoint_md5'] = md5
        identity['li']['rfdetr_checkpoint_md5_ok'] = md5 == RFDETR_BASE_MD5
        if md5 != RFDETR_BASE_MD5:
            raise SystemExit(f'NOT DONE — LI rf-detr-base.pth md5 {md5!r} != registry '
                             f'{RFDETR_BASE_MD5}: wrong or absent weights.')

    # Crossroad 17: per-arm declared-vs-measured; asymmetry across arms is a
    # recorded value, never a failure. Undeclared drift (#37) still fails.
    arm_label = 'rr' if rr_arm_active else 'li'
    container = args.rr_container if rr_arm_active else args.li_container
    pins = gs.thread_pins_by_arm({arm_label: readbacks},
                                 {arm_label: container_declared_threads(container)})
    if pins['PASS'] is not True:
        raise SystemExit(f'NOT DONE — thread pins (declared vs measured, per arm): '
                         f'{json.dumps(pins)}')

    return pf_extra | {'manifest_meta': meta, 'rows': rows, 'readbacks': readbacks,
            'identity': identity, 'thread_pin_parity': pins,
            'pipe_sha256': sha256_bytes(PIPE_PATH.read_bytes()),
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

    async def one(row):
        nonlocal consecutive_failures
        if row['file'] in done or stop.is_set():
            return
        blob = (corpus_dir / row['file']).read_bytes()
        enqueue_ns = time.monotonic_ns()          # stamped BEFORE admission (#29)
        async with sem:
            if stop.is_set():
                return
            admit_ns = time.monotonic_ns()        # stamped at admission (#29)
            rec = {'video': row['file'], 'role': row['role'],
                   'submitted_sha256': sha256_bytes(blob), 'bytes': len(blob),
                   'expected_frames': expected_frames(row, interval_s),
                   'video_s_manifest': row.get('video_s'),
                   'enqueue_ns': enqueue_ns, 'admit_ns': admit_ns}
            try:
                body = await arm.process(blob, row['file'])
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
                blob = (corpus_dir / rep['file']).read_bytes()
                enqueue_ns = time.monotonic_ns()
                async with sem:
                    admit_ns = time.monotonic_ns()
                    rec = {'video': rep_key, 'role': 'determinism_repeat',
                           'submitted_sha256': sha256_bytes(blob), 'bytes': len(blob),
                           'expected_frames': expected_frames(rep, interval_s),
                           'enqueue_ns': enqueue_ns, 'admit_ns': admit_ns}
                    try:
                        rec.update(await arm.process(blob, rep['file']))
                        rec['done_ns'] = time.monotonic_ns()
                        rec['wall_s'] = round((rec['done_ns'] - admit_ns) / 1e9, 2)
                    except Exception as exc:  # noqa: BLE001
                        rec['error'] = repr(exc)
                        rec['done_ns'] = time.monotonic_ns()
                    writer.write(rec)
    else:
        await asyncio.gather(*[one(row) for row in rows])
    return {'aborted_by_breaker': stop.is_set()}


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
                r.get('frame_label_multisets') or [], mate.get('frame_label_multisets') or [])
        agreement = {'PASS': bool(per_video) and all(v['PASS'] is True for v in per_video.values()),
                     'armed_by_probe_run': gate3_armed,
                     'n_videos': len(per_video),
                     'failing': [v for v, g in per_video.items() if g['PASS'] is not True] or None,
                     'per_video': per_video}
        if agreement['failing']:
            # Diagnostic triage only — never a verdict (only a human downgrades,
            # in writing, with the reason; first hypothesis is a REAL difference).
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

async def amain() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--arm', choices=['rocketride', 'llamaindex'])
    ap.add_argument('--posture', choices=['default', 'parity'], default='default',
                    help='RocketRide only; Crossroad 9 runs BOTH, one at a time')
    ap.add_argument('--leg', choices=['sequential', 'blast'])
    ap.add_argument('--n', type=int, help='measured videos (prefix of manifest measured rows)')
    ap.add_argument('--blast-concurrency', type=int)
    ap.add_argument('--tokens', type=int, help='parity posture M (default: LI declared_workers)')
    ap.add_argument('--threads', type=int, help='parity posture per-token threads= (default: unset)')
    ap.add_argument('--manifest', default=str(MANIFEST_DEFAULT))
    ap.add_argument('--corpus-dir', default=str(ROOT / 'corpus' / 'ami' / 'video'))
    ap.add_argument('--interval-s', type=int, default=15)
    ap.add_argument('--rr-port', type=int, default=5565)
    ap.add_argument('--li-port', type=int, default=8802)
    ap.add_argument('--rr-container', default='rr')
    ap.add_argument('--li-container', default='li_video')
    ap.add_argument('--out-dir', default=None)
    ap.add_argument('--skip-cache-drop', action='store_true',
                    help='wiring tests only — measured runs must evict and prove it')
    ap.add_argument('--skip-warmup', action='store_true',
                    help='resume aid ONLY — a fresh container without warm-up is not measurable')
    ap.add_argument('--no-collector', action='store_true')
    ap.add_argument('--char-tol', type=float, default=0.02)
    ap.add_argument('--max-preleg-load1', type=float, default=2.0,
                    help='quiet-box gate: refuse to start with load1 above this '
                         '(hygiene bound, not probe-derived — idle box is <1)')
    ap.add_argument('--allow-noisy-box', action='store_true',
                    help='override the quiet-box gate; the override is recorded in the export')
    ap.add_argument('--liveness-min-fraction', type=float, default=None,
                    help='gate 5 threshold — PROBE-DERIVED, no default; absent = gate NOT RUN')
    ap.add_argument('--gate3-armed', default=None, metavar='PROBE_RUN_ID',
                    help='arm strict cross-arm detection agreement; the id names the probe '
                         'run whose ES2002a comparison confirmed — absent = gate NOT RUN')
    ap.add_argument('--cross', nargs=2, metavar=('RR_JSONL', 'LI_JSONL'),
                    help='cross-arm gates over two completed record files; no run')
    args = ap.parse_args()

    if args.cross:
        out = cross_gates(Path(args.cross[0]), Path(args.cross[1]), args.char_tol,
                          gate3_armed=args.gate3_armed)
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

    # ---- arm + posture ----------------------------------------------------
    li_probe = LIArm(args.li_port)
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
    rows_all = pf['rows']
    measured = [r for r in rows_all if r['role'] == 'measured'][:args.n]
    warm = [r for r in rows_all if r['role'] == 'warm']
    if len(measured) < args.n:
        raise SystemExit(f'NOT DONE — manifest has {len(measured)} measured rows, --n {args.n}')

    if args.arm == 'rocketride':
        await arm.start()
        if posture.name == 'parity' and len(warm) < posture.tokens:
            raise SystemExit(f'NOT DONE — {len(warm)} warm rows < {posture.tokens} tokens: '
                             'every token must see at least one warm item.')

    (out_dir / 'preflight.json').write_text(json.dumps(
        {k: v for k, v in pf.items() if k != 'rows'} | {'posture': posture.label()}, indent=1))
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
        say(f'warm-up: {len(warm)} disjoint items')
        seen_pids, seen_tokens = set(), set()
        conc = posture.tokens if args.arm == 'rocketride' else (arm.declared_workers or 1)
        sem = asyncio.Semaphore(max(1, conc))

        async def warm_one(row):
            async with sem:
                blob = (Path(args.corpus_dir) / row['file']).read_bytes()
                try:
                    rec = await arm.process(blob, row['file'])
                    if rec.get('serving_pid'):
                        seen_pids.add(rec['serving_pid'])
                    if rec.get('token_index') is not None:
                        seen_tokens.add(rec['token_index'])
                except Exception as exc:  # noqa: BLE001
                    say(f'warm-up failure on {row["file"]}: {exc!r} (recorded, continuing)')

        await asyncio.gather(*[warm_one(r) for r in warm])
        if args.arm == 'rocketride' and len(seen_tokens) < posture.tokens:
            raise SystemExit(f'NOT DONE — warm-up touched {len(seen_tokens)}/{posture.tokens} '
                             'tokens; every instance must be warm before timing.')
        if args.arm == 'llamaindex' and len(seen_pids) < (arm.declared_workers or 1):
            raise SystemExit(f'NOT DONE — warm-up observed {len(seen_pids)}/{arm.declared_workers} '
                             'worker pids serving (#21-class): unwarmed workers would serve '
                             'measured traffic cold.')
        say(f'warm-up complete: tokens={sorted(seen_tokens) or "n/a"} '
            f'worker_pids={len(seen_pids) or "n/a"}')

    # ---- the leg, under the collector -------------------------------------
    rec_path = out_dir / f'records_{arm.name}_{posture.name}_{args.leg}.jsonl'
    prior, done_keys, torn = read_completed(rec_path, key='video')
    if prior:
        say(f'resume: {len(done_keys)} videos already recorded'
            + (f' (torn last line tolerated: {torn})' if torn else ''))

    collector = None
    if not args.no_collector:
        from harness.collector_proc import ProcessCollector
        container = args.rr_container if args.arm == 'rocketride' else args.li_container
        root_pid = docker_inspect(container, '{{.State.Pid}}')
        roles = {'driver': {'pids': [os.getpid()]}}
        if root_pid and root_pid.isdigit():
            roles['service'] = {'pids': [int(root_pid)]}
        else:
            raise SystemExit(f'NOT DONE — cannot resolve container root pid for {container!r}; '
                             'the collector must sample the service or nothing is quotable.')
        collector = ProcessCollector(out_dir / f'collector_{arm.name}_{args.leg}.jsonl',
                                     roles, interval_s=0.5)
        collector.start()

    t_leg0 = time.monotonic()
    dr0 = resource.getrusage(resource.RUSAGE_SELF)
    with JsonlWriter(rec_path) as writer:
        leg_meta = await run_leg(arm, measured, args.leg,
                                 args.blast_concurrency or 1,
                                 Path(args.corpus_dir), writer, done_keys,
                                 args.interval_s)
    leg_wall = time.monotonic() - t_leg0
    dr1 = resource.getrusage(resource.RUSAGE_SELF)
    if collector:
        collector.stop()
    await arm.stop()

    # ---- gates + export ---------------------------------------------------
    records, _, _ = read_completed(rec_path, key='video')
    gates = leg_gates(records, measured, arm.name, args.interval_s,
                      liveness_min_fraction=args.liveness_min_fraction)
    # Gate 2 attribution (RR): capture the container log and scrape for the
    # detect node's drop warning — with a channel-liveness marker so a dead
    # log can never read as 'no drops'. Detector = gate 1; this ATTRIBUTES.
    if args.arm == 'rocketride':
        log_file = out_dir / f'dockerlog_{args.rr_container}_{args.leg}.txt'
        try:
            log_text = subprocess.run(['docker', 'logs', args.rr_container],
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
        warmup_policy=f'driver-side, {len(warm)} disjoint manifest warm rows, '
                      f'coverage proven per instance',
        timeout_s=7200,
        parser=f'ffmpeg fps=1/{args.interval_s} + rfdetr(RF-DETR base, thr 0.3)',
        chunk_size=measured_chunk_size or -1,   # FROM RECORDS; -1 = no records, unmissable
        chunk_overlap=0,
        embedding_model=EMBED_MODEL,
        container=(args.rr_container if args.arm == 'rocketride' else args.li_container),
        splitter=('RecursiveCharacterTextSplitter' if args.arm == 'rocketride'
                  else 'SentenceSplitter(native, char length function supplied)'),
    )
    window = steady_window(records, args.blast_concurrency or 1)
    ok_frames = sum(r.get('frames_observed') or 0 for r in ok_records)
    ok_video_s = sum(r.get('video_s_manifest') or 0 for r in ok_records)
    export = {
        'arm': arm.name, 'posture': posture.label(), 'leg': args.leg,
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
            'posture': {'name': posture.name, 'tokens': posture.tokens,
                        'threads_config': posture.threads,
                        'threads_note': ('unset -> engine CONST_DEFAULT_MAX_THREADS=64 '
                                         '(constants.py:48)' if posture.threads is None else
                                         'explicit use(threads=)')},
            'identity_readback': pf['identity'],
            'thread_pins_by_arm': pf['thread_pin_parity'],
            'interval_s': args.interval_s,
            'frames_observed_method': ('bracket-count' if args.arm == 'rocketride'
                                       else 'extractor-count'),
            'chunk_config_source': 'measured from records (config literal never exported)',
        },
    }
    # Structural guard: a blast export without window_n must be impossible.
    assert 'steady_window' in export['throughput'] and (
        export['throughput']['steady_window'].get('defined') is False
        or 'window_n' in export['throughput']['steady_window']), 'window_n missing'
    export_path = out_dir / f'export_{arm.name}_{posture.name}_{args.leg}.json'
    export_path.write_text(json.dumps(export, indent=1))
    say(f'export: {export_path}')
    if driver_share and driver_share > 0.01:
        say(f'WARNING: driver CPU share {driver_share:.1%} > 1% — report it; '
            'pinning gets reinstated if this holds (environment rule)')

    hard = [k for k, g in gates.items()
            if isinstance(g, dict) and g.get('PASS') is False]
    if hard:
        say(f'GATES FAILED: {hard}')
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(asyncio.run(amain()))
