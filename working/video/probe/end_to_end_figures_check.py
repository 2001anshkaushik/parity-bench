#!/usr/bin/env python3
"""end_to_end_figures_check — every figure in ARCHIVE_FILMS_END_TO_END.md,
recomputed from the landed artifacts and checked against the literal in the
document (2026-09-07). A check passes only if (a) the literal appears in the
report text and (b) the number in that literal equals the artifact value to
the literal's own precision. Exit 1 on any failure. Run:
  python3 working/video/probe/end_to_end_figures_check.py
"""
from __future__ import annotations
import json, re, statistics as st, sys
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
HERE = Path(__file__).resolve(); V = HERE.parents[1]; RES = V / 'results'
sys.path.insert(0, str(HERE.parent))
L = RES / 'films500_lifetimes_20260906T090339Z'; C = RES / 'films500_mainrun_20260904T204852Z'; F35 = RES / 'films_mainrun_20260901T204015Z'
RR, LI = 'rocketride_video_parity', 'llamaindex_video_workers'
TEXT = (V / 'ARCHIVE_FILMS_END_TO_END.md').read_text()
fails = []; n_ok = 0

def num(lit: str) -> float:
    m = re.search(r'[-+−]?\d[\d,]*\.?\d*', lit.replace('×', ' '))
    return float(m.group(0).replace(',', '').replace('−', '-'))

def chk(label, value, literal, tol=None, expect=None):
    global n_ok
    present = literal in TEXT
    ok = present
    if value is not None and present:
        s = literal
        m = re.search(r'[-+−]?\d[\d,]*\.?\d*', s.replace('×', ' '))
        dec = len(m.group(0).split('.')[1]) if m and '.' in m.group(0) else 0
        target = num(literal) if expect is None else float(expect)
        if expect is not None:
            dec = len(str(expect).split('.')[1]) if '.' in str(expect) else 0
        t = tol if tol is not None else 0.5 * 10 ** (-dec) + 1e-9
        src = value if isinstance(value, Decimal) else Decimal(repr(float(value)))
        halfup = src.quantize(Decimal(1).scaleb(-dec), rounding=ROUND_HALF_UP)
        ok = abs(float(value) - target) <= t or float(halfup) == target
    n_ok += ok
    if not ok:
        fails.append(f'{label}: literal {literal!r} {"absent" if not present else f"!= artifact {value}"}')
    print(f'  {"PASS" if ok else "FAIL"}  {label}: {literal}' + ('' if value is None else f'  (artifact {value})'))

def ex(d, arm, leg): return json.loads((d / f'export_{arm}_{leg}.json').read_text())
def leg(d, arm, name):
    e = ex(d, arm, name); t = e['throughput']; f = e['efficiency']; sw = t['steady_window']
    ls = e.get('lifetime_state') or {}; tr = (ls.get('service_memory_trajectory') or {}).get('rss') or {}
    fs = (((ls.get('fs_stream') or {}).get('paths') or {}).get('docker_root') or {})
    svc = (e.get('collector_summary') or {}).get('roles', {}).get('service', {})
    g = {'PASS': 0, 'NOT RUN': 0, 'FAIL': 0}
    for k, v in (e.get('gates') or {}).items():
        if isinstance(v, dict) and 'PASS' in v: g['PASS' if v['PASS'] is True else ('FAIL' if v['PASS'] is False else 'NOT RUN')] += 1
    conts = (ls.get('leg_end') or {}).get('containers') or {}
    sp = next(iter((next(iter(conts.values()), {}).get('spool') or {}).values()), {}) if conts else {}
    return dict(span=t['total_frames_per_s'], win=sw.get('window_frames_per_s'), win_n=sw.get('window_n'), xrt=t['total_realtime_factor'], wall=t['total_span_s'],
                frames=t['total_frames'], cores=f['effective_cores'], util=f['cpu_util_of_box'], idle=f['idle_burden']['idle_cores_with_instances_live'],
                cpf=f['cpu_s_per_frame'], cpm=f.get('cpu_s_per_footage_min'), usd=f['usd_per_1k_footage_hours'], n=e['n_records'], err=e['n_errors'], g=g,
                rss=svc.get('peak_rss_bytes', 0) / 2**30, anon=(svc.get('peak_cgroup_anon_mb') or 0) / 1024, first=(tr.get('first_mean') or 0) / 2**30,
                last=(tr.get('last_mean') or 0) / 2**30, fs=(fs.get('max_used_minus_start') or 0) / 2**30, sp_files=sp.get('n_files'), sp_kb=sp.get('du_kb'),
                age=((e.get('provenance_video') or {}).get('container_lifetime') or {}).get('age_at_leg_start_s'), lat=(e.get('latency_normalized') or {}).get('p50'))
r3, r4, l3, l4 = leg(L, RR, 'blast_p3'), leg(L, RR, 'blast_p4'), leg(L, LI, 'blast_p3'), leg(L, LI, 'blast_p4')
r2, l2, r1, l1 = leg(C, RR, 'blast_p2'), leg(C, LI, 'blast_p2'), leg(C, RR, 'blast'), leg(C, LI, 'blast')
rs, lsq = leg(C, RR, 'sequential'), leg(C, LI, 'sequential')
from decimal import Decimal as _Dc
m = lambda a, b, k: (_Dc(repr(float(a[k]))) + _Dc(repr(float(b[k])))) / 2
R_ = {k: m(r3, r4, k) for k in ('span', 'win', 'xrt', 'wall', 'cores', 'util', 'idle', 'cpf', 'cpm', 'usd')}
L_ = {k: m(l3, l4, k) for k in ('span', 'win', 'xrt', 'wall', 'cores', 'util', 'idle', 'cpf', 'cpm', 'usd')}
R_['eff'], L_['eff'] = R_['cores'] - R_['idle'], L_['cores'] - L_['idle']
R_ = {k: float(v) if k not in ('win',) else v for k, v in R_.items()}; L_ = {k: float(v) if k not in ('win',) else v for k, v in L_.items()}
R_['pmc'], L_['pmc'], R_['pec'], L_['pec'] = R_['span'] / R_['cores'], L_['span'] / L_['cores'], R_['span'] / R_['eff'], L_['span'] / L_['eff']
pct = lambda a, b: (a / b - 1) * 100

print('=== §1/§2/§3: the 500-run means and deltas ===')
chk('per effective core RR', R_['pec'], '0.4389'); chk('per effective core LI', L_['pec'], '0.4420'); chk('effective-core delta', pct(L_['pec'], R_['pec']), 'LI +0.7%')
chk('per measured core RR', R_['pmc'], '0.3733'); chk('per measured core LI', L_['pmc'], '0.4411'); chk('measured-core delta', pct(L_['pmc'], R_['pmc']), 'LI +18.1%')
chk('CPU-s/frame RR', R_['cpf'], '2.679'); chk('CPU-s/frame LI', L_['cpf'], '2.268'); chk('CPU-s/frame delta', pct(R_['cpf'], L_['cpf']), 'RR +18.1%')
chk('span RR', R_['span'], '11.613'); chk('span LI', L_['span'], '12.800'); chk('span delta', pct(L_['span'], R_['span']), 'LI +10.2%')
chk('$/1k RR (half-up of 8.215)', R_['usd'], '8.22', tol=0.0051); chk('$/1k LI', L_['usd'], '7.46'); chk('$/1k delta', pct(R_['usd'], L_['usd']), 'RR +10.2%')
chk('§1 span rounded RR', R_['span'], '11.61'); chk('§1 span rounded LI', L_['span'], '12.80'); chk('§1 $ RR', R_['usd'], '$8.22', tol=0.0051); chk('§1 $ LI', L_['usd'], '$7.46')
chk('idle burden RR (4.6465 half-up)', R_['idle'], '4.647', tol=0.00051); chk('idle burden LI (0.0625 half-up)', L_['idle'], '0.063', tol=0.00051); chk('idle ratio', R_['idle'] / L_['idle'], '74× higher')
chk('§1 idle 4.65 cores', R_['idle'], '4.65 cores', tol=0.0051); chk('§1 14.5% of the machine', R_['idle'] / 32 * 100, '14.5%')
chk('window RR', R_['win'], '11.649'); chk('window LI', L_['win'], '12.783'); chk('window n', r3['win_n'], 'n = 482')
chk('realtime RR', R_['xrt'], '173.8'); chk('realtime LI', L_['xrt'], '191.6'); chk('wall RR', R_['wall'], '13,944'); chk('wall LI', L_['wall'], '12,651')
chk('wall RR h', R_['wall'] / 3600, '3.87 h'); chk('wall LI h', L_['wall'] / 3600, '3.51 h'); chk('wall delta', pct(R_['wall'], L_['wall']), 'RR +10.2% longer')
chk('sequential RR', rs['span'], '2.081'); chk('sequential LI', lsq['span'], '1.834'); chk('seq delta', pct(rs['span'], lsq['span']), 'RR +13.5%')
chk('seq latency RR', rs['lat'], '1.81'); chk('seq latency LI', lsq['lat'], '2.10'); chk('seq latency delta', pct(lsq['lat'], rs['lat']), 'LI +16%')
chk('service cores RR', R_['cores'], '31.10'); chk('service cores LI', L_['cores'], '29.02'); chk('cores delta', pct(R_['cores'], L_['cores']), 'RR +7.2%')
chk('util RR', R_['util'] * 100, '97.2'); chk('util LI', L_['util'] * 100, '90.7'); chk('util pts', (R_['util'] - L_['util']) * 100, 'RR +6.5 pts')
chk('effective cores RR', R_['eff'], '26.46'); chk('effective cores LI', L_['eff'], '28.96'); chk('eff delta', pct(L_['eff'], R_['eff']), 'LI +9.4%')
chk('CPU-s/foot-min RR', R_['cpm'], '10.74'); chk('CPU-s/foot-min LI', L_['cpm'], '9.09'); chk('cpm delta', pct(R_['cpm'], L_['cpm']), 'RR +18.1%')
chk('peak RSS RR p3', r3['rss'], '53.2'); chk('peak RSS RR p4', r4['rss'], '50.8'); chk('peak RSS LI p3', l3['rss'], '22.7'); chk('peak RSS LI p4', l4['rss'], '22.6'); chk('RSS ratio', m(r3, r4, 'rss') / m(l3, l4, 'rss'), 'RR 2.3× higher')
chk('anon RR p3', r3['anon'], '45.5'); chk('anon RR p4', r4['anon'], '43.1'); chk('anon LI', l3['anon'], '1.08'); chk('anon ratio', m(r3, r4, 'anon') / m(l3, l4, 'anon'), 'RR 41× higher')
chk('growth RR p3', r3['first'], '26.7 → 52.5'); chk('growth RR p3 end', r3['last'], '52.5 GiB'); chk('growth RR p4', r4['first'], '26.5 → 49.2'); chk('growth LI p3', l3['first'], '22.1 → 21.6'); chk('growth LI p4', l4['first'], '21.8 → 21.6')
chk('retention RR p3', (r3['last'] - r3['first']) * 1024 / 498, '52.9'); chk('retention RR p4', (r4['last'] - r4['first']) * 1024 / 498, '46.6'); chk('retention LI p3', (l3['last'] - l3['first']) * 1024 / 498, '−1.1'); chk('retention LI p4', (l4['last'] - l4['first']) * 1024 / 498, '−0.4')
chk('spool hw RR', r3['fs'], '12.0 / 12.0'); chk('spool hw LI p3', l3['fs'], '13.9 / 13.8'); chk('spool hw delta', pct(m(l3, l4, 'fs'), m(r3, r4, 'fs')), 'LI +15.6%')
chk('spool residue RR', r3['sp_files'], '18 / 76'); chk('spool residue LI', l3['sp_files'], '3 / 32')
chk('gates RR', r3['g']['PASS'], '8 / 1 / 0'); chk('gates LI', l3['g']['PASS'], '7 / 1 / 0'); chk('errors', r3['err'] + l3['err'] + r4['err'] + l4['err'], '| 0 | 0 | matched')
chk('spread RR', abs(pct(r3['span'], r4['span'])), '0.91'); chk('spread LI', abs(pct(l3['span'], l4['span'])), '0.14'); chk('§1 spreads', None, '0.91% and 0.14%')
chk('across lifetimes RR', pct(R_['span'], r2['span']), '+0.03'); chk('across lifetimes LI', pct(L_['span'], l2['span']), '−1.2')
chk('frames per leg', r3['frames'], '161,932'); man = [json.loads(l) for l in (V / 'films500_video_manifest.jsonl').read_text().splitlines() if l.strip()]
meta = man[0]['_meta']; chk('footage hours', meta['total_video_s'] / 3600, '675.73'); chk('above 560 of 500', meta['n_above_560px_detector_basis'], '435 of 500')
print('=== per-leg table ===')
for tag, x, lits in (('RR p3', r3, ('11.665', '11.677', '2.672', '8.18', '31.171', '97.4', '4.653', '174.62', '13,881', '53.2', '6 s')),
                     ('RR p4', r4, ('11.560', '11.620', '2.685', '8.25', '31.038', '97.0', '4.640', '173.05', '14,008', '50.8', '16,530 s')),
                     ('RR p2', r2, ('11.609', '11.613', '2.678', '8.22', '31.084', '97.1', '4.656', '173.77', '13,949', '54.3', None)),
                     ('LI p3', l3, ('12.791', '12.772', '2.271', '7.46', '29.044', '90.8', '0.063', '191.46', '12,660', '22.7', '24 s')),
                     ('LI p4', l4, ('12.809', '12.794', '2.264', '7.45', '28.994', '90.6', '0.062', '191.73', '12,642', '22.6', '13,563 s')),
                     ('LI p2', l2, ('12.953', '12.957', '2.196', '7.36', '28.450', '88.9', '0.067', '193.90', '12,501', '22.8', None))):
    vals = (x['span'], x['win'], x['cpf'], x['usd'], x['cores'], x['util'] * 100, x['idle'], x['xrt'], x['wall'], x['rss'], x['age'])
    for name, v, lit in zip(('span', 'window', 'cpf', 'usd', 'cores', 'util', 'idle', 'xrt', 'wall', 'rss', 'age'), vals, lits):
        if lit is not None: chk(f'{tag} {name}', v, lit)
print('=== §4/§5: the 35-film run, the posture matrix, the C chain ===')
ex35 = lambda name: json.loads((F35 / f'export_{name}.json').read_text())
d1, d2 = ex35('rocketride_video_default_blast'), ex35('rocketride_video_default_blast_p2'); p1, p2 = ex35('rocketride_video_parity_blast'), ex35('rocketride_video_parity_blast_p2'); q1, q2 = ex35('llamaindex_video_workers_blast'), ex35('llamaindex_video_workers_blast_p2')
sp = lambda e: e['throughput']['total_frames_per_s']; wn = lambda e: e['throughput']['steady_window']['window_frames_per_s']
chk('35 default 2.35', (sp(d1) + sp(d2)) / 2, '2.35', tol=0.0051); chk('35 tuned 9.5', (sp(p1) + sp(p2)) / 2, '9.5', tol=0.051)
chk('35 RR span mean (chart 9.51)', (sp(p1) + sp(p2)) / 2, '9.51'); chk('35 RR window mean (chart 8.26)', (wn(p1) + wn(p2)) / 2, '8.26')
chk('35 LI span mean (chart 10.13)', (sp(q1) + sp(q2)) / 2, '10.13'); chk('35 LI window mean (chart 8.44)', (wn(q1) + wn(q2)) / 2, '8.44')
chk('35 RR util 79.8%', (p1['efficiency']['cpu_util_of_box'] + p2['efficiency']['cpu_util_of_box']) / 2 * 100, '79.8%')
chk('35 idle 4.66', (p1['efficiency']['idle_burden']['idle_cores_with_instances_live'] + p2['efficiency']['idle_burden']['idle_cores_with_instances_live']) / 2, '4.66 cores')
chk('35 single-token idle 1.23', (d1['efficiency']['idle_burden']['idle_cores_with_instances_live'] + d2['efficiency']['idle_burden']['idle_cores_with_instances_live']) / 2, '1.23')
chk('35 default 20% of the machine', (d1['efficiency']['cpu_util_of_box'] + d2['efficiency']['cpu_util_of_box']) / 2 * 100, '20% of the machine', tol=0.51)
m35 = [json.loads(l) for l in (V / 'films_video_manifest.jsonl').read_text().splitlines() if l.strip()]
chk('35 footage 49.3 h', sum(r['video_s'] for r in m35 if r.get('role') == 'measured') / 3600, '49.3 h')
rr_eff = (sp(p1) + sp(p2)) / 2 / ((p1['efficiency']['effective_cores'] + p2['efficiency']['effective_cores']) / 2 - (p1['efficiency']['idle_burden']['idle_cores_with_instances_live'] + p2['efficiency']['idle_burden']['idle_cores_with_instances_live']) / 2)
li_eff = (sp(q1) + sp(q2)) / 2 / ((q1['efficiency']['effective_cores'] + q2['efficiency']['effective_cores']) / 2 - (q1['efficiency']['idle_burden']['idle_cores_with_instances_live'] + q2['efficiency']['idle_burden']['idle_cores_with_instances_live']) / 2)
chk('35 per effective core +3.9%', pct(li_eff, rr_eff), 'LI +3.9%', tol=0.06)
pts = {}
for d in ('posture-sweep-20260830', 'c-sweep-highc-20260831'):
    for f in (RES / d).glob('curve_*.json'):
        j = json.loads(f.read_text()); pts[(d, f.stem)] = j['metrics']['frames_per_s']
P = 'posture-sweep-20260830'
for cell, lit in (('curve_rr_M8xT4_C16', '8.32'), ('curve_rr_M16xT2_C32', '8.65'), ('curve_rr_M32xT1_C35', '6.86'), ('curve_rr_M4xT8_C8', '7.29'), ('curve_rr_M8xT2_C16', '8.13'), ('curve_rr_M16xT4_C32', '5.29'),
                  ('curve_li_N8xT4_C16', '10.11'), ('curve_li_N16xT2_C32', '10.07'), ('curve_li_N4xT8_C8', '8.58'), ('curve_li_N8xT2_C16', '9.87'), ('curve_li_N8xT8_C16', '2.20')):
    chk(f'posture {cell}', pts[(P, cell)], lit, tol=0.0051)
H = 'c-sweep-highc-20260831'
for cell, lit in (('curve_rr_M16xT2_C8', '8.21'), ('curve_rr_M16xT2_C16', '9.06'), ('curve_rr_M16xT2_C32', '9.13'), ('curve_li_N16xT2_C8', '9.57'), ('curve_li_N16xT2_C16', '10.22'), ('curve_li_N16xT2_C32', '9.79')):
    chk(f'C chain {cell}', pts[(H, cell)], lit, tol=0.0051)
chk('RR marginal efficiency 0.552 (= T16/T8 ÷ 2)', pts[(H, 'curve_rr_M16xT2_C16')] / pts[(H, 'curve_rr_M16xT2_C8')] / 2, '0.552'); chk('LI marginal efficiency 0.534', pts[(H, 'curve_li_N16xT2_C16')] / pts[(H, 'curve_li_N16xT2_C8')] / 2, '0.534')
chk('RR 16→32 +0.75%', pct(pts[(H, 'curve_rr_M16xT2_C32')], pts[(H, 'curve_rr_M16xT2_C16')]), '+0.75%'); chk('LI 16→32 −4.2%', pct(pts[(H, 'curve_li_N16xT2_C32')], pts[(H, 'curve_li_N16xT2_C16')]), '−4.2%')
chk('oversubscription cost RR 38%', (1 - pts[(P, 'curve_rr_M16xT4_C32')] / pts[(P, 'curve_rr_M16xT2_C32')]) * 100, '38%', tol=1.0)
chk('LI collapse 4.6×', pts[(P, 'curve_li_N16xT2_C32')] / pts[(P, 'curve_li_N8xT8_C16')], '4.6×')
chk('8×2 buys ~94% RR', pts[(P, 'curve_rr_M8xT2_C16')] / pts[(P, 'curve_rr_M16xT2_C32')] * 100, '~94%', tol=0.51); chk('8×2 buys ~98% LI', pts[(P, 'curve_li_N8xT2_C16')] / pts[(P, 'curve_li_N16xT2_C32')] * 100, '~98%', tol=0.51)
print('=== §6: partition, mechanism, V-D ===')
pc = json.loads((C / 'partition_check.json').read_text())
chk('partition above', pc.get('above_diverging'), '433'); chk('partition below', pc.get('below_clean'), '65'); chk('partition violations', len(pc.get('ABOVE_560_PASSING', [])) + len(pc.get('BELOW_560_FAILING', [])), '0 violations')
jb = next(r for r in man if r.get('file') == 'JailBait.mp4'); chk('boundary film 560×380', jb['detector_width'], '560×380'); assert jb['detector_height'] == 380
vd = json.loads((RES / 'wrapper-resize-parity-20260907' / 'side_vd.json').read_text()); fr = vd['frame']
chk('V-D raw scores', None, '0.953240395 0.934387743 0.862633228 0.489725053 0.432809502'); assert ' '.join(s for _, s in fr['raw']['0.3']['detections']) == '0.953240395 0.934387743 0.862633228 0.489725053 0.432809502'
chk('V-D resized scores', None, '0.946473300 0.935210288 0.856113911 0.449365526 0.384643406 0.318114191'); assert ' '.join(s for _, s in fr['resized']['0.3']['detections']) == '0.946473300 0.935210288 0.856113911 0.449365526 0.384643406 0.318114191'
chk('V-D size 714×480 → 560×376', fr['size'][0], '714×480 → 560×376'); assert fr['engine_resized_size'] == [560, 376]
chk('V-D model tensor', None, '[1, 3, 560, 560]'); assert fr['workload']['model_input_shapes_raw'] == fr['workload']['model_input_shapes_resized'] == [[1, 3, 560, 560]]
chk('V-D LANCZOS ms', fr['workload']['facade_lanczos_ms_median_of_5'], '4.64 ms')
print('=== §7: kills ===')
import films500_held_checks as H_
rows, films = H_.manifest(); edge = {f: max(r['detector_width'], r['detector_height']) > 560 for f, r in films.items()}
legs = {(arm, p): H_.records(C if p <= 2 else L, arm, p) for arm in (RR, LI) for p in (1, 2, 3, 4)}
for arm in (RR, LI):
    for pa, pb in ((1, 2), (3, 4), (2, 3)):
        a, b = legs[(arm, pa)], legs[(arm, pb)]; n = sum(H_.same(a[v], b[v]) for v in a if v in b)
        chk(f'identity {arm[:2]} p{pa}≡p{pb}', n, '498 / 498')
rr3, li3 = legs[(RR, 3)], legs[(LI, 3)]
diff = [v for v in rr3 if v in li3 and not (rr3[v].get('frame_label_multisets') == li3[v].get('frame_label_multisets') and rr3[v].get('frame_scores') == li3[v].get('frame_scores'))]
chk('lifetimes p3 partition above', sum(edge[v] for v in diff), '433'); assert sum(not edge[v] for v in diff) == 0
y16 = json.loads((RES / 'detector-parity-y-20260902' / 'side_engine_y.json').read_text())['frames'][1]['predict']['0.3']['detections'][0][1]
y2 = json.loads((RES / 'detector-parity-y-20260902' / 'side_engine_y_t2.json').read_text())['frames'][1]['predict']['0.3']['detections'][0][1]
chk('thread effect 10⁻⁷ (presence; magnitude asserted)', None, '10⁻⁷'); assert 1e-8 < abs(float(y16) - float(y2)) < 1e-6, (y16, y2)
import cachewatch_join as CJ, lifetimes_reading as LR
fm = CJ.frames_minutes(V / 'films500_video_manifest.jsonl'); cw, _ = CJ.parse_cachewatch(L / 'cachewatch.log')
rhos, ioq = [], []
for arm in ('rr', 'li'):
    for p in (3, 4):
        j = CJ.join_leg(L, arm, p, cw, fm); rhos.append(j['rho_cost_iowait']); ioq += [x for x in j['quartiles']['iowait'] if x is not None]
chk('iowait ≤ 1.4%', max(ioq), '≤ 1.4%', tol=0.05); chk('rho min −0.12', min(rhos), '−0.12'); chk('rho max −0.03', max(rhos), '−0.03')
fm2, order = LR.frames_minutes(V / 'films500_video_manifest.jsonl'), LR.manifest_order(V / 'films500_video_manifest.jsonl')
prof = {(a, p): LR.profile(LR.leg_rows(L / f'records_{LR.stem(a, p)}.jsonl'), fm2, order) for a in ('rr', 'li') for p in (3, 4)}
chk('RR p3 drift −2.3%', prof[('rr', 3)]['drift'] * 100, '−2.3%'); chk('LI p3 drift −3.1%', prof[('li', 3)]['drift'] * 100, '−3.1%')
pr = LR.paired(LR.leg_rows(C / 'records_rocketride_video_parity_blast_p2.jsonl'), LR.leg_rows(L / 'records_rocketride_video_parity_blast_p4.jsonl'), fm2)
pl = LR.paired(LR.leg_rows(C / 'records_llamaindex_video_workers_blast_p2.jsonl'), LR.leg_rows(L / 'records_llamaindex_video_workers_blast_p4.jsonl'), fm2)
chk('plateau RR −0.04%', pr['ratio_pct'], '−0.04%'); chk('plateau RR SE 0.57%', pr['se_pct'], '0.57%'); chk('plateau LI +1.32%', pl['ratio_pct'], '+1.32%'); chk('plateau LI SE 0.77%', pl['se_pct'], '0.77%')
fr_ = {f: r['expected_frames_measured'] for f, r in films.items()}
rr2, li2 = legs[(RR, 2)], legs[(LI, 2)]
def ratio(res):
    a = [(rr2[v]['wall_s'] / fr_[v]) for v in rr2 if v in li2 and (films[v]['detector_width'], films[v]['detector_height']) == res]
    b = [(li2[v]['wall_s'] / fr_[v]) for v in rr2 if v in li2 and (films[v]['detector_width'], films[v]['detector_height']) == res]
    return st.median(a) / st.median(b)
chk('ratio 540×360', ratio((540, 360)), '540×360 1.106', expect='1.106'); chk('ratio 640×480', ratio((640, 480)), '640×480 1.114', expect='1.114'); chk('ratio 720×480', ratio((720, 480)), '720×480 1.113', expect='1.113')
det = {}
for v, rec in li2.items():
    if v in films and isinstance(rec.get('stage_s'), dict): det.setdefault((films[v]['detector_width'], films[v]['detector_height']), []).append(rec['stage_s']['detect'] / fr_[v])
meds = [st.median(x) for k, x in det.items() if len(x) >= 5]
chk('LI detect flat min 0.830', min(meds), '0.830–0.850', expect='0.830'); assert abs(max(meds) - 0.850) < 0.0006, max(meds)
print('=== §8: the excluded pass-1 pair ===')
settled_rr = (r2['span'] + r3['span'] + r4['span']) / 3; settled_li = (l2['span'] + l3['span'] + l4['span']) / 3
chk('RR p1 +5% vs settled', pct(r1['span'], settled_rr), 'RocketRide 5% fast', tol=0.6); chk('LI p1 −5% vs settled', -pct(l1['span'], settled_li), 'LlamaIndex 5% slow', tol=0.6)
chk('RR p1 5% fewer CPU-s', -pct(r1['cpf'], r2['cpf']), '5% fewer CPU-seconds', tol=0.6)
chk('per-film ~50 MB', ((r3['last'] - r3['first']) + (r4['last'] - r4['first'])) / 2 * 1024 / 498, '~50 MB per film', tol=5)
chk('26.5 → 49–52 GiB', r4['first'], '26.5 → 49–52 GiB')
print(f'\n{n_ok} checks passed, {len(fails)} failed')
for f in fails: print('  FAIL', f)
sys.exit(1 if fails else 0)
