import importlib.util
from pathlib import Path
import unittest
import subprocess
import sys
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

if __name__ == '__main__':
    unittest.main()
