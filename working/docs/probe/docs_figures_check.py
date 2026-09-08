#!/usr/bin/env python3
"""docs_figures_check — every figure in the docs-campaign documents, recomputed from the
landed artifacts and checked against the literal in the document (DOCS_HANDOFF.md §7.3:
"the figure checker goes in at the START"). Authored 2026-09-07, before the first measured
leg of the docs re-run, so no figure in this campaign is ever written unchecked.

Mechanism — the same as working/video/probe/end_to_end_figures_check.py: a check passes only
if (a) the literal appears in the document text and (b) the number in that literal equals the
artifact value at the literal's own precision (decimal half-up). The checker runs a planted
control FIRST (a deliberately wrong literal must FAIL) so a checker that cannot fail never
gets to mean anything. Exit 1 on any failure.

Figures a document quotes that NO committed artifact can reproduce are listed under
UNVERIFIABLE with the reason; they do not fail the run, but they are printed every time so
they cannot silently become "checked".

Run (from the repo root, on a branch carrying the 18-Aug artifacts — docs-bench or main):
  python3 working/docs/probe/docs_figures_check.py [--doc working/docs/DOCS_HANDOFF.md]...
Add a check the moment a figure enters any docs document. Each new report gets its own
--doc entry (the default set is below) and its checks in a section here.
"""
from __future__ import annotations
import argparse, json, math, re, statistics as st, subprocess, sys
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

HERE = Path(__file__).resolve(); ROOT = HERE.parents[3]; RES = ROOT / 'working' / 'results'
DEFAULT_DOCS = [ROOT / 'working' / 'docs' / 'DOCS_HANDOFF.md']
LI, RR = 'llamaindex_http_pdf', 'rocketride_pdf'
S18 = RES / 'smoke50_parser_in__20260818T094225Z__a5fd8e2033b7.json'
S18B = RES / 'smoke50_parser_in__20260818T155557Z__4c468512ae75.json'
S16 = RES / 'smoke50_parser_in__20260816T031854Z__c362c2816e85.json'
S17 = RES / 'smoke50_parser_in__20260817T011556Z__4ae7d742bc16.json'
B10K = RES / 'exp_batched_blast__20260818T150551Z__373adce246fc.json'
B1K = RES / 'exp_batched_blast__20260818T075451Z__44d9a05dd11e.json'
BATCHED = sorted(RES.glob('exp_batched_blast__20260818T*.json'))
RG = RES / 'rederive_gates__20260818T140635Z__ef789985f863.json'
P2_STOCK = RES / 'smoke_phase2__20260818T035137Z__4a2b2bb35b79.json'
P2_PATCH = RES / 'smoke_phase2__20260818T035559Z__5131e250d300.json'
P2_PATCH2 = RES / 'smoke_phase2__20260818T074453Z__ca62d2e2ee9d.json'
FAULT = RES / 'exp_fault_isolation__20260817T064530Z__9497165fe2a1.json'
ISO_NULL = RES / 'exp_data_isolation__20260817T065922Z__d41525f85cb7.json'
ISO_DISJ = RES / 'exp_data_isolation__20260817T072129Z__6fb48193964a.json'
REGISTER = ROOT / 'working' / 'video' / 'METHODOLOGY_REGISTER.md'

TEXT = ''
fails: list[str] = []; n_ok = 0; unverifiable: list[str] = []


def num(lit: str) -> float:
    m = re.search(r'[-+−]?\d[\d,]*\.?\d*', lit.replace('×', ' '))
    return float(m.group(0).replace(',', '').replace('−', '-'))


def agrees(value, literal, tol=None, expect=None) -> bool:
    """(b) of the contract: value == the literal's number at the literal's precision."""
    m = re.search(r'[-+−]?\d[\d,]*\.?\d*', literal.replace('×', ' '))
    dec = len(m.group(0).split('.')[1]) if m and '.' in m.group(0) else 0
    target = num(literal) if expect is None else float(expect)
    if expect is not None:
        dec = len(str(expect).split('.')[1]) if '.' in str(expect) else 0
    t = tol if tol is not None else 0.5 * 10 ** (-dec) + 1e-9
    src = value if isinstance(value, Decimal) else Decimal(repr(float(value)))
    halfup = src.quantize(Decimal(1).scaleb(-dec), rounding=ROUND_HALF_UP)
    return abs(float(value) - target) <= t or float(halfup) == target


def chk(label, value, literal, tol=None, expect=None):
    global n_ok
    present = literal in TEXT
    ok = present and (value is None or agrees(value, literal, tol, expect))
    n_ok += ok
    if not ok:
        fails.append(f'{label}: literal {literal!r} {"ABSENT from document" if not present else f"!= artifact {value}"}')
    print(f'  {"PASS" if ok else "FAIL"}  {label}: {literal}' + ('' if value is None else f'  (artifact {value})'))


def fact(label, cond, got=''):
    """A non-numeric assertion about an artifact or the tree (no literal to find)."""
    global n_ok
    n_ok += bool(cond)
    if not cond:
        fails.append(f'{label}: {got}')
    print(f'  {"PASS" if cond else "FAIL"}  {label}  {got}')


def unver(label, why):
    unverifiable.append(f'{label} — {why}')


def load(p: Path):
    return json.loads(p.read_text())['data']


def jl(p: Path):
    return [json.loads(l) for l in p.read_text().splitlines() if l.strip()]


def q_nearest(xs, p):
    xs = sorted(xs); return xs[math.ceil(p * len(xs)) - 1]


def git(*args) -> str:
    return subprocess.run(['git', '-C', str(ROOT), *args], capture_output=True, text=True).stdout.strip()


def line(p: Path, n: int) -> str:
    return p.read_text().splitlines()[n - 1]


# ------------------------------------------------------------------------------------
def control():
    """The checker must be able to fail. A wrong literal, a wrong value and an absent
    literal are each tried against the real predicate before any real check runs."""
    global TEXT
    saved = TEXT; TEXT = 'the value is 2.776 docs/s and the count is 9,985'
    a = agrees(2.7762, '2.776'); b = agrees(2.7762, '2.780'); c = '9,985' in TEXT; d = '9,986' in TEXT
    e = agrees(9985, '9,985'); f = agrees(6.019, '6.02%'); g = agrees(6.019, '6.03%')
    TEXT = saved
    ok = a and (not b) and c and (not d) and e and f and (not g)
    print(f'  {"PASS" if ok else "FAIL"}  planted control: the predicate rejects a wrong literal, a wrong value and an absent literal')
    if not ok:
        print('CONTROL FAILED — the checker cannot fail; nothing below means anything'); sys.exit(2)


def section_1():
    print('=== §1: the one-token fact — every measured docs leg, from source ===')
    sm = ROOT / 'working' / 'scripts' / 'smoke50_parser_in.py'; eb = ROOT / 'working' / 'scripts' / 'exp_batched_blast.py'
    ww = ROOT / 'weekend_worker.py'
    l862 = line(sm, 862) + line(sm, 863)
    fact('smoke50_parser_in.py:862 is the one use() of the blast leg, no threads=', 'c.use(filepath' in l862 and 'threads=' not in l862, l862.strip()[:60])
    chk('§1.2 cites smoke50_parser_in.py:862', None, 'smoke50_parser_in.py:862')
    l216 = line(eb, 216) + line(eb, 217)
    fact('exp_batched_blast.py:216 is the one use() of the batched leg, threads=RR_THREADS', 'c.use(filepath' in l216 and 'threads=RR_THREADS' in l216)
    chk('§1.2 cites exp_batched_blast.py:216', None, 'exp_batched_blast.py:216')
    fact('exp_batched_blast.py:68 RR_THREADS defaults to "24"', 'SMOKE_RR_THREADS' in line(eb, 68) and '"24"' in line(eb, 68), line(eb, 68).strip())
    seq = [l for l in ww.read_text().splitlines() if 'self.c.use(filepath' in l]
    fact('weekend_worker RocketArm.__init__ use() carries no threads=', len(seq) >= 1 and all('threads=' not in l for l in seq), str(len(seq)))
    for p in BATCHED:
        pv = load(p)['provenance']
        fact(f'{p.name[:38]} threads_requested 24 / threads_observed None', pv.get('threads_requested') == 24 and pv.get('threads_observed') is None)
    chk('§1.3 threads_requested = 24', 24, 'threads_requested = 24'); chk('§1.3 threads_observed = None', None, 'threads_observed = None')


def section_2():
    print('=== §2: duplication — fixture, corpus maximum, eligible denominator, digests ===')
    stock, patched = load(P2_STOCK), load(P2_PATCH)
    fact('stock fixture run: expect_patch False, label_raw "0"', stock['expect_patch'] is False and stock['provenance']['engine']['label_raw'] == '0')
    fact('patched fixture run: expect_patch True, label_raw "1"', patched['expect_patch'] is True and patched['provenance']['engine']['label_raw'] == '1')
    chk('§2.2 label_raw=0 quoted', None, 'label_raw=0'); chk('§2.2 label_raw=1 quoted', None, 'label_raw=1')
    rs = {r['doc']: r for r in stock['duplication_fixture']['records']}; rp = {r['doc']: r for r in patched['duplication_fixture']['records']}
    for doc, s_lit, p_lit in (('000_000159.pdf', '164', '82'), ('000_000595.pdf', '276', '138'), ('000_000674.pdf', '1872', '936'),
                              ('000_000762.pdf', '132', '66'), ('000_000887.pdf', '344', '172')):
        chk(f'fixture {doc} stock chunks', rs[doc]['n_chunks'], f'`{doc[:10]}` | {s_lit} | {p_lit} | 2.000', expect=s_lit)
        fact(f'fixture {doc} patched chunks = {p_lit}, ratio exactly 2', rp[doc]['n_chunks'] == int(p_lit) and rs[doc]['n_chunks'] == 2 * rp[doc]['n_chunks'])
        fact(f'fixture {doc} repeat_factor 2 -> 1', rs[doc]['repeat_factor'] == 2 and rp[doc]['repeat_factor'] == 1)
    sd_s, sd_p = stock['duplication_fixture']['self_duplication'], patched['duplication_fixture']['self_duplication']
    fact('self_duplication 5/5 -> 0/5', sd_s['duplicated_docs'] == 5 and sd_s['checked'] == 5 and sd_p['duplicated_docs'] == 0 and sd_p['checked'] == 5)
    chk('§2.2 self_duplication 5/5 → 0/5', None, '5/5 → 0/5')

    r16 = [r for r in jl(RES / 'run10k' / 'perdoc_rr_blast.jsonl') if r.get('ok')]
    r18 = [r for r in jl(RES / 'run10k_p2_blast_v2' / 'perdoc_rr_blast.jsonl') if r.get('ok')]
    c16, c18 = [r['n_chunks'] for r in r16], [r['n_chunks'] for r in r18]
    chk('§2.2c 16-Aug max chunks/doc', max(c16), '**2754**'); chk('§2.2c 18-Aug max chunks/doc', max(c18), '**1377**')
    chk('§2.2c 16-Aug mean', st.mean(c16), '| 29.9 |'); chk('§2.2c 18-Aug mean', st.mean(c18), '| 20.7 |')
    chk('§2.2c median 8 (16-Aug)', st.median(c16), '| 8 |'); fact('§2.2c median 8 (18-Aug)', st.median(c18) == 8)
    chk('§2.2c 2754 / 1377 = 2.000', max(c16) / max(c18), '2754 / 1377 = **2.000**', expect='2.000')
    chk('§2.3 16-Aug successful docs', len(r16), '9,985'); chk('§2.3 16-Aug docs ≥64', sum(c >= 64 for c in c16), '**601**')
    chk('§2.3 16-Aug share', sum(c >= 64 for c in c16) / len(r16) * 100, '6.02%')
    chk('§2.3 18-Aug successful docs', len(r18), '9,936'); chk('§2.3 18-Aug docs ≥64', sum(c >= 64 for c in c18), '**595**')
    chk('§2.3 18-Aug share', sum(c >= 64 for c in c18) / len(r18) * 100, '5.99%')
    chk('§2.3 94% cannot trip', (1 - sum(c >= 64 for c in c16) / len(r16)) * 100, '**94% of the corpus', tol=0.51)
    chk('§2.3 never at risk 9,250', 9847 - 595, '9,250', tol=5)   # 0 of ~9,847 checked, ~595 eligible
    rg = load(RG)
    chk('§2.2d LI self_duplication checked', rg['arms'][LI]['self_duplication']['checked'], '0/9,872', expect='9872')
    chk('§2.2d RR self_duplication checked', rg['arms'][RR]['self_duplication']['checked'], '0/9,847', expect='9847')
    fact('§2.2d duplicated_docs 0 on both arms', all(rg['arms'][a]['self_duplication']['duplicated_docs'] == 0 for a in (LI, RR)))
    chk('§2.2d 0 of ~595 eligible', sum(c >= 64 for c in c18), '0 of ~595 eligible', expect='595')

    print('--- §2.4 / §2.6: the digests and the false field, as recorded ---')
    dig = lambda d, k: d['provenance']['image_digests'][k].split('|')
    fact('rr:stock digest 5e83c803 only in smoke_phase2 035137Z', dig(stock, 'rocketride')[0].startswith('sha256:5e83c803') and dig(stock, 'rocketride')[1] == 'rr:stock')
    fact('rr:patched digest 073b43d8 in 035559Z and 074453Z', all(dig(load(p), 'rocketride')[0].startswith('sha256:073b43d8') and dig(load(p), 'rocketride')[1] == 'rr:patched' for p in (P2_PATCH, P2_PATCH2)))
    fact('ws1-llamaindex digest 3d2f1f43 in every 18-Aug smoke_phase2/batched artifact', all(dig(load(p), 'llamaindex')[0].startswith('sha256:3d2f1f43') for p in (P2_STOCK, P2_PATCH, P2_PATCH2, *BATCHED)))
    for lit in ('sha256:5e83c803', 'sha256:073b43d8', 'sha256:3d2f1f43', 'sha256:500c5d77', 'sha256:6699e9d4'):
        chk(f'§2.6 digest {lit[7:]}', None, lit)
    for p in (FAULT, ISO_NULL, ISO_DISJ):
        d = load(p); fact(f'{p.name[:34]} on 17-Aug images 500c5d77 / 6699e9d4', dig(d, 'rocketride')[0].startswith('sha256:500c5d77') and dig(d, 'llamaindex')[0].startswith('sha256:6699e9d4'))
    for p in (S18, S18B):
        pl = load(p)['provenance_leela']
        fact(f'{p.name[:38]} RR arm image_digest is the PATCHED image', pl[RR]['image_digest'].startswith('sha256:073b43d8'))
        fact(f'{p.name[:38]} original field reads False on both arms (the recorded defect)', pl[RR]['duplication_patch_applied'] is False and pl[LI]['duplication_patch_applied'] is False)
    for p in BATCHED:
        e = load(p)['provenance']['engine']; fact(f'{p.name[:38]} engine block label_raw "1" (never carried the false field)', e['label_raw'] == '1' and e['duplication_patch_applied'] is True)
    fact('correction artifact committed (provenance_correction_20260818)', bool(list(RES.glob('provenance_correction_20260818__*.json'))))


def section_3():
    print('=== §3: the banked figures — posture, load, quotable, superseded, never-quote ===')
    d = load(S18); pl = d['provenance_leela']; m = d['metrics']['arms']; pin = d['pinned']
    chk('§3.1 corpus sha', None, '22177c33c3651fceceef99ba5c5c2d89f9bbe270dddc23e9943c6e20b421508c'); fact('corpus sha in export', d['corpus']['sha256'].startswith('22177c33c3651fce'))
    chk('§3.1 n = 9,975', d['corpus']['n'], 'n = 9,975'); fact('corpus_n_docs 9975 on both arms', all(pl[a]['corpus_n_docs'] == 9975 for a in (LI, RR)))
    fact('instance c7i.8xlarge', pl[RR]['instance_type'] == 'c7i.8xlarge'); chk('§3.1 c7i.8xlarge', None, 'c7i.8xlarge')
    fact('engine 3.3.1 / SDK 1.3.0', pl[RR]['rocketride_engine_version'] == '3.3.1' and pl[RR]['rocketride_sdk_version'] == '1.3.0'); chk('§3.1 SDK 1.3.0', None, 'SDK 1.3.0')
    fact('embedding multi-qa-MiniLM-L6-cos-v1', pl[RR]['embedding_model'] == 'sentence-transformers/multi-qa-MiniLM-L6-cos-v1'); chk('§3.1 embedding', None, 'sentence-transformers/multi-qa-MiniLM-L6-cos-v1')
    fact('parsers differ: RR tika, LI pypdf', pl[RR]['parser'].startswith('tika') and pl[LI]['parser'] == 'pypdf'); chk('§3.1 parsers', None, 'RocketRide Tika, LlamaIndex `pypdf`')
    fact('offered 32 / configured 24 (LI) / timeout 1800', pl[LI]['offered_concurrency'] == 32 and pl[LI]['configured_concurrency'] == 24 and pl[LI]['timeout_s'] == 1800)
    chk('§3.1 offered 32', 32, '`offered_concurrency` 32'); chk('§3.1 configured 24', 24, '`configured_concurrency` 24'); chk('§3.1 timeout 1800', 1800, '`timeout_s` 1800')
    chk('§3.1 ttl 7200', load(B10K)['provenance']['ttl_s'], 'ttl 7200')
    tm = pin['torch_threads_measured']
    fact('OMP_NUM_THREADS=1 measured inside the engine task process', tm[RR]['env']['OMP_NUM_THREADS'] == '1' and 'inside the engine task process' in tm[RR]['source'])
    chk('§3.1 OMP pin', None, '`OMP_NUM_THREADS=1` measured **inside the engine task process**')
    fact('torch intra=1 / interop=16', tm[RR]['torch_num_threads'] == 1 and tm[RR]['torch_num_interop_threads'] == 16); chk('§3.1 torch intra/interop', None, 'torch intra=1 / interop=16')
    fact('LI per-worker [[1, 16]]', tm[LI]['per_worker_intra_interop'] == [[1, 16]]); chk('§3.1 LI per-worker', None, '`[[1, 16]]`')
    fact('git_commit 9b7c654…-dirty', pl[RR]['git_commit'].startswith('9b7c654') and pl[RR]['git_commit'].endswith('-dirty')); chk('§3.1 dirty tree', None, '9b7c654…-dirty')
    w = d['warm_up']; fact('warm-up 25 disjoint on both arms', all(w[a]['docs'] == 25 and w[a]['disjoint_from_measured'] for a in (LI, RR)))
    chk('§3.1 9,975 + 25 = 10,000', 9975 + 25, '9,975 measured + 25 warm = 10,000', expect='10000')
    fact('manifest holds exactly 10,000 documents', len((RES / 'corpus_manifest.jsonl').read_text().splitlines()) == 10000)

    print('--- §3.2 load1 floors, from the committed sampler streams ---')
    for dname, stream, lits in (('run10k', 'sampler_rr_blast', ('500', '3.84', '34.55', '37.80')), ('run10k', 'sampler_li_blast', ('313', '4.14', '32.88', '33.51')),
                                ('run10k_blast_v1', 'sampler_rr_blast', ('496', '3.74', '34.51', '38.33')), ('run10k_p2_blast', 'sampler_rr_blast', ('802', '21.93', '66.88', '90.24')),
                                ('run10k_p2_blast_v2', 'sampler_rr_blast', ('718', '15.37', '36.69', '44.46')), ('run10k_p2_blast_v2', 'sampler_li_blast', ('476', '12.05', '33.05', '33.60')),
                                ('run10k_p2_blast_v2', 'sampler_rr_sequential', ('185', '10.18', '10.35', '11.35')), ('run10k_p2_blast_v2', 'sampler_li_sequential', ('81', '9.84', '10.02', '10.09')),
                                ('batched_20260818T133821Z', 'sampler_rr_batched', ('1046', '9.15', '31.50', '35.86'))):
        l1 = [r['load1'] for r in jl(RES / dname / f'{stream}.jsonl') if r.get('kind') == 'system_tick']
        row = f'`{stream}` | {lits[0]} | **{lits[1]}** | {lits[2]} | {lits[3]} |'
        chk(f'load1 {dname}/{stream} n', len(l1), row); fact(f'load1 {dname}/{stream} min/med/max', agrees(min(l1), lits[1]) and agrees(st.median(l1), lits[2]) and agrees(max(l1), lits[3]), f'{min(l1):.2f}/{st.median(l1):.2f}/{max(l1):.2f}')

    print('--- §3.3 / §3.5 quotable ---')
    li, rr = m[LI]['blast_warm0'], m[RR]['blast_warm0']
    chk('LI docs/s', li['docs_per_s'], '| docs/s | 4.1887 | 2.7762 |'); fact('RR docs/s 2.7762', rr['docs_per_s'] == 2.7762)
    chk('LI chunks/s', li['chunks_per_s'], '| chunks/s | 81.84 | 57.39 |'); fact('RR chunks/s 57.39', agrees(rr['chunks_per_s'], '57.39'))
    chk('LI p50', li['latency']['p50'], '3.058s / 28.21s'); fact('LI p95 28.21', agrees(li['latency']['p95'], '28.21'))
    chk('RR p50', rr['latency']['p50'], '4.785s / 31.21s'); fact('RR p95 31.21', agrees(rr['latency']['p95'], '31.21'))
    chk('LI cpu_s/doc', li['cpu_s_per_doc'], '| cpu_s/doc | 4.5127 | 5.9829 |'); fact('RR cpu_s/doc 5.9829', rr['cpu_s_per_doc'] == 5.9829)
    chk('LI effective cores', li['effective_cores'], '| effective cores | 18.90 | 16.61 |'); fact('RR effective cores 16.61', agrees(rr['effective_cores'], '16.61'))
    chk('LI utilisation', li['cpu_utilization'] * 100, '| utilisation | 78.8% | **69.2%** |'); fact('RR utilisation 69.2', agrees(rr['cpu_utilization'] * 100, '69.2'))
    an = lambda dn, s: json.loads((RES / dn / f'{s}.summary.json').read_text())['roles']['service']['peak_cgroup_anon_mb']
    chk('LI cgroup anon peak', an('run10k_p2_blast_v2', 'sampler_li_blast'), '| cgroup anon peak | 17,594.4 MB | 14,018.8 MB |'); fact('RR anon peak 14,018.8', agrees(an('run10k_p2_blast_v2', 'sampler_rr_blast'), '14,018.8'))
    b = load(B10K); t = b['throughput']; ap = b['achieved_parallelism']
    chk('batched docs/s', t['docs_per_s'], '1.9098 docs/s'); chk('batched chunks/s', t['chunks_per_s'], '40.5112 chunks/s'); chk('batched wall', t['wall_s'], 'wall 5,176.5s')
    chk('batched cpu_utilization', ap['cpu_utilization']['cpu_utilization'], '`cpu_utilization` 0.5038'); chk('batched effective cores', ap['effective_cores'], 'effective cores 12.09 of 24')
    chk('batched ok', t['documents_ok'], 'ok 9,886/9,975'); fact('batched total 9975', t['documents_total'] == 9975)
    chk('§3.5 per-document 2.776', rr['docs_per_s'], '**2.776**'); chk('§3.5 batched 1.910', t['docs_per_s'], '**1.910**')
    chk('§3.5 per-document 69.2%', rr['cpu_utilization'] * 100, '**69.2%**'); chk('§3.5 batched 50.4%', ap['cpu_utilization']['cpu_utilization'] * 100, '**50.4%**')
    chk('§3.5 16.61 / 24', rr['effective_cores'], '16.61 / 24'); chk('§3.5 12.09 / 24', ap['effective_cores'], '12.09 / 24'); chk('§3.5 40.51', t['chunks_per_s'], '| 40.51 |')
    chk('§3.5 ~45% faster', (rr['docs_per_s'] / t['docs_per_s'] - 1) * 100, '~45% faster', tol=0.6)
    chk('§3.5 n=1,000 batched 49.7%', load(B1K)['achieved_parallelism']['cpu_utilization']['cpu_utilization'] * 100, '49.7%'); chk('§3.5 n=9,975 50.4%', ap['cpu_utilization']['cpu_utilization'] * 100, '50.4%')
    chk('§3.5 windowed average 50.38%', ap['cpu_utilization']['cpu_utilization'] * 100, '50.38%')
    f = load(FAULT)['arms']
    fact('fault isolation: collateral 0, batch_survived, service_alive_after, recovery_ok on both arms', all(f[a]['collateral_failures'] == 0 and f[a]['batch_survived'] and f[a]['service_alive_after'] and f[a]['recovery_ok'] for a in (LI, RR)))
    fact('fault surfacing: LI service_error, RR no_documents', f[LI]['blast_radius']['per_fault']['poison-x.pdf']['fault_outcome'] == 'service_error' and f[RR]['blast_radius']['per_fault']['poison-x.pdf']['fault_outcome'] == 'no_documents')
    chk('§3.3 collateral_failures = 0', 0, '`collateral_failures = 0`'); chk('§3.3 service_error', None, '`service_error`'); chk('§3.3 no_documents', None, '`no_documents`')
    dj, nl = load(ISO_DISJ)['arms'], load(ISO_NULL)['arms']
    fact('data isolation disjoint: cross-tenant chunks/docs/vectors 0 on both arms', all(dj[a][k] == 0 for a in (LI, RR) for k in ('cross_tenant_chunks', 'cross_tenant_docs', 'cross_tenant_vectors')))
    fact('data isolation null control: overlap 1.0 on both arms', all(nl[a]['chunks']['overlap_frac_of_a'] == 1.0 for a in (LI, RR))); chk('§3.3 null control overlap 1.0', 1.0, 'overlap 1.0')
    empties = {load(B10K)['gates']['census_policy']['empty_documents'], load(RG)['arms'][LI]['gate_verdicts']['leela']['checks']['census']['failed_by_reason'].get('unknown')}
    fact('~88–102 legitimately empty PDFs: 89 (RR batched census) and 102 (LI, rederived)', empties == {89, 102}, str(empties)); chk('§3.3 ~88–102', None, '~88–102 legitimately empty')

    print('--- §3.4 superseded ---')
    m16, m17 = load(S16)['metrics']['arms'], load(S17)['metrics']['arms']
    chk('16-Aug LI 6.4007', m16[LI]['blast_warm64']['docs_per_s'], 'LI 6.4007 / RR 4.0271'); fact('16-Aug RR 4.0271', m16[RR]['blast_warm64']['docs_per_s'] == 4.0271)
    chk('17-Aug LI 6.3586', m17[LI]['blast_warm64']['docs_per_s'], 'LI 6.3586 / RR 3.9930'); fact('17-Aug RR 3.9930', m17[RR]['blast_warm64']['docs_per_s'] == 3.993)
    fact('16-Aug corpus sha 03692bf6a4d5d549 (was PRIOR-RECORD; now from the export)', load(S16)['corpus']['sha256'].startswith('03692bf6a4d5d549')); chk('§5.4 03692bf6a4d5d549', None, '03692bf6a4d5d549')

    print('--- §3.6 never quote — each figure is real, and each reason is checkable ---')
    rss = lambda dn, s: json.loads((RES / dn / f'{s}.summary.json').read_text())['roles']['service']['peak_rss_mb']
    chk('84,960.6 MB is the summed-RSS artifact (run10k_blast_v1)', rss('run10k_blast_v1', 'sampler_rr_blast'), '84,960.6 MB')
    chk('16,397.0 MB true sampled peak (run10k rr anon)', an('run10k', 'sampler_rr_blast'), '16,397.0 MB')
    chk('1.42× from the 10k blast (run10k LI anon / RR anon)', an('run10k', 'sampler_li_blast') / an('run10k', 'sampler_rr_blast'), '1.42×')
    gap_rr = (m[RR]['blast_warm0']['window_t0_ns'] - m[RR]['blast_batchpos_warm0']['window_t0_ns']) / 1e9
    gap_li = (m[LI]['blast_warm0']['window_t0_ns'] - m[LI]['blast_batchpos_warm0']['window_t0_ns']) / 1e9
    chk('stale batch-open gap RR', gap_rr, '**2,388.6s**'); chk('stale batch-open gap LI', gap_li, '0.3s on LlamaIndex')
    seq = jl(RES / 'run10k' / 'perdoc_rr_sequential.jsonl')
    pipe = [i for i, r in enumerate(seq) if not r.get('ok') and 'not running' in (r.get('error') or '')]
    chk('371 PipeException failures (run10k rr sequential)', len(pipe), '371 `PipeException`')
    gaps = [((seq[i]['submit_ns'] - seq[i - 1]['submit_ns']) / 1e9, i) for i in range(1, len(seq)) if seq[i].get('submit_ns') and seq[i - 1].get('submit_ns')]
    g, gi = max(gaps); chk('submission gap exactly 1800.0s', g, '**1800.0s**'); chk('at index 9,629', gi, 'index 9,629'); fact('first PipeException is at that index', pipe[0] == gi, str(pipe[0]))
    gv = d['gate_verdicts']
    fact('gate FAIL verdicts: census recorded 0 of 9975 on both arms (the empty sequential set)', all(gv[a]['shashi']['checks']['census']['recorded'] == 0 and gv[a]['shashi']['checks']['census']['expected'] == 9975 for a in (LI, RR)))
    chk('§3.6 offered 9975 = successful 0', None, 'offered 9975 = successful 0')


def section_4_7():
    print('=== §4 / §7.1: chunk axes ===')
    c18 = [r['n_chunks'] for r in jl(RES / 'run10k_p2_blast_v2' / 'perdoc_rr_blast.jsonl') if r.get('ok')]
    chk('§7.1 median 8', st.median(c18), 'median 8'); chk('§7.1 p95 74 (nearest-rank)', q_nearest(c18, 0.95), 'p95 74', expect='74'); chk('§7.1 max 1377', max(c18), '**max 1377**')
    chk('§7.1 p95-to-max 18.6×', max(c18) / q_nearest(c18, 0.95), '18.6×')
    chk('§4.1 4000/200 defaults', 4000, '4000/200'); fact('declared chunk_config 4000/200 in provenance', load(S18)['provenance_leela'][RR]['chunk_config'] == {'chunk_size': 4000, 'chunk_overlap': 200, 'splitter': 'RecursiveCharacterTextSplitter', 'input_transform': "text + '\\n'"})
    unver('§4.1 mean chunk chars ~3326–3468, max ~3993', 'cited from query_phase1_chunks_20260820T223826Z.json, which is not under working/results on this branch')
    unver('§7.1 slowest 1% carry 58.6% of all service seconds', 'no service-seconds artifact is committed; the per-document latency share (completion−submit) is 17.1% on run10k_p2_blast_v2 and is NOT the same quantity')
    unver('§6.1 engine burns 1.004 cores idle', 'measured live from /proc/<pid>/stat; no committed artifact')
    unver('§3.3 LOC 557 vs 179, COSMIC 4 CFP', 'no LOC/COSMIC artifact under working/results')
    unver('§3.6 RocketRide post-leg reading 135.3 MB', 'a post-leg point sample; no committed artifact names it')
    unver('§6.2 Tika reference 0.599 s/doc', 'no committed timing artifact')
    unver('§1.1 video 2.443 / 12.729 f/s, 5.21×, 0.19%', 'video-campaign figures; checked by working/video/probe/end_to_end_figures_check.py, not here')


def section_5_8():
    print('=== §5 / §8: branch facts and the register, from git and the tree ===')
    added = [l for l in git('diff', '--name-status', 'origin/video-bench', 'origin/main', '--', 'working/results').splitlines()]
    chk('§5.1 128 main-only files under working/results', len(added), '**128 files under `working/results/`**'); fact('all 128 are additions on main', all(l.startswith('A\t') for l in added))
    fact('box.sh is video-bench-only (D in the video-bench→main diff)', git('diff', '--name-status', 'origin/video-bench', 'origin/main', '--', 'working/harness/box.sh').startswith('D'))
    chk('§5.1 fork point 17f77aa', None, '17f77aa'); fact('merge-base of main and video-bench is 17f77aa', git('merge-base', 'origin/main', 'origin/video-bench').startswith('17f77aa'))
    tree = git('ls-tree', '-r', '--name-only', '17f77aa')
    fact('17f77aa already carried the docs driver, arms, batched arm, smoke and rederive', all(p in tree for p in ('weekend_worker.py', 'working/scripts/smoke50_parser_in.py', 'working/scripts/exp_batched_blast.py', 'working/scripts/smoke_phase2.py', 'working/scripts/rederive_gates.py')))
    mod = git('diff', '--name-status', 'origin/video-bench', 'origin/main', '--', 'working/harness/gates_shared.py', 'working/harness/provenance_leela.py', 'working/harness/collector_proc.py', 'working/harness/static_names.py', 'working/nodes/env_probe/IInstance.py')
    fact('main is older on the five shared harness files (all M in the video-bench→main diff)', mod.count('M\t') == 5, mod.replace('\n', ' '))
    fact('main:132 held the literal False', 'duplication_patch_applied": False' in git('show', 'origin/main:working/harness/provenance_leela.py').splitlines()[131])
    fact('origin/video-bench:140 held the literal False', 'duplication_patch_applied": False' in git('show', 'origin/video-bench:working/harness/provenance_leela.py').splitlines()[139])
    chk('§2.4 main line 132', None, '`main` line 132'); chk('§2.4 video-bench line 140', None, '`video-bench` line 140')
    vc = ROOT / 'working' / 'scripts' / 'verify_corpus_manifest.py'
    fact('verify_corpus_manifest.py:41 is the --subset flag line', 'subset = "--subset" in sys.argv[1:]' in line(vc, 41)); chk('§5.4 :41', None, '`:41`')
    fact('verify_corpus_manifest.py:35-37 resolve manifest and corpus paths', 'corpus_manifest.jsonl' in line(vc, 36) and 'govdocs1' in line(vc, 37)); chk('§5.4 :35-37', None, '`:35-37`')
    fact('fetch_govdocs.py committed', (ROOT / 'working' / 'scripts' / 'fetch_govdocs.py').exists())
    reg = REGISTER.read_text().splitlines()
    chk('§8.6 register 35 entries', sum(bool(re.match(r'## \d+\. ', l)) for l in reg), '**35 entries**')
    fact('register entry 2 at :24', reg[23].startswith('## 2. Self-consistency is not evidence')); chk('§2.5 METHODOLOGY_REGISTER.md:24', None, 'METHODOLOGY_REGISTER.md:24')
    fact('register entry 26 at :901', reg[900].startswith('## 26. A box commit is landed')); chk('§8.2 :901', None, 'METHODOLOGY_REGISTER.md:901')
    fact('register entry 33 at :1242', reg[1241].startswith('## 33. Two methods with one name')); chk('§7.2 :1242', None, 'METHODOLOGY_REGISTER.md:1242')


def main(argv=None) -> int:
    global TEXT
    ap = argparse.ArgumentParser(); ap.add_argument('--doc', action='append', help='document(s) whose figures are checked (default: DOCS_HANDOFF.md)')
    a = ap.parse_args(argv)
    docs = [Path(p) for p in a.doc] if a.doc else DEFAULT_DOCS
    TEXT = '\n'.join(p.read_text() for p in docs)
    print(f'documents: {[str(p.relative_to(ROOT)) for p in docs]}')
    missing = [p for p in (S18, S18B, S16, S17, B10K, B1K, RG, P2_STOCK, P2_PATCH, P2_PATCH2, FAULT, ISO_NULL, ISO_DISJ) if not p.exists()]
    if missing:
        print('ARTIFACTS MISSING (this branch does not carry the 18-Aug results — run on docs-bench or main):'); [print('  ', m.name) for m in missing]; return 2
    control(); section_1(); section_2(); section_3(); section_4_7(); section_5_8()
    print(f'\n{n_ok} checks passed, {len(fails)} failed; {len(unverifiable)} figures UNVERIFIABLE (listed, not failed)')
    for f in fails: print('  FAIL', f)
    for u in unverifiable: print('  UNVERIFIABLE', u)
    return 1 if fails else 0


if __name__ == '__main__':
    sys.exit(main())
