"""Migration proof, using isolated homes; no real learner configuration is read."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


# PowerShell itself writes profile/module caches under the (test) home: AppData on Windows,
# ~/.local/share/powershell and ~/.cache/powershell with pwsh. They are not migration writes.
POWERSHELL_RUNTIME = ('AppData', '.local', '.cache')


def snapshot(root):
    result = {}
    for p in root.rglob('*'):
        if p.relative_to(root).parts[0] in POWERSHELL_RUNTIME:
            continue
        key = str(p.relative_to(root))
        if p.is_symlink():
            result[key] = ('link', os.readlink(p))
        elif p.is_file():
            result[key] = hashlib.sha256(p.read_bytes()).hexdigest()
        else:
            result[key] = 'dir'
    return result


class MigrationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.home = Path(self.tmp.name).resolve()
        self.src = self.home / '.claude'
        self.account = self.home / 'custom/account'
        self.local = self.home / 'custom/local'
        self.env = dict(os.environ, HOME=str(self.home), USERPROFILE=str(self.home),
                        WAVE_MIGRATE_SRC=str(self.src), CYS_ACCOUNT_DIR=str(self.account),
                        CYS_LOCAL_DIR=str(self.local))
        self.payload = '한글 원문\r\n보존\n'.encode()
        for path in ('CLAUDE.md', 'skills/설교도우미/SKILL.md', 'agents/도우미.md',
                     'commands/clash.md', 'commands/명령.md',
                     'projects/-Users-x-작업/memory/메모.md',
                     'projects/-Users-x-작업/transcript.jsonl',
                     'projects/-Users-x-작업/memory/transcript.jsonl',
                     'projects/-Users-x-작업/other/private.txt'):
            self.put(self.src / path, self.payload)
        self.put(self.src / 'settings.json', json.dumps({
            'hooks': {'PreToolUse': [{'command': 'SECRET-HOOK'}]},
            'mcpServers': {'fixture-mcp': {'token': 'SECRET-TOKEN'}}}).encode())
        self.put(self.home / '.claude.json', b'{"mcpServers":{"home-mcp":{"token":"SECRET"}}}')
        self.put(self.account / 'CLAUDE.md', b'existing\r\n')
        self.put(self.account / 'commands/clash.md', b'keep')
        self.put(self.local / 'existing.txt', b'local')
        try:
            (self.src / 'skills/link').symlink_to(self.home, target_is_directory=True)
            (self.src / 'skills/설교도우미/escape').symlink_to(self.home, target_is_directory=True)
        except OSError:
            if os.name != 'nt':
                raise
        engine = os.environ.get('MIGRATE_ENGINE', 'powershell' if os.name == 'nt' else 'bash')
        if engine == 'bash':
            self.command = ['/bin/bash', str(ROOT / 'scripts/migrate.sh')]
            self.dry = '--dry-run'
        else:
            exe = shutil.which(engine)
            if not exe:
                self.skipTest(engine + ' unavailable')
            self.command = [exe, '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File',
                            str(ROOT / 'scripts/migrate.ps1')]
            self.dry = '-DryRun'

    def put(self, path, data):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)

    def run_script(self, *flags, ok=True):
        p = subprocess.run(self.command + list(flags), env=self.env, capture_output=True, timeout=30)
        if ok:
            self.assertEqual(p.returncode, 0, (p.stdout + p.stderr).decode('utf-8', 'replace'))
        else:
            self.assertNotEqual(p.returncode, 0)
        return p.stdout.decode('utf-8', 'replace')

    def test_dry_run_writes_nothing(self):
        before = snapshot(self.home)
        output = self.run_script(self.dry)
        self.assertEqual(snapshot(self.home), before)
        self.assertIn('DRY RUN', output)
        self.assertIn('PreToolUse', output)

    def test_bytes_backup_source_unchanged_and_idempotency(self):
        before = snapshot(self.src)
        account_before, local_before = snapshot(self.account), snapshot(self.local)
        self.run_script()
        self.assertEqual(snapshot(self.src), before)
        for path in ('agents/도우미.md', 'commands/명령.md', 'projects/-Users-x-작업/memory/메모.md'):
            self.assertEqual((self.account / path).read_bytes(), self.payload)
        self.assertEqual((self.local / 'skills/설교도우미/SKILL.md').read_bytes(), self.payload)
        self.assertEqual((self.account / 'commands/clash.md').read_bytes(), b'keep')
        self.assertFalse(any(self.account.rglob('*.jsonl')))
        self.assertFalse(any(self.account.rglob('private.txt')))
        self.assertFalse(any(p.is_symlink() for p in self.local.rglob('*')))
        md = (self.account / 'CLAUDE.md').read_bytes()
        self.assertTrue(md.startswith(b'existing\r\n'))
        self.assertIn(self.payload, md)
        self.assertIn(hashlib.sha256(self.payload).hexdigest().encode(), md)
        backups = sorted((self.home / '.cys/backup').glob('migrate-*'))
        self.assertEqual(len(backups), 1)
        self.assertEqual(snapshot(backups[0] / 'claude'), account_before)
        self.assertEqual(snapshot(backups[0] / 'local'), local_before)
        report = (backups[0] / 'report.txt').read_text(encoding='utf-8-sig')
        for label in ('PreToolUse', 'fixture-mcp', 'home-mcp', 'clash', 'copied', 'backup'):
            self.assertIn(label, report)
        self.assertNotIn('SECRET', report)
        if (self.src / 'skills/link').is_symlink():
            self.assertIn('symlink', report)
        state = snapshot(self.account), snapshot(self.local)
        self.run_script()
        self.assertEqual((snapshot(self.account), snapshot(self.local)), state)
        self.assertEqual(snapshot(self.src), before)

    def test_source_with_historical_marker_is_idempotent(self):
        self.put(self.src / 'CLAUDE.md', self.payload +
                 b'<!-- migrated from ~/.claude/CLAUDE.md old -->\n'
                 b'<!-- source sha256: historical -->\nold\n<!-- end migrated -->\n')
        self.run_script()
        before = (self.account / 'CLAUDE.md').read_bytes()
        self.run_script()
        self.assertEqual((self.account / 'CLAUDE.md').read_bytes(), before)

    def test_standalone_hash_marker_does_not_suppress_append(self):
        marker = '<!-- source sha256: ' + hashlib.sha256(self.payload).hexdigest() + ' -->\n'
        self.put(self.account / 'CLAUDE.md', marker.encode())
        self.run_script()
        self.assertIn(self.payload, (self.account / 'CLAUDE.md').read_bytes())

    def test_symlinked_settings_are_skipped(self):
        settings = self.home / '.claude.json'
        settings.unlink()
        try:
            settings.symlink_to(self.src / 'settings.json')
        except OSError:
            self.skipTest('symlink privilege unavailable')
        self.run_script()
        self.assertTrue(settings.is_symlink())

    def test_nested_destination_symlink_is_skipped(self):
        outside = self.home / 'outside'
        outside.mkdir()
        try:
            (self.account / 'agents').symlink_to(outside, target_is_directory=True)
        except OSError:
            self.skipTest('symlink privilege unavailable')
        output = self.run_script()
        self.assertEqual(list(outside.iterdir()), [])
        self.assertIn('symlink', output)
        self.assertTrue((self.account / 'commands/명령.md').exists())

    def test_rejects_destination_inside_source_before_writing(self):
        self.env['CYS_LOCAL_DIR'] = str(self.src / 'nested')
        before = snapshot(self.home)
        self.run_script(ok=False)
        self.assertEqual(snapshot(self.home), before)

    def test_rejects_destination_symlink_before_writing(self):
        link = self.home / 'linked'
        try:
            link.symlink_to(self.account, target_is_directory=True)
        except OSError:
            self.skipTest('symlink privilege unavailable')
        self.env['CYS_ACCOUNT_DIR'] = str(link)
        before = snapshot(self.home)
        self.run_script(ok=False)
        self.assertEqual(snapshot(self.home), before)


if os.name != 'nt' and shutil.which('pwsh') and not os.environ.get('MIGRATE_ENGINE'):
    class PwshMigrationTests(MigrationTests):
        def setUp(self):
            super().setUp()
            self.command = [shutil.which('pwsh'), '-NoProfile', '-File',
                            str(ROOT / 'scripts/migrate.ps1')]
            self.dry = '-DryRun'


if __name__ == '__main__':
    unittest.main()
