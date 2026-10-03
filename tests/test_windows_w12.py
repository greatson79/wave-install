"""W12 Windows function fixtures; no daemon, app or live user home is used."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]

class WindowsW12Tests(unittest.TestCase):
    def test_migration_and_awakening_guards(self):
        pwsh = os.environ.get("PWSH") or shutil.which("pwsh")
        if not pwsh:
            self.skipTest("PWSH required")
        with tempfile.TemporaryDirectory(prefix="w12-windows-") as home:
            result = subprocess.run([pwsh, "-NoProfile", "-File", str(ROOT / "tests/windows_w12_fixture.ps1")], cwd=ROOT, env=dict(os.environ, W12_FIXTURE_HOME=home), text=True, capture_output=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("PASS stale marker rejected; custom directive preserved; mismatch/new blocked", result.stdout)
            self.assertIn("PASS onboarding marker wait", result.stdout)
            self.assertIn("PASS master awake evidence", result.stdout)
            self.assertIn("PASS master launch-agent then queued one-line declaration", result.stdout)
            self.assertEqual(result.stderr, "", result.stderr)

if __name__ == "__main__":
    unittest.main()
