import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class SuiteComparisonTests(unittest.TestCase):
    def test_same_or_smaller_failure_set_and_portable_green(self):
        spec = importlib.util.spec_from_file_location('compare', ROOT / 'scripts/ci/compare-installer-suites.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        baseline = {'tests': 2, 'failure_ids': ['mac.a', 'stale.b'], 'error_ids': []}
        hotfix = {'tests': 3, 'failure_ids': ['mac.a'], 'error_ids': [], 'applicable_success': True,
                  'applicable_tests': 1, 'applicable_skipped': 0}
        self.assertTrue(module.accept(baseline, hotfix))
        hotfix['failure_ids'].append('new.c')
        self.assertFalse(module.accept(baseline, hotfix))
        hotfix['failure_ids'] = ['mac.a']
        hotfix['applicable_success'] = False
        self.assertFalse(module.accept(baseline, hotfix))
        hotfix['applicable_success'] = True
        hotfix['applicable_tests'] = 0
        self.assertFalse(module.accept(baseline, hotfix))
        hotfix['applicable_tests'] = 1
        baseline['tests'] = 0
        self.assertFalse(module.accept(baseline, hotfix))
        baseline['tests'] = 2
        hotfix['tests'] = 0
        self.assertFalse(module.accept(baseline, hotfix))
        hotfix['tests'] = 3
        hotfix['applicable_skipped'] = 1
        self.assertFalse(module.accept(baseline, hotfix))


if __name__ == '__main__':
    unittest.main()
