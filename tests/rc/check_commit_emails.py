#!/usr/bin/env python3
"""rc.4 입력 기준점 이후 커밋만 검사한다. 옛 이력은 변경하지 않는다.
작성자와 커미터 모두 지정 이메일이어야 한다. 기준점·대상·이력이 없으면 실패한다.
"""
import argparse
import json
import os
import re
from pathlib import Path
import shutil
import subprocess
import sys

EMAIL='greatson79@gmail.com'

def git_binary():
    return '/opt/homebrew/bin/git' if Path('/opt/homebrew/bin/git').is_file() else shutil.which('git')

def judge(repo, baseline, head, git=None, env=None):
    git=git or git_binary()
    def run(*args):
        p=subprocess.run([git,'-C',str(repo),*args],env=env,capture_output=True,text=True)
        if p.returncode: raise ValueError(p.stderr.strip())
        return p.stdout.strip()
    try:
        base=run('rev-parse','--verify',baseline+'^{commit}')
        target=run('rev-parse','--verify',head+'^{commit}')
        if run('rev-parse','--is-shallow-repository')!='false':
            raise ValueError('얕은 이력은 검사 불가: fetch-depth 0 필요')
        try:
            run('merge-base','--is-ancestor',base,target)
        except ValueError as e:
            raise ValueError('기준점이 입력의 조상이 아님 또는 조상 확인 실패') from e
        raw=run('log','--format=%H%x09%ae%x09%ce',base+'..'+target)
        lines=raw.splitlines() if raw else []
        bad=[]
        for line in lines:
            fields=line.split('\t')
            if len(fields)!=3 or fields[1:]!=[EMAIL,EMAIL]:bad.append(line)
        report='기준 %s → 입력 %s · 새 커밋 %d개\n'%(base,target,len(lines))
        report+='SHA\t작성자 이메일\t커미터 이메일\n'+raw+'\n'
        report+=('FAIL: 불일치 %d개'%len(bad)) if bad else ('PASS' if lines else '검사 0건')
        return int(bool(bad)),report
    except (OSError,TypeError,ValueError) as e:
        return 1,'FAIL: 이력 판정 불가: '+str(e)

def zero_input_warning(counts):
    return 'WARN: 모든 검사 입력이 기준점과 같음(검사 0건)' if len(counts) == 4 and all(n == 0 for n in counts) else ''

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--repo',type=Path,default=Path('.'))
    ap.add_argument('--app-repo',type=Path,required=True)
    ap.add_argument('--mac-head',required=True);ap.add_argument('--win-head',required=True)
    ap.add_argument('--runner-head',default='HEAD')
    ap.add_argument('--inputs',type=Path,default=Path(__file__).with_name('rc-inputs.json'))
    ap.add_argument('--baseline',type=Path,default=Path(__file__).with_name('rc4-email-baseline.json'))
    ap.add_argument('--out',type=Path,required=True)
    a=ap.parse_args();reports=[];failed=False;counts=[]
    try:
        base=json.loads(a.baseline.read_text());inputs=json.loads(a.inputs.read_text())
        targets=[('installer',a.repo,inputs['installer_sha']),('runner',a.repo,a.runner_head),
                 ('mac',a.app_repo,a.mac_head),('win',a.app_repo,a.win_head)]
        for label,repo,head in targets:
            rc,report=judge(repo,base['app' if label in ('mac','win') else label],head);failed|=bool(rc)
            match=re.search(r'새 커밋 ([0-9]+)개',report);counts.append(int(match.group(1)) if match else -1)
            reports.append('[%s]\n%s'%(label,report))
    except (OSError,ValueError,KeyError) as e:
        reports.append('FAIL: 입력·기준점 읽기 실패: '+str(e));failed=True
    warning=zero_input_warning(counts)
    text='\n\n'.join(reports)+('\n'+warning if warning else '')+'\n';a.out.parent.mkdir(parents=True,exist_ok=True)
    a.out.write_text(text,encoding='utf-8');print(text,end='');return int(failed)

if __name__=='__main__':sys.exit(main())
