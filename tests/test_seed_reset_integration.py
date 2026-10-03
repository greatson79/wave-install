"""Seed settings and actual reset entry points; every write stays in a temporary HOME."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import tempfile
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'lib'))
import trust_seed


class SeedResetTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(prefix='wave-reset-')
        self.addCleanup(tmp.cleanup)
        self.home = Path(tmp.name)
        self.wave = self.home / '.wave'
        self.profile = self.home / '.cys/claude'
        self.profile.mkdir(parents=True)
        self.pack = self.home / '.cys/pack'
        self.pack.mkdir()
        self.cfg = self.profile / '.claude.json'
        self.settings = self.profile / 'settings.json'
        self.journal = self.wave / 'trust-seed.tsv'
        self.personal = self.home / '.claude/settings.json'
        self.personal.parent.mkdir()
        self.personal.write_text('{"theme":"light","personal":true}')
        self.env = {k: v for k, v in os.environ.items() if not k.startswith(('CYS_', 'AITERM_', 'CLAUDE_', 'WAVE_'))}
        self.env.update(HOME=str(self.home), USERPROFILE=str(self.home), CYS_ACCOUNT_DIR=str(self.profile),
                        XDG_CONFIG_HOME=str(self.home / 'xdg'), WAVE_NO_PROGRESS='1')

    def seed(self):
        return trust_seed.seed(str(self.profile), str(self.journal), str(self.wave), str(self.home))

    def run_reset(self, windows, *args, env=None):
        if windows:
            pwsh = os.environ.get('PWSH') or shutil.which('pwsh')
            if not pwsh:
                self.skipTest('PWSH required')
            cmd = [pwsh, '-NoProfile', '-File', str(ROOT / 'reset.ps1'), *args]
        else:
            cmd = ['bash', str(ROOT / 'reset.sh'), *args]
        return subprocess.run(cmd, env=env or self.env, cwd=self.home, text=True, capture_output=True, timeout=30)

    def test_mac_settings_match_reference_and_keep_other_keys(self):
        self.settings.write_text('{"theme":"light","autoUpdatesChannel":"latest","other":42}')
        self.seed()
        data = json.loads(self.settings.read_text())
        self.assertEqual(data, dict(theme='dark', autoUpdatesChannel='stable', other=42, remoteControlAtStartup=True))
        self.assertNotIn('skipDangerousModePermissionPrompt', data)
        self.assertEqual(self.personal.read_text(), '{"theme":"light","personal":true}')

    def test_reset_wave_and_all_restore_before_deleting_journal(self):
        for windows in (False, True):
            for target in ('wave', 'all'):
                with self.subTest(windows=windows, target=target):
                    self.pack.mkdir(exist_ok=True)
                    self.seed()
                    args = ('-Apply', '-Target', target) if windows else ('--apply', '--target', target)
                    r = self.run_reset(windows, *args)
                    self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
                    self.assertFalse(self.wave.exists())
                    self.assertNotIn(str(self.home), json.loads(self.cfg.read_text())['projects'])
                    self.assertNotIn(str(self.wave), json.loads(self.cfg.read_text())['projects'])
                    self.assertNotIn('remoteControlAtStartup', json.loads(self.settings.read_text()))
                    self.assertEqual(self.pack.exists(), target == 'wave')
                    self.assertEqual(self.personal.read_text(), '{"theme":"light","personal":true}')

    def test_list_and_pack_leave_seed_unchanged(self):
        self.seed()
        before = [f.read_bytes() for f in (self.cfg, self.settings, self.journal)]
        for windows in (False, True):
            for args in (('-List',), ('-Apply', '-Target', 'pack')) if windows else (('--list',), ('--apply', '--target', 'pack')):
                self.pack.mkdir(exist_ok=True)
                r = self.run_reset(windows, *args)
                self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
                self.assertEqual([f.read_bytes() for f in (self.cfg, self.settings, self.journal)], before)

    def test_rollback_failure_keeps_wave_and_journal(self):
        self.seed()
        self.cfg.write_text('{broken json')
        for windows in (False, True):
            r = self.run_reset(windows, *(['-Apply'] if windows else ['--apply']))
            self.assertNotEqual(r.returncode, 0, r.stdout + r.stderr)
            self.assertTrue(self.journal.exists())

    def test_windows_reset_ignores_unrelated_wave_home(self):
        self.seed()
        elsewhere = self.home / 'other-wave'
        elsewhere.mkdir()
        marker = elsewhere / 'trust-seed.tsv'
        marker.write_text('must not read or delete\n')
        r = self.run_reset(True, '-Apply', env=dict(self.env, WAVE_HOME=str(elsewhere)))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertNotIn(str(self.home), json.loads(self.cfg.read_text())['projects'])
        self.assertEqual(marker.read_text(), 'must not read or delete\n')

    def test_foreign_journal_path_fails_without_touching_personal_settings(self):
        self.seed()
        with self.journal.open('a') as f:
            f.write(str(self.personal) + '\tremoteControlAtStartup\tabsent\n')
        for windows in (False, True):
            r = self.run_reset(windows, *(['-Apply'] if windows else ['--apply']))
            self.assertNotEqual(r.returncode, 0, r.stdout + r.stderr)
            self.assertTrue(self.journal.exists())
            self.assertEqual(self.personal.read_text(), '{"theme":"light","personal":true}')

    def test_reset_rejects_linked_settings_directory_before_any_write(self):
        self.seed()
        linked = self.home / 'linked-profile'
        linked.symlink_to(self.profile, target_is_directory=True)
        self.journal.write_text(self.journal.read_text().replace(str(self.profile), str(linked)))
        before = (self.cfg.read_bytes(), self.settings.read_bytes())
        for windows in (False, True):
            env = dict(self.env, CYS_ACCOUNT_DIR=str(linked))
            r = self.run_reset(windows, *(['-Apply'] if windows else ['--apply']), env=env)
            self.assertNotEqual(r.returncode, 0, r.stdout + r.stderr)
            self.assertEqual((self.cfg.read_bytes(), self.settings.read_bytes()), before)
            self.assertTrue(self.journal.exists())

    def test_reset_rejects_linked_settings_file_before_any_write(self):
        self.seed()
        self.settings.unlink()
        self.settings.symlink_to(self.personal)
        before = self.cfg.read_bytes()
        for windows in (False, True):
            r = self.run_reset(windows, *(['-Apply'] if windows else ['--apply']))
            self.assertNotEqual(r.returncode, 0, r.stdout + r.stderr)
            self.assertEqual(self.cfg.read_bytes(), before)
            self.assertEqual(self.personal.read_text(), '{"theme":"light","personal":true}')
            self.assertTrue(self.journal.exists())

    def test_reset_rejects_unknown_settings_key(self):
        self.seed()
        with self.journal.open('a') as f:
            f.write(str(self.settings) + '\ttheme\tabsent\n')
        before = self.cfg.read_bytes()
        for windows in (False, True):
            r = self.run_reset(windows, *(['-Apply'] if windows else ['--apply']))
            self.assertNotEqual(r.returncode, 0, r.stdout + r.stderr)
            self.assertEqual(self.cfg.read_bytes(), before)
            self.assertTrue(self.journal.exists())

    def test_journal_dotdot_link_cannot_redirect_settings_write(self):
        child = self.personal.parent / 'child'
        child.mkdir()
        (self.profile / 'jump').symlink_to(child, target_is_directory=True)
        for windows in (False, True):
            with self.subTest(windows=windows):
                self.settings.write_text('{}')
                self.seed()
                self.personal.write_text('{"remoteControlAtStartup":true,"personal":true}')
                before = self.personal.read_bytes()
                raw = str(self.profile) + '/jump/../settings.json'
                self.journal.write_text(self.journal.read_text().replace(str(self.settings), raw))
                r = self.run_reset(windows, *(['-Apply'] if windows else ['--apply']))
                self.assertEqual(self.personal.read_bytes(), before, r.stdout + r.stderr)
                self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
                self.assertNotIn('remoteControlAtStartup', json.loads(self.settings.read_text()))

    def test_packaging_includes_reset_and_rollback_dependencies(self):
        out = self.home / 'release'
        r = subprocess.run(['bash', str(ROOT / 'scripts/make-release.sh'), '0.3.0', 'https://example.invalid/v0.3.0', str(out)],
                           env=self.env, cwd=self.home, capture_output=True, text=True, timeout=30)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        required = {'wave-install-0.3.0/' + n for n in ('reset.sh', 'reset.ps1', 'bootstrap.ps1', 'lib/trust_seed.py')}
        with tarfile.open(out / 'wave-install-0.3.0.tar.gz') as archive:
            self.assertTrue(required.issubset(archive.getnames()))
        with zipfile.ZipFile(out / 'wave-install-0.3.0.zip') as archive:
            self.assertTrue(required.issubset(archive.namelist()))


if __name__ == '__main__':
    unittest.main()
