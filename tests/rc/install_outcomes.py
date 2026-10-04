#!/usr/bin/env python3
"""RC 판정기에 종료값 원문·S07~S09 검사를 결합한다. 기존 FAIL/미측정은 승격하지 않는다.
정상 설치 PASS와 noboot 시험 PASS(설치 확인 미완)는 별개다. 기대값은 잡 종류로 선언한다.
"""
import argparse
import importlib.util
import json
from pathlib import Path
import sys

EXPECT = json.loads(Path(__file__).with_name('install-outcome-expect.json').read_text())

def read_state(path):
    d = json.loads(path.read_text(encoding='utf-8-sig'))
    steps = d['steps']
    result = {}
    for prefix in ('S07', 'S08', 'S09'):
        matches = [v for k, v in steps.items() if k[:3] == prefix]
        if len(matches) != 1 or not isinstance(matches[0], dict):
            raise ValueError('단계 누락·중복: ' + prefix)
        v = matches[0]
        result[prefix] = [v['status'], v['exit_code']]
    return d, result

def check(root, osn, gate):
    base = Path(root) / osn
    kind = 'noboot' if gate == 'noboot' else 'normal'
    if gate != 'G1': base /= gate
    exit_name = 'run.exit' if osn == 'win' and gate != 'noboot' else 'exit'
    state_name = {'G1': 'G1_state.json', 'G5': 'state.json', 'noboot': 'install-state.json'}[gate]
    note = ''
    try:
        raw = (base / exit_name).read_text(encoding='utf-8-sig').strip()
        code = int(raw)
        note = '%s/%s exit=%s (기대 %s)' % (base, exit_name, raw, EXPECT[kind]['exit'])
        doc, stages = read_state(base / state_name)
        note += ' · ' + ' '.join('%s=%s/%s' % (k, *v) for k, v in stages.items())
    except (OSError, UnicodeError, ValueError, KeyError, TypeError, AttributeError) as e:
        return 'FAIL', note + ' · 판정 불가: 증거 없음·형식 오류 (%s)' % e
    want = EXPECT[kind]
    if code != want['exit'] or stages != want['stages']:
        return 'FAIL', note
    s07 = next(v for k, v in doc['steps'].items() if k[:3] == 'S07')
    obs = s07.get('observed') or {}
    if kind == 'normal' and isinstance(obs, dict) and obs.get('fleet_state') == 'alive_unconfirmed':
        return 'FAIL', note + ' · 각성 확인 미완'
    return 'PASS', note + (' · 가짜 Claude 시험 기대 일치(설치 성공 아님)' if kind == 'noboot' else '')

def strengthen(rows, root, platforms=('mac', 'win'), gates=('G1', 'G5')):
    for gid in gates:
        row = next((r for r in rows if r['id'] == gid), None)
        if row is None:
            row = {'id': gid, 'title': '실행 종료값·S07~S09'}; rows.append(row)
        if gid == 'G1': row['title'] = 'G1-CI 한 줄 설치·종료값·S07~S09'
        for osn in platforms:
            old = row.get(osn, ['FAIL', '기존 관문 판정 없음'])
            old = list(old)
            old[1] = old[1].replace('S02·S07~S09 = G9 사람 단계(미측정, 통과 아님)', 'S02 실제 로그인은 G9 실기 단계')
            verdict, why = check(root, osn, gid)
            row[osn] = ['FAIL' if verdict == 'FAIL' else old[0], old[1] + ' · ' + why]
    return rows

def raw_report(root):
    root = Path(root)
    lines = ['| 증거 파일 | 값 |', '|---|---|']
    for p in sorted(root.rglob('*')):
        if p.is_file() and (p.name == 'exit' or p.name.endswith('.exit') or p.name == 'exit_code.txt'):
            lines.append('| ./%s | %s |' % (p.relative_to(root), p.read_text(encoding='utf-8-sig').strip()))
    lines += ['', 'S07~S09 상태:']
    for p in sorted(root.rglob('*.json')):
        if p.name not in ('G1_state.json','state.json','install-state.json'): continue
        try:
            d, st = read_state(p)
            obs = next(v for k,v in d['steps'].items() if k[:3]=='S07').get('observed') or {}
            lines.append('./%s %s %s %s' % (p.relative_to(root),d.get('status'), ' '.join('%s=%s/%s'%(k,*v) for k,v in st.items()),obs.get('fleet_state')))
        except (OSError, ValueError, KeyError, TypeError, AttributeError) as e:
            lines.append('./%s 판정 불가: %s' % (p.relative_to(root), e))
    return '\n'.join(lines)+'\n'

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('root',type=Path);ap.add_argument('--gate',type=Path)
    ap.add_argument('--json',action='store_true');ap.add_argument('--platforms',default='mac,win')
    ap.add_argument('--gates',default='G1,G5');ap.add_argument('--raw-table',type=Path)
    ap.add_argument('--noboot',choices=('mac','win'))
    a=ap.parse_args()
    if a.raw_table:
        a.raw_table.write_text(raw_report(a.root),encoding='utf-8')
    if a.noboot:
        verdict, why = check(a.root, a.noboot, 'noboot')
        print('%s: %s' % (verdict, why)); return int(verdict != 'PASS')
    if not a.gate:
        if a.raw_table: return 0
        ap.error('--gate 또는 --raw-table 필요')
    spec=importlib.util.spec_from_file_location('base_gate',a.gate)
    gate=importlib.util.module_from_spec(spec);spec.loader.exec_module(gate)
    rows=strengthen(gate.judge(a.root),a.root,a.platforms.split(','),a.gates.split(','))
    print(json.dumps(rows,ensure_ascii=False,indent=1) if a.json else gate.render(rows))
    return int(any(v[0]!='PASS' for r in rows for k,v in r.items() if k in ('mac','win','common')))

if __name__=='__main__':sys.exit(main())
