#!/usr/bin/env python3
"""Windows release assets are self-contained and pinned by the published bootstrap."""
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[1]
BASE = 'https://github.com/greatson79/wave-install/releases/download/v0.3.0'


class WindowsReleaseTests(unittest.TestCase):
    def test_wave_terminal_assembly_includes_pinned_windows_entry(self):
        with tempfile.TemporaryDirectory() as folder:
            out = Path(folder)
            (out / 'app-asset').write_bytes(b'fixture')
            result = subprocess.run(['bash', str(ROOT / 'scripts/assemble-wave-terminal-release.sh'),
                                     'greatson79/wave-terminal', '0.2.5', folder], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            for name in ('bootstrap.ps1', 'win-start.ps1', 'wave-install-0.3.0.zip', 'steps.json'):
                self.assertTrue((out / name).is_file(), name)
            start = (out / 'win-start.ps1').read_text(encoding='utf-8-sig')
            self.assertIn('https://github.com/greatson79/wave-terminal/releases/download/v0.2.5/bootstrap.ps1', start)
            self.assertIn(hashlib.sha256((out / 'bootstrap.ps1').read_bytes()).hexdigest(), start)
            self.assertNotIn('__WAVE_BOOTSTRAP_', start)
            with zipfile.ZipFile(out / 'wave-install-0.3.0.zip') as archive:
                self.assertEqual(archive.read('wave-install-0.3.0/steps.json'), (out / 'steps.json').read_bytes())
            self.assertEqual(json.loads((out / 'steps.json').read_text())['release']['asset_name']['windows_x64'],
                             'wave-terminal-0.2.5-windows-x64-setup.exe')
            check = subprocess.run(['shasum', '-a', '256', '-c', 'SHA256SUMS'], cwd=out, capture_output=True, text=True)
            self.assertEqual(check.returncode, 0, check.stdout + check.stderr)

    def test_zip_and_powershell_bootstrap_are_pinned(self):
        with tempfile.TemporaryDirectory() as folder:
            out = Path(folder)
            result = subprocess.run(['bash', str(ROOT / 'scripts/make-release.sh'), '0.3.0', BASE, folder],
                                    capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            zip_path = out / 'wave-install-0.3.0.zip'
            zip_sha = hashlib.sha256(zip_path.read_bytes()).hexdigest()
            bootstrap = (out / 'bootstrap.ps1').read_text(encoding='utf-8-sig')
            self.assertIn(BASE + '/wave-install-0.3.0.zip', bootstrap)
            self.assertIn(zip_sha, bootstrap)
            self.assertNotIn('__WAVE_INSTALL_ZIP_', bootstrap)
            with zipfile.ZipFile(zip_path) as archive:
                names = archive.namelist()
                self.assertEqual({name.split('/')[0] for name in names}, {'wave-install-0.3.0'})
                for required in ('bootstrap.ps1', 'steps.json', 'install-state.json', 'wave-pack/manifest.json', 'LICENSE', 'reinstall.sh', 'reinstall.ps1'):
                    self.assertIn('wave-install-0.3.0/' + required, names)
                self.assertIn(b'__WAVE_INSTALL_ZIP_SHA256__', archive.read('wave-install-0.3.0/bootstrap.ps1'))
            checksums = (out / 'SHA256SUMS').read_text()
            self.assertEqual(len(checksums.splitlines()), 4)
            check = subprocess.run(['shasum', '-a', '256', '-c', 'SHA256SUMS'], cwd=out,
                                   capture_output=True, text=True)
            self.assertEqual(check.returncode, 0, check.stdout + check.stderr)


if __name__ == '__main__':
    unittest.main()
