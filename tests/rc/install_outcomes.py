#!/usr/bin/env python3
"""RC 판정기에 종료값 원문·S07~S09 검사를 결합한다. 기존 FAIL/미측정은 승격하지 않는다.
정상 설치 PASS와 noboot 시험 PASS(설치 확인 미완)는 별개다. 기대값은 잡 종류로 선언한다.
"""
import argparse
import importlib.util
import json
import re
from pathlib import Path
import sys

EXPECTATIONS = {
    'rc4': json.loads(Path(__file__).with_name('install-outcome-expect.json').read_text()),
    'rc5': json.loads(Path(__file__).with_name('install-outcome-expect-rc5.json').read_text()),
}
RC5_BOOT_NOTICE = '각성 미확인: master 좌석은 살아 있지만 Claude 세션 기록에서 답변을 찾지 못했습니다. 설치는 계속합니다. Wave Terminal 의 master 창에서 자비스가 응답하는지 확인해 주세요.'

def read_state(path):
    d = json.loads(path.read_text(encoding='utf-8-sig'))
    steps = d['steps']
    result = {}
    for prefix in ('S07', 'S08', 'S09'):
        matches = [v for k, v in steps.items() if k[:3] == prefix]
        if len(matches) != 1 or not isinstance(matches[0], dict):
            raise ValueError('단계 누락·중복: ' + prefix)
        v = matches[0]
        code = v['exit_code']
        if code is not None and type(code) is not int:
            raise ValueError('단계 exit_code 정수 형식 오류: ' + prefix)
        result[prefix] = [v['status'], code]
    return d, result

def _compare_observed(doc, step, required, note):
    try:
        observed = doc['steps'][step]['observed']
    except (KeyError, TypeError):
        return 'FAIL', note + ' · 관측값 없음: ' + step
    if not isinstance(observed, dict):
        return 'FAIL', note + ' · 관측 객체 형식 오류: ' + step
    for key, want in required.items():
        got = observed.get(key)
        if type(got) is not type(want) or got != want:
            return 'FAIL', note + ' · ' + step + '.' + key + '=' + repr(got) + ' (기대 ' + repr(want) + ')'
    return None

def _check_rc5_noboot(base, doc, note):
    wanted = EXPECTATIONS['rc5']['noboot']
    for step, key in (('S07_INITIAL_FLEET','S07_observed'),('S08_VERIFY','S08_observed')):
        result = _compare_observed(doc, step, wanted[key], note)
        if result:
            return result
    if doc.get('status') != 'complete' or doc.get('required_steps_passed') is not True:
        return 'FAIL', note + ' · 최상위 설치 완료 확인 불일치'
    if not (base / 'marker_absent').is_file():
        return 'FAIL', note + ' · marker_absent 증거 없음'
    try:
        raw = (base / 'cys-status.json').read_bytes()
        status = json.loads(raw.decode('utf-8-sig'))
        surfaces = status['surfaces']
    except (OSError, UnicodeError, ValueError, KeyError, TypeError) as e:
        return 'FAIL', note + ' · 원문 cys status --json 판정 불가: ' + str(e)
    if not isinstance(surfaces, list):
        return 'FAIL', note + ' · 원문 cys status surfaces 목록 아님'
    for role in ('master','cso','worker'):
        matches = [x for x in surfaces if isinstance(x,dict) and x.get('role') == role]
        if len(matches) != 1:
            return 'FAIL', note + ' · 원문 cys status 역할 수 불일치: ' + role
        seat = matches[0]
        if seat.get('exited') is not False or seat.get('agent_alive') is not True or type(seat.get('launch_complete')) is not bool or seat['launch_complete'] is not True:
            signal = {key: seat.get(key) for key in ('role','exited','agent_alive','launch_complete')}
            return 'FAIL', note + ' · 원문 cys status 역할 신호 불일치: ' + repr(signal)
    try:
        install_log = (base / 'install.log').read_text(encoding='utf-8-sig')
    except (OSError, UnicodeError) as e:
        return 'FAIL', note + ' · install.log 없음·형식 오류: ' + str(e)
    if RC5_BOOT_NOTICE not in install_log:
        return 'FAIL', note + ' · install.log에 각성 미확인 안내 없음'
    return None

def check(root, osn, gate, schema):
    if schema not in EXPECTATIONS:
        return 'FAIL', '판정 불가: s07_schema 미설정·미지원 (' + repr(schema) + ')'
    base = Path(root) / osn
    kind = 'noboot' if gate == 'noboot' else 'normal'
    expect = EXPECTATIONS[schema][kind]
    if gate != 'G1': base /= gate
    exit_name = 'run.exit' if osn == 'win' and gate != 'noboot' else 'exit'
    state_name = {'G1': 'G1_state.json', 'G5': 'state.json', 'noboot': 'install-state.json'}[gate]
    note = ''
    try:
        raw = (base / exit_name).read_text(encoding='utf-8-sig').strip()
        if not re.fullmatch(r'0|[1-9][0-9]*', raw):
            raise ValueError('종료값은 ASCII 숫자만 허용')
        code = int(raw)
        note = '%s/%s exit=%s (기대 %s)' % (base, exit_name, raw, expect['exit'])
        doc, stages = read_state(base / state_name)
        note += ' · ' + ' '.join('%s=%s/%s' % (k, *v) for k, v in stages.items())
    except (OSError, UnicodeError, ValueError, KeyError, TypeError, AttributeError) as e:
        return 'FAIL', note + ' · 판정 불가: 증거 없음·형식 오류 (%s)' % e
    want = expect
    if code != want['exit'] or stages != want['stages']:
        return 'FAIL', note
    s07 = next(v for k, v in doc['steps'].items() if k[:3] == 'S07')
    obs = s07.get('observed')
    if not isinstance(obs, dict):
        return 'FAIL', note + ' · S07 관측 객체 없음'
    if schema == 'rc5':
        if kind == 'normal':
            required = {'fleet_started':True,'seats':3,'roles':['master','cso','worker']}
            result = _compare_observed(doc, 'S07_INITIAL_FLEET', required, note)
            if result: return result
            if type(obs.get('launch_complete')) is not int or obs['launch_complete'] != 3:
                return 'FAIL', note + ' · S07_INITIAL_FLEET.observed.launch_complete=' + repr(obs.get('launch_complete')) + ' (기대 정수 3)'
            if type(obs.get('master_marker_present')) is not bool:
                return 'FAIL', note + ' · S07_INITIAL_FLEET.observed.master_marker_present 형식 오류'
            if doc.get('status') != 'complete' or doc.get('required_steps_passed') is not True:
                return 'FAIL', note + ' · 최상위 설치 완료 확인 불일치'
        else:
            result = _check_rc5_noboot(base, doc, note)
            if result: return result
    elif kind == 'normal':
        if doc.get('status') != 'complete' or doc.get('required_steps_passed') is not True:
            return 'FAIL', note + ' · 최상위 설치 완료 확인 불일치'
        if obs.get('fleet_started') is not True or type(obs.get('seats')) is not int or obs['seats'] != 3 or obs.get('roles') != ['master','cso','worker']:
            return 'FAIL', note + ' · S07 세 역할 시작 확인 불일치'
        if osn == 'mac': ready = obs.get('master_marker_verified') is True
        else: ready = all(obs.get(k) is True for k in ('master_awakened','child_alive','cso_alive'))
        if not ready: return 'FAIL', note + ' · rc.4 S07 완료 근거 불일치'
    elif obs.get('fleet_started') is not False or obs.get('fleet_state') != 'alive_unconfirmed':
        return 'FAIL', note + ' · 확인 미완 관측 불일치'
    return 'PASS', note + (' · 가짜 Claude 시험 기대 일치(설치 성공 아님)' if kind == 'noboot' else '')

def strengthen(rows, root, platforms, gates, schema):
    for gid in gates:
        row = next((r for r in rows if r['id'] == gid), None)
        if row is None:
            row = {'id': gid, 'title': '실행 종료값·S07~S09'}; rows.append(row)
        if gid == 'G1': row['title'] = 'G1-CI 한 줄 설치·종료값·S07~S09'
        for osn in platforms:
            old = row.get(osn, ['FAIL', '기존 관문 판정 없음'])
            old = list(old)
            old[1] = old[1].replace('S02·S07~S09 = G9 사람 단계(미측정, 통과 아님)', 'S02 실제 로그인은 G9 실기 단계')
            verdict, why = check(root, osn, gid, schema=schema)
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
    ap.add_argument('--noboot',choices=('mac','win'));ap.add_argument('--schema',choices=('rc4','rc5'))
    a=ap.parse_args()
    try:
        declared=json.loads(Path(__file__).with_name('rc-inputs.json').read_text())['s07_schema']
        schema=a.schema or declared
        if schema != declared: raise ValueError('CLI schema와 rc-inputs.json 불일치')
    except (OSError,ValueError,KeyError,TypeError) as e:
        print('FAIL: 러너 입력 스키마 판정 불가: '+str(e));return 1
    if a.raw_table:
        a.raw_table.write_text(raw_report(a.root),encoding='utf-8')
    if a.noboot:
        verdict, why = check(a.root, a.noboot, 'noboot',schema=schema)
        print('%s: %s' % (verdict, why)); return int(verdict != 'PASS')
    if not a.gate:
        if a.raw_table: return 0
        ap.error('--gate 또는 --raw-table 필요')
    spec=importlib.util.spec_from_file_location('base_gate',a.gate)
    gate=importlib.util.module_from_spec(spec);spec.loader.exec_module(gate)
    rows=strengthen(gate.judge(a.root),a.root,a.platforms.split(','),a.gates.split(','),schema=schema)
    print(json.dumps(rows,ensure_ascii=False,indent=1) if a.json else gate.render(rows))
    return int(any(v[0]!='PASS' for r in rows for k,v in r.items() if k in ('mac','win','common')))

if __name__=='__main__':sys.exit(main())
