"""Mutate workflow controls: a valid YAML file alone is not sufficient."""
import copy
import importlib.util
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('workflow_check', ROOT/'tests/workflow-check.py')
checker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(checker)


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.workflow = checker.load(ROOT/'.github/workflows/windows-smoke.yml')

    def test_checked_in_workflow(self):
        self.assertEqual(checker.validate(self.workflow), [])

    def test_unsafe_workflow_mutants(self):
        def mutate(name, change, expected):
            with self.subTest(name=name):
                value = copy.deepcopy(self.workflow)
                change(value)
                self.assertTrue(any(expected in e for e in checker.validate(value)))
        mutate('no matrix', lambda w: w['jobs']['bootstrap-contract'].update({'runs-on': 'windows-latest'}), 'OS matrix')
        mutate('early PowerShell', lambda w: w['jobs']['bootstrap-contract']['steps'].insert(1, {'shell': 'pwsh', 'run': 'Write-Host hi'}), 'first executable check')
        mutate('implicit release', lambda w: w['on']['workflow_dispatch']['inputs']['release_smoke'].update(default='true'), 'opt-in boolean')
        mutate('required pin', lambda w: w['on']['workflow_dispatch']['inputs']['terminal_tag'].update(required='true'), 'pin-free dispatch')
        mutate('install on PR', lambda w: w['jobs']['signed-install'].pop('if'), 'real installation must be opt-in')
        mutate('skip contracts', lambda w: w['jobs']['signed-install'].pop('needs'), 'depend on contract matrix')
        mutate('ignore failure', lambda w: w['jobs']['bootstrap-contract'].update({'continue-on-error': 'true'}), 'propagate failures')
        mutate('write token', lambda w: w.update(permissions={'contents': 'write'}), 'read-only token')
        def unguard_pin(w):
            for s in w['jobs']['bootstrap-contract']['steps']:
                if checker.is_live_pin(s.get('run', '')):
                    s.pop('if')
        mutate('live download in default run', unguard_pin, 'pin check must be opt-in')

    def test_duplicate_yaml_keys_are_rejected(self):
        with tempfile.TemporaryDirectory(dir=ROOT, prefix='.yaml-test-') as td:
            path = Path(td)/'workflow.yml'
            path.write_text('jobs:\n  check: {}\n  check: {}\n')
            with self.assertRaisesRegex(ValueError, 'duplicate YAML key'):
                checker.load(path)

if __name__ == '__main__':
    unittest.main(verbosity=2)
