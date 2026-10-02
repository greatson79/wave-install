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
# Windows embeddable Python ._pth may omit the script directory. Resolve our sibling explicitly.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from process_identity import ProcessObserver, parent_chain, windows_snapshot, claim_probe_scripts

p = argparse.ArgumentParser()
p.add_argument('--app', required=True)
p.add_argument('--evidence', required=True)
p.add_argument('--surface-probes', action='store_true')
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

def run(label, command, timeout=60, stdin=b'', observe_identity=False):
    started = time.time()
    result = dict(label=label, command=list(map(str, command)), timeout_seconds=timeout)
    result.update(state='started', started_at=started)
    results.append(result)
    save('surface-executions.json' if a.surface_probes else 'executions.json', results)
    observer = ProcessObserver() if observe_identity else None
    proc = None
    if observer:
        observer.start()
    try:
        with (out/(label+'.stdout')).open('wb') as stdout_file, (out/(label+'.stderr')).open('wb') as stderr_file:
            proc = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=stdout_file, stderr=stderr_file)
            if observer:
                observer.set_root(proc.pid)
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
    if observer:
        observed = observer.finish(proc.pid if proc else None)
        observed['inherited_environment'] = {key: os.environ.get(key) for key in
                                             ('CYS_SURFACE_ID', 'AITERM_SURFACE_ID', 'CYS_SOCKET', 'AITERM_SOCKET', 'CYS_ROLE')}
        observed['command'] = list(map(str, command))
        save(label+'-identity.json', observed)
    result['elapsed_seconds'] = round(time.time()-started, 3)
    save('surface-executions.json' if a.surface_probes else 'executions.json', results)
    print(json.dumps(result), flush=True)
    return result

if a.surface_probes:
    # This process is a real PTY descendant; daemon caller identity comes from its ancestry.
    identity = {'pid': os.getpid(), 'parent_pid': os.getppid(),
                'environment': {key: os.environ.get(key) for key in
                                ('CYS_SURFACE_ID', 'AITERM_SURFACE_ID', 'CYS_SOCKET', 'AITERM_SOCKET', 'CYS_ROLE')},
                'collection': 'Actual PTY descendant; environment captured without overriding identity'}
    try:
        identity['parent_chain'] = parent_chain(os.getpid(), windows_snapshot())
    except Exception as exc:
        identity['parent_chain_unmeasured'] = repr(exc)
    save('surface-identity.json', identity)
    claim = run('phase-3-claim-role', [cys, 'claim-role', 'master'], 15, observe_identity=True)
    if claim.get('exit_code') == 0:
        os.environ['CYS_ROLE'] = 'master'
        bash = shutil.which('bash')
        if bash:
            # Baseline is always untraced; the opt-in rerun has separate output files.
            prior_trace = os.environ.pop('CYS_HOOK_IDENTITY_TRACE', None)
            try:
                run('session-start-master', [bash, str(pack/'hooks/session-start.sh')], 60, b'{}\n', observe_identity=True)
                trace_prefix = str(out / 'session-start-master-trace')
                converted = run('hook-trace-path', [bash, '-c', 'cygpath -u "$1"', '_', trace_prefix], 15)
                trace_path = ((out/'hook-trace-path.stdout').read_text(encoding='utf-8', errors='replace').strip()
                              if converted.get('exit_code') == 0 else '')
                if trace_path and '\n' not in trace_path:
                    os.environ['CYS_HOOK_IDENTITY_TRACE'] = trace_path
                    run('session-start-master-traced', [bash, str(pack/'hooks/session-start.sh')],
                        60, b'{}\n', observe_identity=True)
                    trace_files = []
                    for suffix in ('.pid', '.ps.stdout', '.ps.stderr', '.ps.exit'):
                        path = Path(trace_prefix + suffix)
                        item = {'path': str(path), 'exists': path.is_file()}
                        if item['exists']:
                            try:
                                raw = path.read_bytes()
                                item.update(bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest())
                            except OSError as exc:
                                item['read_error'] = repr(exc)
                        trace_files.append(item)
                    save('hook-trace-files.json', {
                        'files': trace_files,
                        'trace_available': all(item['exists'] and 'sha256' in item for item in trace_files),
                        'note': 'Missing trace files mean unmeasured; traced hook exit alone is not trace evidence. Empty files are valid captured output.'})
                else:
                    save('hook-trace-unmeasured.json', {'reason': 'Bash cygpath failed to resolve one trace prefix'})
            finally:
                if prior_trace is None:
                    os.environ.pop('CYS_HOOK_IDENTITY_TRACE', None)
                else:
                    os.environ['CYS_HOOK_IDENTITY_TRACE'] = prior_trace
            # Keep the unmodified hook baseline first, then compare Bash invocation forms.
            path_probe = run('bash-cys-path', [bash, '-c', 'command -v cys'], 15)
            if path_probe.get('exit_code') == 0:
                bash_cys = (out/'bash-cys-path.stdout').read_text(encoding='utf-8', errors='replace').strip()
                run('bash-cys-details', [bash, '-c', 'p=$(command -v cys) || exit; printf "resolved=%s\\n" "$p"; if command -v cygpath >/dev/null 2>&1; then cygpath -w "$p"; fi; if command -v sha256sum >/dev/null 2>&1; then sha256sum "$p"; fi'], 15)
                save('direct-cys-binary.json', {'path': cys, 'sha256': hashlib.sha256(Path(cys).read_bytes()).hexdigest(),
                                              'comparison': 'Compare bash-cys-details.stdout; unresolved path/hash equality remains unverified'})
                timeout_probe = run('bash-timeout-path', [bash, '-c', 'command -v timeout'], 15)
                bash_timeout = ((out/'bash-timeout-path.stdout').read_text(encoding='utf-8', errors='replace').strip()
                                if timeout_probe.get('exit_code') == 0 else None)
                if bash_cys and '\n' not in bash_cys:
                    for label, script in claim_probe_scripts(bash_cys, bash_timeout).items():
                        run(label, [bash, '-c', script], 15, observe_identity=True)
                    if not bash_timeout:
                        save('bash-timeout-unmeasured.json', {'reason': 'This Bash has no timeout command'})
                else:
                    save('bash-probes-unmeasured.json', {'reason': 'command -v cys did not return one path'})
            else:
                save('bash-probes-unmeasured.json', {'reason': 'This Bash could not resolve cys'})
            events = run('claim-denied-events', [cys, 'events', '--after-seq', '0', '--name', 'role.claim_denied'], 3)
            save('claim-denied-events-collection.json', {
                'expected_timeout': True, 'timed_out': events.get('timed_out'),
                'stdout_bytes': events.get('stdout_bytes'),
                'note': 'Bounded stream capture. Timeout is the intended stop, not a successful probe verdict. Raw events may include earlier claims; correlate timestamps and caller_pid.'})

        else:
            save('hook-unmeasured.json', {'reason': 'Bash unavailable; original hook and Bash comparison probes were not executed'})
    else:
        save('hook-unmeasured.json', {'reason':'Real-surface claim failed; directive bytes unavailable'})
    run('phase-2-ping', [cys, 'ping'], 15)
    llms = {name:shutil.which(name) for name in ('claude','codex','agy','gemini','grok')}
    save('llm-availability.json', llms)
    if any(llms.values()):
        save('boot-unmeasured.json', {'reason':'LLM CLI present; no-LLM boundary', 'paths':llms})
    else:
        run('phase-4-boot', [cys, 'boot'], 300)
    run('phase-5-check', [sys.executable, str(pack/'bin/javis_orchestra.py'), 'check'], 60)
    if not any(llms.values()):
        run('bootstrap-chain', [sys.executable, str(pack/'bin/javis_bootstrap.py')], 360)
    state_dir = Path.home()/'.cys/state'
    for f in state_dir.glob('boot*.json') if state_dir.exists() else []:
        shutil.copyfile(f, out/f.name)
    save('surface-done.json', {'completed':True})
    sys.exit(0)

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
# Preserve the product's preflight phase, then run identity-sensitive probes in a real PTY.
run('phase-1-preflight-fix', [sys.executable, str(preflight), '--fix'], 300)
run('preflight-after', [sys.executable, str(preflight), '--json'], 180)
run('daemon-list', [cys, 'list'], 30)
run('create-surface', [cys, 'new-surface', '--title', 'P0-measurement'], 30)
surface_file = out/'create-surface.stdout'
match = re.search(r'surface:(\d+)', surface_file.read_text(errors='replace')) if surface_file.exists() else None
if not match:
    save('surface-unmeasured.json', {'reason':'No real surface returned'})
    sys.exit(1)
ref = 'surface:'+match.group(1)
def ps_quote(value):
    return "'"+str(value).replace("'", "''")+"'"
command = '& '+ps_quote(sys.executable)+' '+ps_quote(Path(__file__).resolve())+' --app '+ps_quote(app)+' --evidence '+ps_quote(out)+' --surface-probes'
run('surface-send', [cys, 'send', '--surface', ref, command], 15)
run('surface-submit', [cys, 'send-key', '--surface', ref, 'Return'], 15)
deadline = time.monotonic()+600
while time.monotonic() < deadline and not (out/'surface-done.json').exists():
    time.sleep(2)
run('surface-screen', [cys, 'read-screen', '--surface', ref], 15)
finished = (out/'surface-done.json').exists()
save('measurement-status.json', {'collection_finished':finished, 'product_pass':None, 'probe_mode':'real PTY descendant for role/hook/boot; individual probes and actual fail-fast chain', 'llm_invoked':False})
sys.exit(0 if finished else 1)
