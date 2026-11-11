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


# PowerShell itself writes profile/module caches under the (test) home (PS 5.1 resolves AppData from
# %USERPROFILE% via the registry, so env vars cannot move it). Only these exact PowerShell-owned trees
# are ignored; anything else under AppData/.local/.cache still counts as a write and fails the test.
POWERSHELL_OWNED = (
    ('AppData', 'Local', 'Microsoft', 'Windows', 'PowerShell'),
    ('AppData', 'Local', 'Microsoft', 'PowerShell'),
    ('AppData', 'Roaming', 'Microsoft', 'Windows', 'PowerShell'),
    ('.local', 'share', 'powershell'),
    ('.cache', 'powershell'),
    ('.config', 'powershell'),
)


def powershell_owned(parts):
    # A PowerShell-owned tree itself, anything inside it, or one of its parent folders.
    return any(parts[:len(owned)] == owned or owned[:len(parts)] == parts for owned in POWERSHELL_OWNED)


def snapshot(root):
    result = {}
    for p in root.rglob('*'):
        if powershell_owned(p.relative_to(root).parts):
            continue
        key = str(p.relative_to(root))
        if p.is_symlink():
            result[key] = ('link', os.readlink(p))
        elif p.is_file():
            result[key] = hashlib.sha256(p.read_bytes()).hexdigest()
        else:
            result[key] = 'dir'
    return result


class SnapshotFilterTests(unittest.TestCase):
    def test_only_powershell_owned_trees_are_ignored(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for rel in ('AppData/Local/Microsoft/Windows/PowerShell/StartupProfileData-NonInteractive',
                        '.local/share/powershell/Modules/x.txt', 'AppData/stray.txt',
                        'AppData/Local/wave-stray/x.txt', '.local/share/wave/x.txt', '.cache/other.txt'):
                (root / rel).parent.mkdir(parents=True, exist_ok=True)
                (root / rel).write_text('x')
            keys = {Path(k).as_posix() for k, v in snapshot(root).items() if v != 'dir'}
            self.assertEqual(keys, {'AppData/stray.txt', 'AppData/Local/wave-stray/x.txt',
                                    '.local/share/wave/x.txt', '.cache/other.txt'})


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
            self.command = ['/bin/bash', str(ROOT / 'scripts/migrate.sh'), '--yes']
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
        command = [arg for arg in self.command if arg != '--yes'] if flags else self.command
        p = subprocess.run(command + list(flags), env=self.env, capture_output=True, timeout=30)
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


    @unittest.skipIf(os.name == 'nt', 'macOS pipe entry point')
    def test_piped_yes_migrates(self):
        p = self.pipe_shell('--yes')
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual((self.account / 'agents/도우미.md').read_bytes(), self.payload)
        for text in ('옮긴 것 5개', '건너뛴 것 1개(이름 충돌)', '훅·MCP 목록', '백업 위치', '보고서 위치'):
            self.assertIn(text, p.stdout.decode())

    @unittest.skipIf(os.name == 'nt', 'macOS pipe entry point')
    def test_piped_dry_and_no_tty_write_nothing(self):
        for flags in (('--dry-run',), ()):
            with self.subTest(flags=flags):
                before = snapshot(self.home)
                p = self.pipe_shell(*flags)
                self.assertEqual(p.returncode, 0, p.stderr)
                self.assertEqual(snapshot(self.home), before)
                self.assertIn(b'DRY RUN', p.stdout)
                if not flags:
                    self.assertIn('--yes', p.stdout.decode())

    def pipe_shell(self, *flags):
        return subprocess.run(['/bin/bash', '-s', '--', *flags],
                              input=(ROOT / 'scripts/migrate.sh').read_bytes(),
                              env=self.env, capture_output=True, timeout=30, start_new_session=True)

    @unittest.skipUnless(os.name == 'nt', 'requires Windows PowerShell 5.1')
    def test_starter_yes_no_and_hash_mismatch(self):
        template = ROOT / 'scripts/migrate-start.ps1'
        self.assertTrue(template.is_file(), 'migration starter must exist')
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            pin = hashlib.sha256((ROOT / 'scripts/migrate.ps1').read_bytes()).hexdigest()
            for answer, digest in (('N', pin), ('Y', '0' * 64), ('Y', pin)):
                with self.subTest(answer=answer, digest=digest):
                    starter = tmp / 'starter.ps1'
                    starter.write_bytes(template.read_bytes().replace(b'__WAVE_MIGRATE_PS1_SHA256__', digest.encode()))
                    env = dict(self.env, WAVE_MIGRATE_ANSWER=answer,
                               WAVE_MIGRATE_PS1_URL=(ROOT / 'scripts/migrate.ps1').as_uri(),
                               TEMP=str(tmp), TMP=str(tmp))
                    before = snapshot(self.home)
                    p = subprocess.run([shutil.which('powershell'), '-NoProfile', '-ExecutionPolicy',
                                        'Bypass', '-Command',
                                        "Get-Content -Raw -LiteralPath '" + str(starter).replace("'", "''") + "' | Invoke-Expression"],
                                       env=env, capture_output=True, timeout=30)
                    if digest != pin:
                        self.assertNotEqual(p.returncode, 0)
                        self.assertIn(b'SHA_MISMATCH', p.stdout + p.stderr)
                    else:
                        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
                    self.assertEqual(sorted(p.name for p in tmp.iterdir()), ['starter.ps1'])
                    if answer == 'N' or digest != pin:
                        self.assertEqual(snapshot(self.home), before)
                    else:
                        self.assertEqual((self.account / 'agents/도우미.md').read_bytes(), self.payload)
                        self.assertIn('옮긴 것 5개', p.stdout.decode('utf-8-sig'))


class SiteAssemblyTests(unittest.TestCase):
    def test_starter_encoding(self):
        p = ROOT / 'scripts/migrate-start.ps1'
        self.assertTrue(p.is_file(), 'migration starter must exist')
        data = p.read_bytes()
        self.assertTrue(data.startswith(b'& {'))
        data.decode('ascii')
        self.assertFalse(data.startswith(b'\xef\xbb\xbf'))
        self.assertTrue((ROOT / 'scripts/migrate.ps1').read_bytes().startswith(b'\xef\xbb\xbf'))

    @unittest.skipIf(os.name == 'nt', 'site assembly uses Bash')
    def test_assembled_pin_and_checksums(self):
        assembler = ROOT / 'scripts/assemble-migrate-site.sh'
        self.assertTrue(assembler.is_file(), 'site assembler must exist')
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / 'site'
            p = subprocess.run(['/bin/bash', str(assembler), str(out)], capture_output=True)
            self.assertEqual(p.returncode, 0, p.stderr)
            self.assertEqual({f.name for f in out.iterdir()},
                             {'migrate', 'migrate.ps1', 'migrate.sh', 'SHA256SUMS-migrate'})
            pin = hashlib.sha256((out / 'migrate.ps1').read_bytes()).hexdigest()
            starter = (out / 'migrate').read_bytes()
            self.assertIn(pin.encode(), starter)
            self.assertNotIn(b'__WAVE_', starter)
            starter.decode('ascii')
            self.assertTrue(starter.startswith(b'& {'))
            for name in ('migrate.ps1', 'migrate.sh'):
                self.assertEqual((out / name).read_bytes(), (ROOT / 'scripts' / name).read_bytes())
            entries = {}
            for line in (out / 'SHA256SUMS-migrate').read_text().splitlines():
                digest, name = line.split()
                entries[name] = digest
                self.assertEqual(digest, hashlib.sha256((out / name).read_bytes()).hexdigest())
            self.assertEqual(set(entries), {'migrate', 'migrate.ps1', 'migrate.sh'})


if os.name != 'nt' and shutil.which('pwsh') and not os.environ.get('MIGRATE_ENGINE'):
    class PwshMigrationTests(MigrationTests):
        def setUp(self):
            super().setUp()
            self.command = [shutil.which('pwsh'), '-NoProfile', '-File',
                            str(ROOT / 'scripts/migrate.ps1')]
            self.dry = '-DryRun'


if __name__ == '__main__':
    unittest.main()
