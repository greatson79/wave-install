#!/usr/bin/env python3
"""Windows release assets are self-contained and pinned by the published bootstrap."""
import hashlib
from pathlib import Path
import subprocess
import tempfile
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[1]
BASE = 'https://github.com/greatson79/wave-install/releases/download/v0.2.0'


class WindowsReleaseTests(unittest.TestCase):
    def test_zip_and_powershell_bootstrap_are_pinned(self):
        with tempfile.TemporaryDirectory() as folder:
            out = Path(folder)
            result = subprocess.run(['bash', str(ROOT / 'scripts/make-release.sh'), '0.2.0', BASE, folder],
                                    capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            zip_path = out / 'wave-install-0.2.0.zip'
            zip_sha = hashlib.sha256(zip_path.read_bytes()).hexdigest()
            bootstrap = (out / 'bootstrap.ps1').read_text(encoding='utf-8-sig')
            self.assertIn(BASE + '/wave-install-0.2.0.zip', bootstrap)
            self.assertIn(zip_sha, bootstrap)
            self.assertNotIn('__WAVE_INSTALL_ZIP_', bootstrap)
            with zipfile.ZipFile(zip_path) as archive:
                names = archive.namelist()
                self.assertEqual({name.split('/')[0] for name in names}, {'wave-install-0.2.0'})
                for required in ('bootstrap.ps1', 'steps.json', 'install-state.json', 'wave-pack/manifest.json'):
                    self.assertIn('wave-install-0.2.0/' + required, names)
                self.assertIn(b'__WAVE_INSTALL_ZIP_SHA256__', archive.read('wave-install-0.2.0/bootstrap.ps1'))
            checksums = (out / 'SHA256SUMS').read_text()
            self.assertEqual(len(checksums.splitlines()), 4)
            check = subprocess.run(['shasum', '-a', '256', '-c', 'SHA256SUMS'], cwd=out,
                                   capture_output=True, text=True)
            self.assertEqual(check.returncode, 0, check.stdout + check.stderr)


if __name__ == '__main__':
    unittest.main()
