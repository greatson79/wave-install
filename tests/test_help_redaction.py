import importlib.util
import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

class HelpRedactionTests(unittest.TestCase):
    def safe(self, text, username='alice'):
        path = ROOT / 'lib/install_help.py'
        self.assertTrue(path.exists(), 'R5 redaction module must exist')
        spec = importlib.util.spec_from_file_location('install_help', path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module.safe_text(text, username)

    def test_secrets_and_accounts_are_removed(self):
        secrets = ['alice@example.com', 'Bearer secretvalue', 'sk-abcdefghijklmn',
                   'abcdefghijabcdefghij#abcdefgh', 'ghp_abcdefghijklmnopqrstuvwxyz',
                   'github_pat_abcdefghijklmnopqrstuvwxyz', 'login-secret']
        source = '\n'.join(secrets[:-1]) + '\nPaste code here if prompted > login-secret\n' + r'C:\Users\alice\log' + '\n/Users/alice/log\n/home/alice/log\nUSERNAME=alice\nwhoami: alice\nalice'
        result = self.safe(source)
        for value in secrets + ['alice']:
            self.assertNotIn(value, result)
        self.assertIn('<EMAIL>', result)
        self.assertIn('<TOKEN>', result)
        self.assertIn('<USER>', result)

    def test_control_characters_removed_without_losing_newlines(self):
        self.assertEqual(self.safe('a\x1b[31m\x00\x7fb\n다음'), 'ab\n다음')

    @unittest.skipUnless(os.environ.get('PWSH') or shutil.which('pwsh'), 'PowerShell is required for OS parity')
    def test_windows_and_mac_same_redaction(self):
        samples = [
            'alice@example.com Bearer secretvalue sk-abcdefghijklmn',
            'abcdefghijabcdefghij#abcdefgh ghp_abcdefghijklmnopqrstuvwxyz',
            'Paste code here if prompted > login-secret',
            r'C:\Users\alice\log' + '\n/Users/alice/log /home/alice/log',
            'USERNAME=alice\nwhoami: domain/alice\nalice',
            'a\x1b[31m\x00\x7fb\n다음',
            'aliceSuffix <TOKEN> <USER>',
        ]
        with tempfile.TemporaryDirectory() as td:
            data = Path(td)/'input.json'
            data.write_text(json.dumps(samples), encoding='utf-8')
            script = Path(td)/'parity.ps1'
            script.write_text("param($Module,$InputFile)\n$ErrorActionPreference='Stop'\n. $Module\n@((Get-Content $InputFile -Raw | ConvertFrom-Json) | ForEach-Object { ConvertTo-HelpSafeText $_ 'alice' }) | ConvertTo-Json -Compress\n", encoding='utf-8-sig')
            result = subprocess.run([os.environ.get('PWSH') or shutil.which('pwsh'), '-NoProfile', '-File', str(script), str(ROOT/'lib/install-help.ps1'), str(data)], capture_output=True, text=True, timeout=10)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(result.stdout.lstrip('\ufeff')), [self.safe(x) for x in samples])

    def test_spaced_account_and_ansi_cannot_leak(self):
        for source in (r'C:\Users\Alice Smith\log', '/Users/Alice Smith/log'):
            self.assertNotIn('Smith', self.safe(source, 'Alice Smith'))
        self.assertEqual(self.safe('sk-abcd\x1b[31mefghijkl'), '<TOKEN>')
        self.assertEqual(self.safe('al\x1b[31mice'), '<USER>')
        self.assertEqual(self.safe('sk-abcd\x1b]0;title\x07efghijkl'), '<TOKEN>')

    def test_short_username_does_not_destroy_unrelated_words(self):
        self.assertEqual(self.safe('run curl now; user=a; a', 'a'), 'run curl now; user=<USER>; <USER>')

if __name__ == '__main__':
    unittest.main()
