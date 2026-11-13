import contextlib
import importlib.util
import io
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('coverage_gate', ROOT / 'scripts/check-hotfix-coverage.py')
gate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate)


class CoverageGateTests(unittest.TestCase):
    def test_patch_is_required_and_reverting_it_fails(self):
        with tempfile.TemporaryDirectory() as td:
            repo = Path(td)
            def git(*args):
                return subprocess.check_output(['git', '-C', td, *args], stderr=subprocess.DEVNULL).decode().strip()
            git('init')
            git('config', 'user.name', 'Fixture')
            git('config', 'user.email', 'fixture@example.invalid')
            path = repo / 'launcher.txt'
            path.write_text('broken\n')
            git('add', '.')
            git('commit', '-m', 'base')
            base = git('rev-parse', 'HEAD')
            path.write_text('fixed\n')
            git('commit', '-am', 'hotfix')
            commit = git('rev-parse', 'HEAD')
            manifest = {'patches': [{'commit': commit, 'patch_id': gate.patch_id(repo, commit),
                                      'reverse_patch_id': gate.patch_id(repo, commit, reverse=True)}],
                        'assets': []}
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertFalse(gate.audit(repo, manifest))
                git('revert', '--no-edit', commit)
                self.assertTrue(gate.audit(repo, manifest), 'a reverted patch is missing from the current source')
                git('checkout', base)
                self.assertTrue(gate.audit(repo, manifest))


if __name__ == '__main__':
    unittest.main()
