"""Portable launch/encoding guards; Windows runtime proofs live in hotfix_av_proof.ps1."""
from pathlib import Path
import json
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]


class AvLaunchTests(unittest.TestCase):
    def test_no_direct_installed_exe_launches(self):
        source = (ROOT / 'bootstrap.ps1').read_text(encoding='utf-8-sig')
        self.assertIsNone(re.search(r'& \$(?:cys|cysd|app)\b|Start-Process -FilePath \$(?:app|cys)\b|Start-Process -FilePath \(Join-Path \$WaveHome', source))
        helper = source.split('function Invoke-BoundedCheck(', 1)[1].split('\nfunction ', 1)[0]
        self.assertIn('$env:SystemRoot\\System32\\cmd.exe', helper)
        self.assertIn('taskkill.exe', helper)
        self.assertIn('/T /F /PID', helper)

    def test_encoding_and_hint(self):
        boot = (ROOT / 'bootstrap.ps1').read_bytes()
        start = (ROOT / 'win-start.ps1').read_bytes()
        self.assertTrue(boot.startswith(b'\xef\xbb\xbf'))
        self.assertTrue(start.startswith(b'& {'))
        start.decode('ascii')
        source = boot.decode('utf-8-sig')
        row = source.split('"code": "J-AV-03"', 1)[1].split('}', 1)[0]
        self.assertIn('안랩 Safe Transaction(ASTx)·V3·알약', row)
        self.assertIn('작업 표시줄', row)
        actions = json.loads('{"code": "J-AV-03"' + row + '}')
        points = re.search(r'Write-Host \(-join \(\[char\[\]\]\(([^)]+)\)', start.decode('ascii'))
        self.assertIsNotNone(points)
        self.assertEqual(''.join(chr(int(n)) for n in points[1].split(',')), actions['action1'] + ' ' + actions['action2'])


if __name__ == '__main__':
    unittest.main()
