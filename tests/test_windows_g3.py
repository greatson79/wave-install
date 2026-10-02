"""G3 receipt validation fixtures, isolated from the live pack and all processes."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
ROOT = Path(__file__).resolve().parents[1]
class WindowsG3Tests(unittest.TestCase):
    def test_original_injection_receipt(self):
        pwsh = os.environ.get('PWSH') or shutil.which('pwsh')
        if not pwsh:
            self.skipTest('PWSH required')
        with tempfile.TemporaryDirectory(prefix='windows-g3-') as home:
            result = subprocess.run([pwsh, '-NoProfile', '-File', str(ROOT/'tests/windows_g3_fixture.ps1')], cwd=ROOT, env=dict(os.environ, W12_FIXTURE_HOME=home), capture_output=True, text=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stdout+result.stderr)
            self.assertIn('PASS G3', result.stdout)
            self.assertEqual(result.stderr, '')
if __name__ == '__main__':
    unittest.main()
