"""P0 observations only. Run with the installed app's Python, never runner Python."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time

p = argparse.ArgumentParser()
p.add_argument('--app', required=True)
p.add_argument('--evidence', required=True)
a = p.parse_args()
app, out = Path(a.app), Path(a.evidence)
pack = Path.home() / '.cys' / 'pack'
os_path = os.environ['PATH']
paths = [app, app/'runtime/python', app/'runtime/git/cmd', app/'runtime/git/usr/bin', app/'runtime/node']
os.environ['PATH'] = os.pathsep.join(map(str, paths)) + os.pathsep + os_path
os.environ['CYS_PACK_DIR'] = str(pack)
os.environ['PYTHONIOENCODING'] = 'utf-8'
cys = str(app/'cys.exe')
results = []

def save(name, value):
    temp = out/(name+'.tmp')
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
    os.replace(temp, out/name)

def run(label, command, timeout=60, stdin=b''):
    started = time.time()
    result = dict(label=label, command=list(map(str, command)), timeout_seconds=timeout)
    result.update(state='started', started_at=started)
    results.append(result)
    save('executions.json', results)
    try:
        with (out/(label+'.stdout')).open('wb') as stdout_file, (out/(label+'.stderr')).open('wb') as stderr_file:
            proc = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=stdout_file, stderr=stderr_file)
            try:
                proc.communicate(stdin, timeout=timeout)
                result.update(exit_code=proc.returncode, timed_out=False, state='completed')
            except subprocess.TimeoutExpired:
                subprocess.run(['taskkill', '/PID', str(proc.pid), '/T', '/F'], capture_output=True, timeout=15)
                proc.communicate(timeout=15)
                result.update(exit_code=proc.returncode, timed_out=True, state='timed_out')
        stdout = (out/(label+'.stdout')).read_bytes()
        stderr = (out/(label+'.stderr')).read_bytes()
        result.update(stdout_bytes=len(stdout), stderr_bytes=len(stderr), stdout_sha256=hashlib.sha256(stdout).hexdigest())
    except Exception as exc:
        result.update(exit_code=None, error=repr(exc), unmeasured=True, state='unmeasured')
    result['elapsed_seconds'] = round(time.time()-started, 3)
    save('executions.json', results)
    print(json.dumps(result), flush=True)
    return result

runtimes = []
for tool in ('python3', 'bash', 'git', 'node', 'uv'):
    found = shutil.which(tool)
    supplier = 'absent'
    if found:
        supplier = 'app' if Path(found).resolve().is_relative_to(app.resolve()) else 'OS-or-runner'
    row = dict(tool=tool, path=found, supplier=supplier)
    if found:
        row['sha256'] = hashlib.sha256(Path(found).read_bytes()).hexdigest()
        row['execution'] = run('runtime-'+tool, [found, '--version'], 20)
    runtimes.append(row)
save('runtimes.json', runtimes)
save('environment.json', {'python':sys.executable, 'home':str(Path.home()), 'path':os.environ['PATH'], 'scope':'Fresh standard user; hosted tools excluded from PATH, not uninstalled'})
run('init-pack', [cys, 'init-pack'], 120)
preflight, bootstrap = pack/'bin/javis_preflight.py', pack/'bin/javis_bootstrap.py'
source = []
for f in (preflight, bootstrap, pack/'hooks/session-start.sh', pack/'hooks/_lib.sh'):
    if f.is_file():
        source.append({'path':str(f), 'bytes':f.stat().st_size, 'sha256':hashlib.sha256(f.read_bytes()).hexdigest()})
        shutil.copyfile(f, out/('source-'+f.name))
save('pack-source.json', source)
# Preserve the untouched preflight JSON before --fix can change the disposable profile.
run('preflight-before', [sys.executable, str(preflight), '--json'], 180)
# Establish a real shell surface. No LLM CLI or authentication fixture is installed.
run('daemon-list', [cys, 'list'], 30)
surface = run('create-surface', [cys, 'new-surface', '--title', 'P0-measurement'], 30)
surface_file = out/'create-surface.stdout'
match = re.search(r'surface:(\d+)', surface_file.read_text(errors='replace')) if surface_file.exists() else None
if match:
    os.environ['CYS_SURFACE_ID'] = match.group(1)
    os.environ['CYS_ROLE'] = 'master'
    bash = shutil.which('bash')
    if bash:
        run('session-start-master', [bash, str(pack/'hooks/session-start.sh')], 60, b'{}\n')
else:
    save('hook-unmeasured.json', {'reason':'No real surface returned; no fabricated surface id injected'})
# Each phase is an independent diagnostic probe. Later probes may run after failure;
# this does not claim that the complete bootstrap chain reached them naturally.
run('phase-1-preflight-fix', [sys.executable, str(preflight), '--fix'], 300)
run('preflight-after', [sys.executable, str(preflight), '--json'], 180)
run('phase-2-ping', [cys, 'ping'], 15)
run('phase-3-claim-role', [cys, 'claim-role', 'master'], 15)
llms = {name:shutil.which(name) for name in ('claude','codex','agy','gemini','grok')}
save('llm-availability.json', llms)
if any(llms.values()):
    save('boot-unmeasured.json', {'reason':'LLM CLI present; no-LLM measurement boundary', 'paths':llms})
else:
    run('phase-4-boot', [cys, 'boot'], 300)
run('phase-5-check', [sys.executable, str(pack/'bin/javis_orchestra.py'), 'check'], 60)
# Actual bootstrap invocation preserves its own fail-fast behavior and boot-last evidence.
if not any(llms.values()):
    run('bootstrap-chain', [sys.executable, str(bootstrap)], 360)
for f in (pack/'round').glob('boot*.json') if (pack/'round').exists() else []:
    shutil.copyfile(f, out/f.name)
save('measurement-status.json', {'collection_finished':True, 'product_pass':None, 'probe_mode':'individual phases plus actual fail-fast chain', 'llm_invoked':False})
