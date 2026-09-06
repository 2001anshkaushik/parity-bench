#!/usr/bin/env python3
"""lifetime_state — the filesystem-vs-process discriminator (ruling 2026-09-06,
TASK 1), measured never assumed, basis stated on every number.

Two mechanisms can produce a monotone per-film slowdown that PERSISTS into
the next pass and look identical from outside:
  * PROCESS state — allocator arenas, fragmentation, retained per-frame state
    in the engine's processes (§6 residual candidate #3);
  * FILESYSTEM state — both arms spool every video to the container's /tmp
    (RR: engine/ai/common/avi/reader.py:425 NamedTemporaryFile, no dir, no
    TMPDIR in the image => /tmp, removed in Reader.__del__; LI:
    li_video/service.py:164 ws1v_spool_*.vid, unlinked at :190) and delete
    it — ~500 GB of write-and-delete churn per campaign on the overlay
    writable layer, i.e. on the host filesystem under the docker root.
    Free-space scattering there slows allocation for EVERY later writer.
A fresh container on the SAME dirty filesystem starts slow if it is the
filesystem and starts fast if it is process state. This module makes both
sides readable at leg start and leg end, in every export:

  read_state(containers, spool_paths, host_paths) ->
    containers[c].spool  : df of each spool path INSIDE the container (the
                           overlay the engine writes to), du + file count of
                           the path (spool in flight / leaked), /proc/mounts
                           lines proving the path is on the writable layer
    containers[c].cgroup : memory.current / anon / file (mem_watch bases)
    containers[c].procs  : sum of VmRSS/RssAnon/VmData/VmSize over every
                           process in the container + the top-N processes by
                           RSS with cmdline (server vs token processes,
                           separable) — the direct read on the process side
    containers[c].layer  : docker ps -s writable-layer size (spool + logs)
    host.df[name]        : statvfs of the docker root, corpus dir, /tmp,
                           out dir (bytes; device + fstype from df -P)
    host.frag            : free-space fragmentation proxy for the docker-root
                           device — ext4: /proc/fs/ext4/<dev>/mb_groups
                           (world-readable; the buddy histogram e2freefrag
                           reports), plus `sudo -n e2freefrag` best-effort;
                           xfs: xfs_spaceman freesp -s best-effort. State is
                           ALWAYS recorded ('measured' / 'unavailable: why')
                           — a null that means "could not look" must never
                           read as "nothing there" (mem_watch's silent-gap
                           class, register entry 31).
    host.diskstats       : /proc/diskstats for the device (sectors read /
                           written, io ms) — start->end delta = the churn
                           volume the leg actually wrote
    host.psi_io          : /proc/pressure/io if present

  FsSampler                : 5 s statvfs stream of the host paths under the leg
                           (the spool high-water at filesystem level — the
                           campaign never collected a per-film spool figure;
                           the nearest held instrument was mem_watch's 5 s df
                           in the sweep, not run in the campaign)
  service_memory_trajectory(collector_jsonl) : first/last-5-min means, max,
                           time-quartile means of the service role's rss /
                           cg_anon / cg_current / n_procs from the collector
                           stream the driver already runs in every leg

Self-test (laptop, no docker): --self-test.  Startup check (box, before any
leg — entry 31: a new tool with no startup check is how a measured absence
goes unapplied): --check [--docker-root auto] [--paths name=path ...].
One-off read: --read --containers a,b --spool-paths /tmp --paths ...
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import shutil
import statistics
import subprocess
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional

SEP = '=====LSTATE====='
EXT4_ORDERS = 14          # mb_groups histogram columns 2^0 .. 2^13 blocks
EXT4_BLOCK = 4096

BASIS = {
    'spool_df': 'df -kP of the spool path INSIDE the container (the overlay the engine '
                'writes to; size/used/avail in KiB as the engine sees them)',
    'spool_du': 'du -sk + `find -type f | wc -l` of the spool path inside the container — '
                'spool in flight at the instant of the read; at leg END (before the tokens '
                'are terminated) a non-zero count is a spool LEAK',
    'mounts': '/proc/mounts lines for / and the spool path inside the container — a spool '
              'path with no mount of its own lives on the writable layer (host fs under '
              'the docker root)',
    'cgroup': 'cgroup v2 memory.current (incl. page cache) / memory.stat anon (OOM-relevant) '
              '/ file (reclaimable), read inside the container',
    'procs': 'sum over every /proc/[0-9]*/status in the container of VmRSS, RssAnon, VmData, '
             'VmSize (KiB) + n processes; top_by_rss lists the largest with cmdline so the '
             'persistent engine server and the per-token processes are separable',
    'layer': 'docker ps -s SIZE: the writable layer (spool + container logs + anything '
             'written), first token; virtual size second',
    'host_df': 'os.statvfs of each host path: total/free/avail/used bytes; device and '
               'fstype from df -P',
    'frag_ext4': '/proc/fs/ext4/<dev>/mb_groups summed over block groups: free blocks, free '
                 'fragments, avg free extent KiB, per-order histogram (count of free '
                 'extents of 2^k blocks), share of free blocks in extents >= 2^10 blocks '
                 '(4 MiB; lower bound from the histogram) — e2freefrag\'s data source',
    'frag_tool': 'e2freefrag / xfs_spaceman text, best-effort via sudo -n; state recorded',
    'diskstats': '/proc/diskstats row for the device: reads, sectors_read, writes, '
                 'sectors_written, io_ms (cumulative; leg delta = churn volume)',
    'fs_stream': 'statvfs of the host paths every period_s under the leg: used/avail '
                 'bytes; summary = start/end/max used, min avail per path',
    'service_memory_trajectory': 'collector role_tick rows for role=service: first 5 min '
                                 'mean -> last 5 min mean, max, time-quartile means, for '
                                 'rss / vms / cg_anon / cg_current / n_procs',
}

# ---------------------------------------------------------------------------
# container side: ONE docker exec per container, sh only (no procps; the li
# image is python:3.12-slim — mem_watch's lesson)
# ---------------------------------------------------------------------------

def _probe_sh(spool_paths: List[str], top_n: int) -> str:
    parts = []
    for p in spool_paths:
        parts.append(f"echo PATH {p}; df -kP {p} 2>/dev/null | tail -1; echo {SEP}; "
                     f"du -sk {p} 2>/dev/null | cut -f1; echo {SEP}; "
                     f"find {p} -type f 2>/dev/null | wc -l; echo {SEP}; "
                     f"grep -E ' (/|{p}) ' /proc/mounts 2>/dev/null; echo {SEP}; ")
    parts.append(
        f"echo CGROUP; cat /sys/fs/cgroup/memory.current 2>/dev/null; echo {SEP}; "
        f"grep -E '^(anon|file) ' /sys/fs/cgroup/memory.stat 2>/dev/null; echo {SEP}; "
        "echo PROCS; for d in /proc/[0-9]*; do "
        "[ \"$d\" = \"/proc/$$\" ] && continue; "
        "s=$(grep -E '^(VmRSS|RssAnon|VmData|VmSize):' \"$d/status\" 2>/dev/null | "
        "tr -s ' \\t' ' ' | tr '\\n' ' ') || continue; [ -n \"$s\" ] || continue; "
        "c=$(tr '\\0' ' ' < \"$d/cmdline\" 2>/dev/null | cut -c1-160); "
        f"echo \"P ${{d#/proc/}} | $s| $c\"; done; echo {SEP}; echo TOPN {top_n}")
    return ''.join(parts)


def parse_container_probe(text: str, spool_paths: List[str], top_n: int = 6) -> dict:
    out: dict = {'spool': {}, 'cgroup': {'memory_current': None, 'anon': None, 'file': None},
                 'procs': {'n': None, 'vmrss_kb': None, 'rssanon_kb': None, 'vmdata_kb': None,
                           'vmsize_kb': None, 'top_by_rss': [], 'state': 'unavailable'}}
    if not text.strip():
        for p in spool_paths:
            out['spool'][p] = {'state': 'unavailable: probe produced no output'}
        return out
    # spool sections: 'PATH <p>' then 4 SEP-delimited sections
    for p in spool_paths:
        m = re.search(r'^PATH ' + re.escape(p) + r'\n(.*?)\n' + re.escape(SEP) + r'\n(.*?)\n'
                      + re.escape(SEP) + r'\n(.*?)\n' + re.escape(SEP) + r'\n(.*?)' + re.escape(SEP),
                      text, re.S | re.M)
        if not m:
            out['spool'][p] = {'state': 'unavailable: section missing'}
            continue
        df, du, nf, mounts = (m.group(i).strip() for i in (1, 2, 3, 4))
        rec: dict = {'state': 'measured'}
        cols = df.split()
        if len(cols) >= 6 and cols[1].isdigit():
            rec.update({'fs': cols[0], 'size_kb': int(cols[1]), 'used_kb': int(cols[2]),
                        'avail_kb': int(cols[3]), 'mounted_on': cols[5]})
        else:
            rec['state'] = 'partial: df unparsed'
        rec['du_kb'] = int(du) if du.isdigit() else None
        rec['n_files'] = int(nf) if nf.isdigit() else None
        rec['mounts'] = [l for l in mounts.splitlines() if l.strip()]
        rec['on_writable_layer'] = (not any(f' {p} ' in l for l in rec['mounts'])
                                    if rec['mounts'] else None)
        out['spool'][p] = rec
    cg = re.search(r'^CGROUP\n(.*?)\n' + re.escape(SEP) + r'\n(.*?)' + re.escape(SEP), text, re.S | re.M)
    if cg:
        cur = cg.group(1).strip()
        out['cgroup']['memory_current'] = int(cur) if cur.isdigit() else None
        for line in cg.group(2).splitlines():
            mm = re.match(r'^(anon|file)\s+(\d+)$', line.strip())
            if mm:
                out['cgroup'][mm.group(1)] = int(mm.group(2))
    pr = re.search(r'^PROCS\n(.*?)' + re.escape(SEP), text, re.S | re.M)
    if pr:
        rows = []
        for line in pr.group(1).splitlines():
            if not line.startswith('P '):
                continue
            head, _, cmd = line[2:].partition('| ')
            pid = head.strip()
            fields = {k: int(v) for k, v in re.findall(r'(VmRSS|RssAnon|VmData|VmSize): (\d+) kB', line)}
            if 'VmRSS' not in fields:
                continue
            rows.append({'pid': int(pid) if pid.isdigit() else pid, **{k.lower(): v for k, v in fields.items()},
                         'cmd': cmd.rsplit('| ', 1)[-1].strip()[:160]})
        out['procs'] = {
            'n': len(rows),
            'vmrss_kb': sum(r.get('vmrss', 0) for r in rows),
            'rssanon_kb': sum(r.get('rssanon', 0) for r in rows) if any('rssanon' in r for r in rows) else None,
            'vmdata_kb': sum(r.get('vmdata', 0) for r in rows),
            'vmsize_kb': sum(r.get('vmsize', 0) for r in rows),
            'top_by_rss': sorted(rows, key=lambda r: -r.get('vmrss', 0))[:top_n],
            'state': 'measured' if rows else 'zero-matching',
        }
    return out


def _docker(args: List[str], timeout: int = 30) -> Optional[str]:
    try:
        p = subprocess.run(['docker', *args], capture_output=True, text=True, timeout=timeout)
        return p.stdout if p.returncode == 0 else None
    except Exception:
        return None


def read_container(container: str, spool_paths: List[str], top_n: int = 6) -> dict:
    try:
        p = subprocess.run(['docker', 'exec', container, 'sh', '-c', _probe_sh(spool_paths, top_n)],
                           capture_output=True, text=True, timeout=60)
        rec = parse_container_probe(p.stdout if p.returncode == 0 else '', spool_paths, top_n)
        rec['exec_rc'] = p.returncode
    except (subprocess.TimeoutExpired, OSError) as exc:
        rec = parse_container_probe('', spool_paths, top_n)
        rec['exec_rc'] = -1
        rec['error'] = repr(exc)
    size = _docker(['ps', '-s', '--no-trunc', '-f', f'name=^{container}$', '--format', '{{.Size}}'])
    rec['layer'] = {'size': (size or '').strip() or None,
                    'state': 'measured' if size and size.strip() else 'unavailable: docker ps -s empty'}
    mounts = _docker(['inspect', '-f', '{{json .Mounts}}', container])
    try:
        rec['docker_mounts'] = json.loads(mounts) if mounts else None
    except json.JSONDecodeError:
        rec['docker_mounts'] = None
    rec['graph_driver'] = (_docker(['inspect', '-f', '{{.GraphDriver.Name}}', container]) or '').strip() or None
    return rec


# ---------------------------------------------------------------------------
# host side
# ---------------------------------------------------------------------------

def docker_root() -> Optional[str]:
    out = _docker(['info', '-f', '{{.DockerRootDir}}'])
    return out.strip() if out and out.strip() else None


def statvfs_bytes(path: str) -> dict:
    try:
        s = os.statvfs(path)
    except OSError as exc:
        return {'state': f'unavailable: {exc.__class__.__name__}: {exc}'}
    total = s.f_blocks * s.f_frsize
    free = s.f_bfree * s.f_frsize
    return {'state': 'measured', 'total_bytes': total, 'free_bytes': free,
            'avail_bytes': s.f_bavail * s.f_frsize, 'used_bytes': total - free,
            'inodes_free': s.f_ffree, 'inodes_total': s.f_files}


def df_device(path: str) -> dict:
    """device + fstype + mount point for a path, from df -P/-T (GNU or busybox)."""
    for argv in (['df', '-PT', path], ['df', '-P', path]):
        try:
            p = subprocess.run(argv, capture_output=True, text=True, timeout=20)
        except Exception:
            continue
        if p.returncode != 0:
            continue
        lines = [l for l in p.stdout.splitlines() if l.strip()]
        if len(lines) < 2:
            continue
        cols = lines[-1].split()
        if argv[1] == '-PT' and len(cols) >= 7:
            return {'device': cols[0], 'fstype': cols[1], 'mount': cols[6]}
        if len(cols) >= 6:
            return {'device': cols[0], 'fstype': None, 'mount': cols[5]}
    return {'device': None, 'fstype': None, 'mount': None}


def parse_mb_groups(text: str) -> dict:
    groups = 0
    free = frags = 0
    hist = [0] * EXT4_ORDERS
    for line in text.splitlines():
        m = re.match(r'^#(\d+)\s*:\s*(\d+)\s+(\d+)\s+(\d+)\s*\[(.*)\]', line)
        if not m:
            continue
        groups += 1
        free += int(m.group(2))
        frags += int(m.group(3))
        counts = [int(x) for x in m.group(5).split()]
        for i, c in enumerate(counts[:EXT4_ORDERS]):
            hist[i] += c
    if groups == 0:
        return {'state': 'unavailable: no group rows parsed'}
    big = sum(hist[k] * (1 << k) for k in range(10, EXT4_ORDERS))   # >= 2^10 blocks = 4 MiB
    return {'state': 'measured', 'groups': groups, 'free_blocks': free, 'free_fragments': frags,
            'avg_free_extent_kb': round(free / frags * EXT4_BLOCK / 1024, 1) if frags else None,
            'hist_by_order': hist,
            'free_share_in_extents_ge_4mib_lower_bound': round(big / free, 4) if free else None}


def _sudo_text(argv: List[str], timeout: int = 120) -> dict:
    """best-effort: plain, then sudo -n; the state says which (or why neither)."""
    if shutil.which(argv[0]) is None:
        return {'state': f'unavailable: {argv[0]} not installed'}
    for pre in ([], ['sudo', '-n']):
        try:
            p = subprocess.run([*pre, *argv], capture_output=True, text=True, timeout=timeout)
        except Exception as exc:
            return {'state': f'unavailable: {exc!r}'}
        if p.returncode == 0 and p.stdout.strip():
            return {'state': 'measured' + (' (sudo -n)' if pre else ''), 'text': p.stdout[-4000:]}
        last = (p.stderr or p.stdout).strip()[-300:]
    return {'state': f'unavailable: rc!=0 plain and sudo -n: {last}'}


def frag_proxy(device: Optional[str], fstype: Optional[str], mount: Optional[str]) -> dict:
    out: dict = {'device': device, 'fstype': fstype, 'mount': mount}
    ext4_dir = Path('/proc/fs/ext4')
    cands = []
    if device:
        cands.append(Path(device).name)
    if ext4_dir.is_dir():
        listed = sorted(p.name for p in ext4_dir.iterdir())
        out['proc_fs_ext4_entries'] = listed
        if len(listed) == 1 and listed[0] not in cands:
            cands.append(listed[0])          # /dev/root style df names; one ext4 fs on the box
    out['mb_groups'] = {'state': 'unavailable: no /proc/fs/ext4/<dev>/mb_groups readable'}
    for name in cands:
        mb = ext4_dir / name / 'mb_groups'
        try:
            txt = mb.read_text()
        except OSError:
            continue
        out['mb_groups'] = {'source': str(mb), **parse_mb_groups(txt)}
        break
    if (fstype or '').startswith('ext') and device:
        out['e2freefrag'] = _sudo_text(['e2freefrag', device])
    elif fstype == 'xfs' and mount:
        out['xfs_spaceman'] = _sudo_text(['xfs_spaceman', '-c', 'freesp -s', mount])
    else:
        out['tool'] = {'state': f'unavailable: fstype {fstype!r} — no tool wired'}
    return out


def diskstats(device: Optional[str]) -> dict:
    if not device:
        return {'state': 'unavailable: no device'}
    name = Path(device).name
    try:
        txt = Path('/proc/diskstats').read_text()
    except OSError as exc:
        return {'state': f'unavailable: {exc}'}
    for line in txt.splitlines():
        f = line.split()
        if len(f) >= 14 and f[2] == name:
            return {'state': 'measured', 'device': name, 'reads': int(f[3]), 'sectors_read': int(f[5]),
                    'writes': int(f[7]), 'sectors_written': int(f[9]), 'io_ms': int(f[12]),
                    'note': 'sectors are 512 B'}
    return {'state': f'unavailable: {name} not in /proc/diskstats'}


def psi_io() -> dict:
    try:
        return {'state': 'measured', 'text': Path('/proc/pressure/io').read_text().strip()}
    except OSError:
        return {'state': 'unavailable: no /proc/pressure/io'}


def read_host(host_paths: Dict[str, str]) -> dict:
    out: dict = {'df': {}, 'docker_root': docker_root()}
    for name, path in host_paths.items():
        out['df'][name] = {'path': path, **statvfs_bytes(path), **df_device(path)}
    root = out['docker_root']
    dev = (out['df'].get('docker_root') or df_device(root) if root else {}) or {}
    if root and 'docker_root' not in host_paths:
        out['df']['docker_root'] = {'path': root, **statvfs_bytes(root), **df_device(root)}
        dev = out['df']['docker_root']
    out['frag'] = frag_proxy(dev.get('device'), dev.get('fstype'), dev.get('mount'))
    out['diskstats'] = diskstats(dev.get('device'))
    out['psi_io'] = psi_io()
    return out


def read_state(containers: List[str], spool_paths: List[str], host_paths: Dict[str, str],
               phase: str, top_n: int = 6) -> dict:
    t0 = time.monotonic()
    state = {'phase': phase, 'taken_utc': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
             'containers': {c: read_container(c, spool_paths, top_n) for c in containers},
             'host': read_host(host_paths)}
    state['read_cost_s'] = round(time.monotonic() - t0, 2)
    return state


# ---------------------------------------------------------------------------
# the 5 s host-fs stream under the leg
# ---------------------------------------------------------------------------

class FsSampler:
    def __init__(self, host_paths: Dict[str, str], out_path: Path, period_s: float = 5.0):
        self.paths = dict(host_paths)
        self.out_path = Path(out_path)
        self.period_s = period_s
        self.rows: List[dict] = []
        self._task: Optional[asyncio.Task] = None
        self._t0 = time.monotonic()

    def _row(self) -> dict:
        row = {'t': round(time.monotonic() - self._t0, 1),
               'utc': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}
        for name, path in self.paths.items():
            s = statvfs_bytes(path)
            row[name] = ({'used': s['used_bytes'], 'avail': s['avail_bytes']}
                         if s.get('state') == 'measured' else {'state': s.get('state')})
        return row

    async def _run(self) -> None:
        with open(self.out_path, 'a') as fh:
            while True:
                row = self._row()
                self.rows.append(row)
                fh.write(json.dumps(row) + '\n')
                fh.flush()
                await asyncio.sleep(self.period_s)

    def start(self) -> None:
        self.out_path.unlink(missing_ok=True)
        self._task = asyncio.create_task(self._run())

    async def stop(self) -> dict:
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except (asyncio.CancelledError, Exception):
                pass
        return self.summary()

    def summary(self) -> dict:
        out = {'basis': BASIS['fs_stream'], 'period_s': self.period_s, 'n': len(self.rows),
               'path': str(self.out_path), 'paths': {}}
        for name in self.paths:
            used = [r[name]['used'] for r in self.rows if isinstance(r.get(name), dict) and 'used' in r[name]]
            avail = [r[name]['avail'] for r in self.rows if isinstance(r.get(name), dict) and 'avail' in r[name]]
            if not used:
                out['paths'][name] = {'state': 'unavailable'}
                continue
            out['paths'][name] = {'state': 'measured', 'start_used': used[0], 'end_used': used[-1],
                                  'max_used': max(used), 'min_avail': min(avail),
                                  'max_used_minus_start': max(used) - used[0]}
        return out


# ---------------------------------------------------------------------------
# the process-side trajectory, from the collector stream every leg already has
# ---------------------------------------------------------------------------

def service_memory_trajectory(collector_jsonl: Path, edge_s: float = 300.0) -> dict:
    try:
        rows = [json.loads(l) for l in Path(collector_jsonl).read_text().splitlines() if l.strip()]
    except (OSError, json.JSONDecodeError) as exc:
        return {'state': f'unavailable: {exc.__class__.__name__}'}
    svc = [r for r in rows if r.get('kind') == 'role_tick' and r.get('role') == 'service']
    if not svc:
        return {'state': 'unavailable: no service role_tick rows'}
    t_first, t_last = svc[0]['t'], svc[-1]['t']
    first = [r for r in svc if r['t'] <= t_first + edge_s]
    last = [r for r in svc if r['t'] >= t_last - edge_s]
    out: dict = {'state': 'measured', 'basis': BASIS['service_memory_trajectory'],
                 'n_ticks': len(svc), 'span_s': round(t_last - t_first, 1), 'edge_s': edge_s}
    for k in ('rss', 'vms', 'cg_anon', 'cg_current', 'n_procs', 'cg_pids_tasks'):
        vals = [r[k] for r in svc if isinstance(r.get(k), (int, float))]
        if not vals:
            continue
        f = [r[k] for r in first if isinstance(r.get(k), (int, float))]
        l = [r[k] for r in last if isinstance(r.get(k), (int, float))]
        n = len(vals)
        out[k] = {'first_mean': round(statistics.mean(f), 1) if f else None,
                  'last_mean': round(statistics.mean(l), 1) if l else None,
                  'max': max(vals),
                  'quartile_means': [round(statistics.mean(vals[i * n // 4:(i + 1) * n // 4]), 1)
                                     for i in range(4)]}
    return out


# ---------------------------------------------------------------------------
# CLI: --check (startup, before any leg), --read, --self-test
# ---------------------------------------------------------------------------

def check_instruments(host_paths: Dict[str, str]) -> int:
    """Prints what the box can and cannot measure. Exit 1 only if the MANDATORY
    readings (statvfs of every named host path, docker root resolvable) fail;
    the fragmentation proxy is best-effort and its absence is recorded, not fatal."""
    h = read_host(host_paths)
    rc = 0
    print(f"docker root: {h['docker_root']}")
    if not h['docker_root']:
        print('NOT DONE — docker root dir unresolvable (docker info)')
        rc = 1
    for name, d in h['df'].items():
        if d.get('state') != 'measured':
            print(f"NOT DONE — statvfs {name}={d.get('path')}: {d.get('state')}")
            rc = 1
        else:
            print(f"  {name}: {d['path']} dev={d.get('device')} fstype={d.get('fstype')} "
                  f"free={d['free_bytes'] / 2**30:.1f} GiB used={d['used_bytes'] / 2**30:.1f} GiB "
                  f"of {d['total_bytes'] / 2**30:.1f} GiB")
    fr = h['frag']
    mb = fr.get('mb_groups', {})
    print(f"  frag proxy mb_groups: {mb.get('state')}"
          + (f" — free {mb['free_blocks'] * EXT4_BLOCK / 2**30:.1f} GiB in {mb['free_fragments']} extents, "
             f"avg {mb['avg_free_extent_kb']} KiB, share in >=4 MiB extents >= {mb['free_share_in_extents_ge_4mib_lower_bound']}"
             if mb.get('state') == 'measured' else ''))
    for tool in ('e2freefrag', 'xfs_spaceman', 'tool'):
        if tool in fr:
            print(f"  frag tool {tool}: {fr[tool].get('state')}")
    print(f"  diskstats: {h['diskstats'].get('state')} | psi io: {h['psi_io'].get('state')}")
    print('lifetime_state check:', 'PASS (mandatory readings measured)' if rc == 0 else 'FAIL')
    return rc


def check_containers(containers: List[str], spool_paths: List[str]) -> int:
    """The container-side probe is sh that has never run anywhere but a Linux
    container: exercise it against the live arm BEFORE any leg and REFUSE
    unless every section measures. A dead probe recording 'unavailable' for
    a 15 h run is the measured-absence class (entry 31), caught here instead."""
    rc = 0
    for c in containers:
        rec = read_container(c, spool_paths)
        bad = []
        if rec.get('exec_rc') != 0:
            bad.append(f"exec rc {rec.get('exec_rc')} {rec.get('error', '')}")
        for p, sp in rec.get('spool', {}).items():
            if sp.get('state') != 'measured' or sp.get('du_kb') is None or sp.get('n_files') is None:
                bad.append(f'spool {p}: {sp.get("state")} du={sp.get("du_kb")} files={sp.get("n_files")}')
        if rec['procs'].get('state') != 'measured':
            bad.append(f"procs: {rec['procs'].get('state')}")
        if rec['cgroup'].get('anon') is None:
            bad.append('cgroup anon unreadable')
        if rec.get('layer', {}).get('state') != 'measured':
            bad.append(f"layer: {rec.get('layer', {}).get('state')}")
        if bad:
            rc = 1
            print(f'NOT DONE — {c}: ' + '; '.join(bad))
        else:
            sp = next(iter(rec['spool'].values()))
            top = rec['procs']['top_by_rss'][0] if rec['procs']['top_by_rss'] else {}
            print(f"  {c}: spool {sp.get('fs')} avail {sp['avail_kb'] / 2**20:.1f} GiB, du {sp['du_kb']} KiB / "
                  f"{sp['n_files']} files, on writable layer={sp.get('on_writable_layer')}; cg anon "
                  f"{rec['cgroup']['anon'] / 2**30:.2f} GiB; procs {rec['procs']['n']} rss "
                  f"{rec['procs']['vmrss_kb'] / 2**20:.2f} GiB (top: {top.get('cmd', '')[:60]!r} "
                  f"{top.get('vmrss', 0) / 2**20:.2f} GiB); layer {rec['layer']['size']}")
    print('lifetime_state container check:', 'PASS' if rc == 0 else 'FAIL')
    return rc


def self_test() -> int:
    ok = True

    def check(name, cond):
        nonlocal ok
        print(f'  {"PASS" if cond else "FAIL"}  {name}')
        ok = ok and cond

    canned = ('PATH /tmp\noverlay 1000000 400000 600000 40% /\n' + SEP + '\n1234\n' + SEP + '\n3\n' + SEP + '\n'
              'overlay / overlay rw 0 0\n' + SEP + '\nCGROUP\n5000\n' + SEP + '\nanon 111\nfile 222\n' + SEP + '\n'
              'PROCS\nP 12 | VmSize: 100 kB VmData: 40 kB VmRSS: 30 kB RssAnon: 20 kB | python node.py\n'
              'P 13 | VmSize: 200 kB VmData: 90 kB VmRSS: 80 kB RssAnon: 70 kB | dist/server/engine\n'
              + SEP + '\nTOPN 6\n')
    r = parse_container_probe(canned, ['/tmp'])
    sp = r['spool']['/tmp']
    check('spool df parsed (size/used/avail KiB, fs)', sp['size_kb'] == 1000000 and sp['used_kb'] == 400000
          and sp['avail_kb'] == 600000 and sp['fs'] == 'overlay' and sp['state'] == 'measured')
    check('spool du/file-count parsed; no own mount => writable layer',
          sp['du_kb'] == 1234 and sp['n_files'] == 3 and sp['on_writable_layer'] is True)
    check('cgroup current/anon/file parsed', r['cgroup'] == {'memory_current': 5000, 'anon': 111, 'file': 222})
    pr = r['procs']
    check('procs summed + top_by_rss ordered (server first) with cmdline',
          pr['n'] == 2 and pr['vmrss_kb'] == 110 and pr['rssanon_kb'] == 90 and pr['vmdata_kb'] == 130
          and pr['top_by_rss'][0]['cmd'] == 'dist/server/engine' and pr['state'] == 'measured')
    empty = parse_container_probe('', ['/tmp'])
    check("empty probe => every section 'unavailable', never zero",
          empty['spool']['/tmp']['state'].startswith('unavailable') and empty['procs']['state'] == 'unavailable'
          and empty['cgroup']['anon'] is None)
    nop = parse_container_probe(canned.replace('P 12 |', 'X').replace('P 13 |', 'X'), ['/tmp'])
    check("procs section ran but matched nothing => 'zero-matching' (distinct from unavailable)",
          nop['procs']['state'] == 'zero-matching' and nop['procs']['n'] == 0)
    mb = parse_mb_groups('#group: free  frags first [ 2^0 2^1 2^2 2^3 2^4 2^5 2^6 2^7 2^8 2^9 2^10 2^11 2^12 2^13 ]\n'
                         '#0    : 20481 3     37    [ 1     0     0     0     1     0     0     0     0     0     0     0     0     2     ]\n'
                         '#1    : 1024  4     0     [ 0     0     0     0     0     0     0     0     0     0     1     0     0     0     ]\n')
    check('mb_groups summed: groups/free/frags/hist/avg extent/>=4MiB share',
          mb['groups'] == 2 and mb['free_blocks'] == 21505 and mb['free_fragments'] == 7
          and mb['hist_by_order'][13] == 2 and mb['hist_by_order'][10] == 1
          and mb['avg_free_extent_kb'] == round(21505 / 7 * 4, 1)
          and mb['free_share_in_extents_ge_4mib_lower_bound'] == round((2 * 8192 + 1024) / 21505, 4))
    check('mb_groups with no rows => unavailable', parse_mb_groups('junk')['state'].startswith('unavailable'))
    here = statvfs_bytes(os.getcwd())
    check('statvfs measured on cwd with used = total - free',
          here['state'] == 'measured' and here['used_bytes'] == here['total_bytes'] - here['free_bytes'])
    check('statvfs on a missing path is an explicit absence',
          statvfs_bytes('/nonexistent/x')['state'].startswith('unavailable'))
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / 'c.jsonl'
        rows = [{'kind': 'role_tick', 'role': 'service', 't': t, 'rss': 100 + t, 'cg_anon': 10 + t, 'n_procs': 3}
                for t in range(0, 1200, 100)] + [{'kind': 'system_tick', 't': 5}]
        p.write_text('\n'.join(json.dumps(r) for r in rows) + '\n')
        tr = service_memory_trajectory(p, edge_s=300)
        check('trajectory: first/last means, max, quartiles from role_tick service rows only',
              tr['state'] == 'measured' and tr['n_ticks'] == 12 and tr['rss']['first_mean'] == 250.0
              and tr['rss']['last_mean'] == 1050.0 and tr['rss']['max'] == 1200
              and tr['rss']['quartile_means'] == [200.0, 500.0, 800.0, 1100.0] and tr['cg_anon']['max'] == 1110)
        check('trajectory on a missing stream is an explicit absence',
              service_memory_trajectory(Path(td) / 'none.jsonl')['state'].startswith('unavailable'))

        async def run_sampler():
            s = FsSampler({'cwd': os.getcwd()}, Path(td) / 'fs.jsonl', period_s=0.05)
            s.start()
            await asyncio.sleep(0.2)
            return await s.stop()
        summ = asyncio.run(run_sampler())
        check('FsSampler streams rows and summarises start/end/max used, min avail',
              summ['n'] >= 3 and summ['paths']['cwd']['state'] == 'measured'
              and summ['paths']['cwd']['max_used'] >= summ['paths']['cwd']['start_used']
              and (Path(td) / 'fs.jsonl').exists())
    check('every reading has a named basis', set(BASIS) >= {'spool_df', 'spool_du', 'mounts', 'cgroup', 'procs',
                                                            'layer', 'host_df', 'frag_ext4', 'frag_tool',
                                                            'diskstats', 'fs_stream', 'service_memory_trajectory'})
    check('container probe is sh-only (no procps: pgrep/ps absent from the slim image)',
          'pgrep' not in _probe_sh(['/tmp'], 6) and ' ps ' not in _probe_sh(['/tmp'], 6))
    # entry 27: every name in the video tree resolves (a missing import passed
    # py_compile and a green self-test once)
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))   # working/
    try:
        from harness.static_names import probe_selftest_findings
        sn = probe_selftest_findings(__file__)
        check('static names: every video-tree name resolves (entry 27)', sn == {})
        if sn:
            print('  UNRESOLVED:', sn)
    except ImportError as exc:
        check(f'static names check importable ({exc})', False)
    print('self-test:', 'PASS' if ok else 'FAIL')
    return 0 if ok else 4


def _parse_paths(items: List[str]) -> Dict[str, str]:
    out = {}
    for it in items or []:
        name, _, path = it.partition('=')
        if not path:
            raise SystemExit(f'NOT DONE — --paths wants name=path, got {it!r}')
        out[name] = path
    return out


def main() -> int:
    ap = argparse.ArgumentParser(allow_abbrev=False)
    ap.add_argument('--self-test', action='store_true')
    ap.add_argument('--check', action='store_true', help='startup instrument check (box)')
    ap.add_argument('--read', action='store_true', help='one-off read_state, JSON to stdout')
    ap.add_argument('--check-containers', default=None,
                    help='comma-separated LIVE containers: run the probe, refuse unless it measures')
    ap.add_argument('--containers', default='', help='comma-separated container names (--read)')
    ap.add_argument('--spool-paths', default='/tmp', help='comma-separated in-container paths')
    ap.add_argument('--paths', nargs='*', default=[], help='host paths as name=path')
    ap.add_argument('--phase', default='oneoff')
    args = ap.parse_args()
    if args.self_test:
        return self_test()
    paths = _parse_paths(args.paths)
    if args.check_containers:
        return check_containers([c for c in args.check_containers.split(',') if c.strip()],
                                [p for p in args.spool_paths.split(',') if p])
    if args.check:
        return check_instruments(paths)
    if args.read:
        containers = [c for c in args.containers.split(',') if c.strip()]
        st = read_state(containers, [p for p in args.spool_paths.split(',') if p], paths, args.phase)
        print(json.dumps(st, indent=1))
        return 0
    ap.error('one of --self-test / --check / --read')
    return 2


if __name__ == '__main__':
    sys.exit(main())
