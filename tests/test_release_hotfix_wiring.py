"""Release prerequisites and actual generated win-start bytes, without running the installer."""
import importlib.util
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class ReleaseHotfixWiringTests(unittest.TestCase):
    def test_generated_entry_is_ascii_without_bom(self):
        source = (ROOT / 'scripts/assemble-wave-terminal-release.sh').read_text()
        block = source.split('python3 - "$STAGE/src/win-start.ps1"', 1)[1].split("<<'PY'\n", 1)[1].split('\nPY', 1)[0]
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            bootstrap = root / 'bootstrap.ps1'
            bootstrap.write_text('fixture')
            target = root / 'win-start.ps1'
            subprocess.run([sys.executable, '-', str(ROOT / 'win-start.ps1'), str(target),
                            'https://example.invalid/bootstrap.ps1', str(bootstrap)],
                           input=block, text=True, check=True)
            self.assertTrue(target.read_bytes().startswith(b'& {'))
            self.assertTrue(target.read_bytes().isascii())

    def test_ascii_entry_is_the_only_bom_free_exception(self):
        spec = importlib.util.spec_from_file_location('balance', ROOT / 'tests/ps-balance.py')
        checker = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(checker)
        with tempfile.TemporaryDirectory() as td:
            entry = Path(td) / 'win-start.ps1'
            entry.write_bytes(b'& { Write-Host "fixture" }')
            self.assertEqual(checker.check_bom(entry), [])
            entry.write_text('& { Write-Host "한글" }')
            self.assertTrue(checker.check_bom(entry))
            other = Path(td) / 'bootstrap.ps1'
            other.write_bytes(b'& { }')
            self.assertTrue(checker.check_bom(other))

    def test_release_and_pin_both_require_gates_before_work(self):
        for file, boundary in [('scripts/assemble-wave-terminal-release.sh', 'STAGE='),
                               ('tests/win-pin-check.py', '    values = pins(args.steps)')]:
            source = (ROOT / file).read_text()
            for gate in ('check-installer-launch.py', 'check-hotfix-coverage.py'):
                self.assertIn(gate, source)
                self.assertLess(source.index(gate), source.index(boundary))


if __name__ == '__main__':
    unittest.main()
