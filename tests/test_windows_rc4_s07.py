"""rc.4 S07 Windows function fixtures; no daemon, app or live user home is used."""
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class WindowsRc4S07Tests(unittest.TestCase):
    def run_fixture(self, mode, env=None):
        pwsh = os.environ.get("PWSH") or shutil.which("pwsh")
        if not pwsh:
            self.skipTest("PWSH required")
        return subprocess.run([pwsh, "-NoProfile", "-File", str(ROOT / "tests/windows_rc4_s07_fixture.ps1"), "-Mode", mode],
                              cwd=ROOT, env=dict(os.environ, **(env or {})), text=True, capture_output=True, timeout=60)

    def test_budget_pause_and_unfinished_outcome(self):
        r = self.run_fixture("unit")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("PASS budget = 420s + paused gate time", r.stdout)
        self.assertIn("PASS unfinished: alive seats -> alive_unconfirmed, none alive -> failure", r.stdout)

    def test_alive_unconfirmed_exits_2_without_help_code(self):
        with tempfile.TemporaryDirectory() as td:
            r = self.run_fixture("exit2", {"RC4_FIXTURE_DIR": td})
            self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
            self.assertEqual((Path(td) / "rec.txt").read_text().strip().splitlines()[-1], "S07_INITIAL_FLEET|failed|2|WT-S07-FLEET")


if __name__ == "__main__":
    unittest.main()
