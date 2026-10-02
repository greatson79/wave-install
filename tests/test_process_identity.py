import importlib.util
import json
import os
from pathlib import Path
import unittest
import subprocess
import shutil
import sys
import tempfile
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('process_identity', ROOT/'scripts/ci/process_identity.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

class IdentityEvidenceTests(unittest.TestCase):
    def test_measurement_imports_sibling_with_isolated_python_path(self):
        result = subprocess.run([sys.executable, '-I', str(ROOT/'scripts/ci/p0-measure.py'), '--help'],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('--surface-probes', result.stdout)

    def test_chain_keeps_caller_and_all_observed_parents(self):
        table = {30: dict(pid=30,parent_pid=20,executable='cys.exe'),
                 20: dict(pid=20,parent_pid=10,executable='bash.exe'),
                 10: dict(pid=10,parent_pid=1,executable='powershell.exe')}
        self.assertEqual([r['pid'] for r in m.parent_chain(30, table)], [30,20,10])
        self.assertEqual(m.parent_chain(99, table), [])

    def test_cycle_terminates_without_invented_parents(self):
        table = {1: dict(pid=1,parent_pid=2), 2: dict(pid=2,parent_pid=1)}
        self.assertEqual([r['pid'] for r in m.parent_chain(1,table)], [1,2])

    def test_unrelated_cys_process_is_not_hook_caller(self):
        observer = m.ProcessObserver()
        observer.records[(7,8)] = dict(caller_pid=7,parent_chain=[{'pid':7},{'pid':8}])
        observer.records[(9,10)] = dict(caller_pid=9,parent_chain=[{'pid':9},{'pid':10}])
        with patch.object(observer.thread,'join'):
            result = observer.finish(8)
        self.assertEqual([r['caller_pid'] for r in result['cys_processes']], [7])
        self.assertEqual(result['state'],'observed')
        self.assertEqual([r['caller_pid'] for r in result['unassociated_cys_processes']], [9])
        self.assertIn('no relationship', result['unassociated_note'])

    def test_missed_short_lived_caller_is_unmeasured(self):
        observer = m.ProcessObserver()
        with patch.object(observer.thread,'join'):
            result = observer.finish(123)
        self.assertEqual(result['state'],'unmeasured')
        self.assertEqual(result['cys_processes'],[])

    def test_observer_failure_is_preserved(self):
        observer = m.ProcessObserver()
        with patch.object(m,'windows_snapshot',side_effect=OSError('snapshot denied')):
            observer.collect()
        self.assertIn('snapshot denied',observer.errors[0])

    def test_root_presence_snapshots_keep_missing_and_seen_states(self):
        observer = m.ProcessObserver()
        observer.set_root(20)
        observer.record_snapshot({})
        observer.record_snapshot({20: dict(pid=20,parent_pid=1,executable='bash.exe')})
        observer.record_snapshot({20: dict(pid=20,parent_pid=1,executable='bash.exe')})
        observer.record_snapshot({})
        with patch.object(observer.thread,'join'):
            result = observer.finish(20)
        self.assertEqual(result['snapshot_count'],4)
        self.assertEqual(result['root_sample_count'],4)
        self.assertEqual(result['root_seen_count'],2)
        self.assertEqual([r['present'] for r in result['root_snapshots']], [False,True,False])
        self.assertEqual(result['root_snapshots'][1]['parent_chain'][0]['pid'],20)
        self.assertEqual(result['state'],'unmeasured')

    def test_unassociated_only_observation_is_not_promoted_to_associated(self):
        observer = m.ProcessObserver()
        observer.record_snapshot({7:dict(pid=7,parent_pid=9,executable='cys.exe')})
        with patch.object(observer.thread,'join'):
            result = observer.finish(20)
        self.assertEqual(result['state'],'unmeasured')
        self.assertEqual(len(result['unassociated_cys_processes']),1)
        self.assertEqual(result['root_sample_count'],0)

    def test_hook_trace_baseline_is_separate_and_environment_restored(self):
        import textwrap
        source = (ROOT/'scripts/ci/p0-measure.py').read_text()
        start = source.index("            prior_trace =")
        end = source.index("            # Keep the unmodified hook baseline", start)
        block = textwrap.dedent(source[start:end])
        for fail_traced, files_present in ((False, False), (False, True), (True, False)):
            with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {'CYS_HOOK_IDENTITY_TRACE': 'prior'}):
                out = Path(tmp)
                labels = []
                saved = {}
                def run(label, *args, **kwargs):
                    labels.append(label)
                    if label == 'session-start-master':
                        self.assertNotIn('CYS_HOOK_IDENTITY_TRACE', os.environ)
                    if label == 'hook-trace-path':
                        (out/'hook-trace-path.stdout').write_text('/converted/trace prefix\n')
                    if label == 'session-start-master-traced':
                        self.assertEqual(os.environ['CYS_HOOK_IDENTITY_TRACE'], '/converted/trace prefix')
                        self.assertTrue(kwargs['observe_identity'])
                        if fail_traced:
                            raise RuntimeError('fixture interruption')
                        if files_present:
                            for suffix in ('.pid', '.ps.stdout', '.ps.stderr', '.ps.exit'):
                                (out/('session-start-master-trace' + suffix)).write_bytes(b'')
                    return {'exit_code': 0}
                scope = dict(os=os, run=run, bash='bash', pack=out, out=out, Path=Path, hashlib=__import__('hashlib'), save=lambda name, value: saved.update({name: value}))
                if fail_traced:
                    with self.assertRaises(RuntimeError):
                        exec(block, scope)
                else:
                    exec(block, scope)
                self.assertEqual(labels, ['session-start-master', 'hook-trace-path', 'session-start-master-traced'])
                self.assertEqual(os.environ['CYS_HOOK_IDENTITY_TRACE'], 'prior')
                if not fail_traced:
                    self.assertEqual(saved['hook-trace-files.json']['trace_available'], files_present)
                    if files_present:
                        self.assertTrue(all(row['bytes'] == 0 and len(row['sha256']) == 64 for row in saved['hook-trace-files.json']['files']))

    def test_bash_probes_preserve_quoted_path_arguments_and_failure_code(self):
        path_bash = shutil.which('bash')
        bash = path_bash
        if os.name == 'nt':
            # PATH bash may be the Windows/WSL launcher; this test requires Git MSYS.
            git = shutil.which('git')
            self.assertIsNotNone(git, 'Git for Windows is required for this regression')
            candidates = [parent / 'usr/bin/bash.exe' for parent in Path(git).resolve().parents]
            bash = next((str(path) for path in candidates
                         if path.is_file() and path.with_name('cygpath.exe').is_file()), None)
        self.assertIsNotNone(bash, 'Git MSYS bash with sibling cygpath was not found')
        print('Bash regression executable: ' + bash, flush=True)
        bash_env = dict(os.environ, PATH=str(Path(bash).parent) + os.pathsep + os.environ.get('PATH', ''))
        evidence_path = os.environ.get('W3_BASH_EVIDENCE')
        evidence = {'platform': sys.platform, 'python': sys.executable,
                    'path_bash_candidate': path_bash, 'selected_bash': bash,
                    'selected_cygpath': str(Path(bash).with_name('cygpath.exe')) if os.name == 'nt' else None,
                    'conversions': []}
        def record_conversion(label, command, env):
            try:
                result = subprocess.run(command, capture_output=True, text=True, env=env, timeout=15)
                row = {'label': label, 'command': command, 'exit_code': result.returncode,
                       'stdout': result.stdout, 'stderr': result.stderr}
            except subprocess.TimeoutExpired as exc:
                row = {'label': label, 'command': command, 'timed_out': True,
                       'stdout': (exc.stdout or b'').decode(errors='replace'),
                       'stderr': (exc.stderr or b'').decode(errors='replace')}
                result = None
            except OSError as exc:
                row = {'label': label, 'command': command, 'exit_code': None, 'error': repr(exc)}
                result = None
            evidence['conversions'].append(row)
            if evidence_path:
                target = Path(evidence_path)
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(json.dumps(evidence, ensure_ascii=False, indent=2), encoding='utf-8')
            return result
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "space and 'quote"
            root.mkdir()
            cys = root / 'cys-probe.sh'
            cys.write_text('#!/bin/sh\nprintf "%s:%s\\n" "$1" "$2"\necho denied >&2\nexit 7\n', newline='\n')
            cys.chmod(0o755)
            timeout = root / 'timeout-probe.sh'
            timeout.write_text('#!/bin/sh\nshift\nexec "$@"\n', newline='\n')
            timeout.chmod(0o755)
            def bash_path(path):
                if os.name != 'nt':
                    return str(path)
                if evidence_path:
                    # Reproduce the former runner PATH selection on the same fixture.
                    record_conversion('former-path-bash', ['bash', '-c', 'cygpath -u "$1"', '_', str(path)], os.environ)
                converted = record_conversion('explicit-git-msys',
                    [bash, '-c', 'cygpath -u "$1"', '_', str(path)], bash_env)
                self.assertIsNotNone(converted, 'Explicit Git MSYS conversion failed to start or timed out')
                self.assertEqual(converted.returncode, 0, f'bash={bash} stdout={converted.stdout!r} stderr={converted.stderr!r}')
                self.assertTrue(converted.stdout.strip(), 'cygpath returned an empty path')
                return converted.stdout.strip()
            cys_path, timeout_path = bash_path(cys), bash_path(timeout)
            for label, script in m.claim_probe_scripts(cys_path, timeout_path).items():
                result = subprocess.run([bash,'-c',script],capture_output=True,text=True,env=bash_env)
                self.assertEqual(result.returncode,7,(label,result.stderr))
                self.assertIn('claim-role:master',result.stdout)
                self.assertIn('denied',result.stderr if label.endswith('direct') else result.stdout)
            self.assertNotIn('bash-claim-timeout-substitution',m.claim_probe_scripts(cys_path))

if __name__ == '__main__':
    unittest.main()
