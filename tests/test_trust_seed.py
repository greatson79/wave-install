"""좌석 첫 실행 관문 사전 기록(trust seed)·S07 관문 안내 — 임시 HOME 만 쓴다(실 ~/.claude·~/.cys·~/.wave 무접촉)."""
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'lib'))
import trust_seed  # noqa: E402

TRUST_SCREEN = ('Accessing workspace:\n\n /Users/someone\n\n Quick safety check: Is this a project you created or one you trust?\n'
                ' ❯ 1. No, exit\n   2. Yes, I trust this folder\n')
BYPASS_SCREEN = ' WARNING: Claude Code running in Bypass Permissions mode\n ❯ 1. No, exit\n   2. Yes, I accept\n'
ECHO_ONLY_SCREEN = ' Yes, I trust this folder ✔\n\n❯ \n'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


class HelperTests(unittest.TestCase):
    """지인 jarvis-install seed_claude_prefs 규칙(lib/trust_seed.py 머리말) + Wave 고유 remoteControlAtStartup=true."""
    def setUp(self):
        t = tempfile.TemporaryDirectory(prefix='trust-seed-')
        self.addCleanup(t.cleanup)
        self.dir = Path(t.name) / 'cys-claude'
        self.dir.mkdir()
        self.cfg, self.sf = self.dir / '.claude.json', self.dir / 'settings.json'
        self.journal = Path(t.name) / 'wave/trust-seed.tsv'
        self.work = Path(t.name) / 'wave'
        self.home = '/Users/first.last'  # 마침표가 포함된 계정 경로도 하나의 키로 다룬다

    def seed(self):
        return trust_seed.seed(str(self.dir), str(self.journal), str(self.work), self.home)

    def test_fresh_writes_reference_keys_then_rerun_is_noop(self):
        rc, msgs = self.seed()
        self.assertEqual(rc, 0)
        self.assertEqual(json.loads(self.cfg.read_text()), {
            'hasCompletedOnboarding': True, 'fullscreenUpsellSeenCount': 99,
            'projects': {str(self.work): {'hasTrustDialogAccepted': True}, self.home: {'hasTrustDialogAccepted': True}}})
        self.assertEqual(json.loads(self.sf.read_text()), {'remoteControlAtStartup': True, 'skipDangerousModePermissionPrompt': True, 'theme': 'dark', 'autoUpdatesChannel': 'stable'})
        self.assertEqual(self.cfg.stat().st_mode & 0o777, 0o600)
        self.assertEqual(self.journal.read_text(), '%s\t%s\n%s\tremoteControlAtStartup\tabsent\n%s\tskipDangerousModePermissionPrompt\tabsent\n' % (self.cfg, self.home, self.sf, self.sf))
        self.assertFalse((self.dir / '.claude.json.wave-bak').exists())  # 맥 원작에는 백업 사본이 없다
        before = (sha(self.cfg), sha(self.sf), sha(self.journal))
        rc, msgs = self.seed()
        self.assertEqual(rc, 0)
        self.assertIn('홈 폴더 신뢰 설정이 이미 있어 그대로 두었습니다', msgs[0])
        self.assertEqual((sha(self.cfg), sha(self.sf), sha(self.journal)), before)

    def test_missing_profile_dir_is_skipped(self):
        self.dir.rmdir()
        self.assertEqual(self.seed()[0], 0)
        self.assertFalse(self.dir.exists())
        self.assertFalse(self.journal.exists())

    def test_existing_home_false_is_kept_onboarding_overwritten_other_keys_preserved(self):
        original = {'oauthAccount': {'emailAddress': 'x'}, 'numStartups': 9007199254740993, 'hasCompletedOnboarding': False,
                    'fullscreenUpsellSeenCount': 3,
                    'projects': {'/other': {'hasTrustDialogAccepted': False, 'allowedTools': []},
                                 self.home: {'hasTrustDialogAccepted': False, 'history': ['a']}}}
        self.cfg.write_text(json.dumps(original))
        self.cfg.chmod(0o644)
        self.sf.write_text(json.dumps({'theme': 'light', 'remoteControlAtStartup': False}))
        self.assertEqual(self.seed()[0], 0)
        data = json.loads(self.cfg.read_text())
        self.assertIs(data['hasCompletedOnboarding'], True)
        self.assertEqual(data['fullscreenUpsellSeenCount'], 99)
        self.assertEqual(data['projects'][self.home], {'hasTrustDialogAccepted': False, 'history': ['a']})  # 원작: 있으면 그대로(false 도)
        self.assertEqual(data['projects']['/other'], original['projects']['/other'])
        self.assertEqual((data['oauthAccount'], data['numStartups']), (original['oauthAccount'], 9007199254740993))
        self.assertEqual(self.cfg.stat().st_mode & 0o777, 0o644)
        self.assertEqual(json.loads(self.sf.read_text()), {'theme': 'dark', 'remoteControlAtStartup': True, 'skipDangerousModePermissionPrompt': True, 'autoUpdatesChannel': 'stable'})
        self.assertEqual(self.journal.read_text(), '%s\tremoteControlAtStartup\tfalse\n%s\tskipDangerousModePermissionPrompt\tabsent\n' % (self.sf, self.sf))  # 홈 키는 넣지 않았으니 기록 없음
        trust_seed.rollback(str(self.dir), str(self.journal), str(self.work))
        data = json.loads(self.cfg.read_text())
        self.assertNotIn(str(self.work), data['projects'])
        self.assertEqual(data['projects'][self.home], original['projects'][self.home])
        self.assertEqual(json.loads(self.sf.read_text()), {'theme': 'dark', 'remoteControlAtStartup': False, 'autoUpdatesChannel': 'stable'})

    def test_rollback_removes_only_our_true_keys(self):
        self.cfg.write_text(json.dumps({'projects': {self.home: {'allowedTools': ['x']}}}))
        self.seed()
        trust_seed.rollback(str(self.dir), str(self.journal), str(self.work))
        self.assertEqual(json.loads(self.cfg.read_text()), {'hasCompletedOnboarding': True, 'fullscreenUpsellSeenCount': 99,
                                                            'projects': {self.home: {'allowedTools': ['x']}}})
        self.assertEqual(json.loads(self.sf.read_text()), {'theme': 'dark', 'autoUpdatesChannel': 'stable'})
        self.assertFalse(self.journal.exists())

    def test_skip_prompt_prior_value_is_recorded_and_restored(self):
        # 제품 설정 계약: skipDangerousModePermissionPrompt — 키·값 유지 · 바꾸기 전 값을 기록 · rollback 이 되돌림
        for prior, row in ((False, 'false'), ('absent', 'absent')):
            with self.subTest(prior=prior):
                self.journal.unlink(missing_ok=True)
                self.sf.write_text('{}' if prior == 'absent' else json.dumps({'skipDangerousModePermissionPrompt': prior}))
                self.assertEqual(self.seed()[0], 0)
                self.assertIs(json.loads(self.sf.read_text())['skipDangerousModePermissionPrompt'], True)
                self.assertIn('%s\tskipDangerousModePermissionPrompt\t%s\n' % (self.sf, row), self.journal.read_text())
                trust_seed.rollback(str(self.dir), str(self.journal), str(self.work))
                back = json.loads(self.sf.read_text())
                if prior == 'absent':
                    self.assertNotIn('skipDangerousModePermissionPrompt', back)
                else:
                    self.assertIs(back['skipDangerousModePermissionPrompt'], False)

    def test_skip_prompt_already_true_is_not_recorded_nor_removed(self):
        self.sf.write_text(json.dumps({'skipDangerousModePermissionPrompt': True}))
        self.seed()
        self.assertNotIn('skipDangerousModePermissionPrompt', self.journal.read_text())
        trust_seed.rollback(str(self.dir), str(self.journal), str(self.work))
        self.assertIs(json.loads(self.sf.read_text())['skipDangerousModePermissionPrompt'], True)

    def test_rollback_leaves_values_changed_after_the_seed(self):
        self.seed()
        data = json.loads(self.cfg.read_text())
        data['projects'][self.home]['hasTrustDialogAccepted'] = False  # 그 뒤 사람이 바꿨다
        self.cfg.write_text(json.dumps(data))
        self.sf.write_text(json.dumps({'remoteControlAtStartup': False}))
        trust_seed.rollback(str(self.dir), str(self.journal), str(self.work))
        self.assertEqual(json.loads(self.cfg.read_text())['projects'], {self.home: {'hasTrustDialogAccepted': False}})
        self.assertEqual(json.loads(self.sf.read_text()), {'remoteControlAtStartup': False})

    def test_journal_failure_adds_no_home_key_and_returns_3(self):
        self.journal.parent.mkdir(parents=True)
        self.journal.mkdir()  # 기록 파일 자리에 폴더 — 덧붙이기 실패
        rc, msgs = self.seed()
        self.assertEqual(rc, 3)
        data = json.loads(self.cfg.read_text())
        self.assertNotIn(self.home, data['projects'])
        self.assertIs(data['hasCompletedOnboarding'], True)
        self.assertFalse(self.sf.exists())

    def test_unknown_shape_is_refused_without_writing(self):
        self.cfg.write_text('{"projects": []}')
        self.assertEqual(trust_seed.main(['seed', str(self.dir), str(self.journal), str(self.work), self.home]), 1)
        self.assertEqual(self.cfg.read_text(), '{"projects": []}')
        self.assertFalse(self.journal.exists())


class MacBootstrapTests(unittest.TestCase):
    def setUp(self):
        t = tempfile.TemporaryDirectory(prefix='trust-seed-mac-')
        self.addCleanup(t.cleanup)
        self.home = Path(t.name)
        self.wave = self.home / '.wave'
        (self.wave / 'bin').mkdir(parents=True)
        (self.wave / 'fleet').mkdir()
        (self.home / '.cys/claude').mkdir(parents=True)
        # 사용자 개인 설정(가짜) — 설치 전후 바이트가 같아야 한다.
        (self.home / '.claude').mkdir()
        (self.home / '.claude.json').write_text('{"projects": {}}')
        (self.home / '.claude/settings.json').write_text('{"theme": "light"}')
        self.fakebin = self.home / 'fakebin'
        self.fakebin.mkdir()
        self.calls = self.home / 'calls.log'
        cys = self.wave / 'bin/cys'
        cys.write_text('#!/bin/sh\necho "cys $*" >> "$CALLS"\ncase "$1" in\nread-screen) cat "$SCREEN";;\nesac\n')
        cys.chmod(0o755)
        source = (ROOT / 'bootstrap.sh').read_text()
        self.lib = self.home / 'functions.sh'
        self.lib.write_text(source.rsplit('\nmain "$@"\n', 1)[0] + '\nSCRIPT_DIR="$ROOT_DIR"\n')
        self.env = {k: v for k, v in os.environ.items() if k not in ('CYS_ACCOUNT_DIR', 'CLAUDE_CONFIG_DIR')}
        self.env.update(HOME=str(self.home), WAVE_HOME=str(self.wave), CALLS=str(self.calls), ROOT_DIR=str(ROOT),
                        PATH=str(self.fakebin) + ':' + os.environ['PATH'], SCREEN=str(self.home / 'screen.txt'))

    def bash(self, script, **env):
        return subprocess.run(['bash', '-c', 'source "$1"; ' + script, 'ts', str(self.lib)], env=dict(self.env, **env),
                              text=True, capture_output=True, timeout=60, stdin=subprocess.DEVNULL)

    def personal(self):
        return sha(self.home / '.claude.json'), sha(self.home / '.claude/settings.json')

    def test_seed_writes_wave_profile_only_and_reruns_idempotent(self):
        before = self.personal()
        r = self.bash('seed_claude_trust && seed_claude_trust; echo RC=$?')
        self.assertIn('RC=0', r.stdout, r.stderr)
        self.assertIn('첫 실행 질문(테마·폴더 신뢰·큰 화면 권유)을 미리 넘겨 두었습니다.', r.stderr)
        self.assertIn('홈 폴더 신뢰 설정이 이미 있어 그대로 두었습니다', r.stderr)
        data = json.loads((self.home / '.cys/claude/.claude.json').read_text())
        self.assertIs(data['hasCompletedOnboarding'], True)
        self.assertEqual(data['fullscreenUpsellSeenCount'], 99)
        self.assertIs(data['projects'][str(self.home)]['hasTrustDialogAccepted'], True)
        self.assertIs(data['projects'][str(self.wave)]['hasTrustDialogAccepted'], True)
        self.assertEqual(sorted(data['projects']), sorted([str(self.home), str(self.wave)]))  # 원작처럼 실경로 칸은 따로 만들지 않는다
        self.assertIs(json.loads((self.home / '.cys/claude/settings.json').read_text())['remoteControlAtStartup'], True)
        self.assertEqual(self.personal(), before)
        self.assertTrue((self.wave / 'trust-seed.tsv').is_file())
        self.assertNotIn('claude', self.calls.read_text() if self.calls.exists() else '')  # 로그인 확인 호출 없음(원작과 같다)

    def test_cys_account_dir_is_honoured(self):
        acct = self.home / 'acct'
        acct.mkdir()
        self.bash('seed_claude_trust', CYS_ACCOUNT_DIR=str(acct))
        self.assertTrue((acct / '.claude.json').is_file())
        self.assertTrue((acct / 'settings.json').is_file())
        self.assertFalse((self.home / '.cys/claude/.claude.json').exists())

    def test_journal_failure_stops_step_with_j_perm_01(self):
        (self.wave / 'trust-seed.tsv').mkdir()
        r = self.bash('if seed_claude_trust; then echo RC=0; else echo RC=1; fi')
        self.assertIn('RC=1', r.stdout)
        self.assertIn('J-PERM-01', r.stderr)

    def gate(self, screen):
        (self.home / 'screen.txt').write_text(screen)
        (self.wave / 'fleet/status.json').write_text(json.dumps({'surfaces': [
            {'surface_ref': 'surface:5', 'role': 'master', 'exited': False},
            {'surface_ref': 'surface:7', 'role': 'cso', 'exited': False}]}))
        return self.bash('notice_first_run_gate; notice_first_run_gate; echo RC=$?')

    def test_gate_screen_prints_notice_once_and_sends_no_keys(self):
        for screen in (TRUST_SCREEN, BYPASS_SCREEN):
            with self.subTest(screen=screen[:30]):
                self.calls.unlink(missing_ok=True)
                r = self.gate(screen)
                self.assertIn('RC=0', r.stdout)
                self.assertEqual(r.stderr.count("Wave 창에서 'Yes, I trust this folder'(또는 해당 동의)를 골라 주세요"), 1)
                calls = self.calls.read_text()
                self.assertNotIn('send', calls)
                self.assertIn('cys read-screen --surface surface:5', calls)

    def test_confirm_echo_alone_is_not_a_gate(self):
        r = self.gate(ECHO_ONLY_SCREEN)
        self.assertNotIn('골라 주세요', r.stderr)

    def test_s07_waits_on_gate_with_notice_until_human_picks(self):
        # 관문 화면 고정본에서 S07 대기 루프가 실패로 끝나지 않고 안내 후 계속 돈다(cso 가 살아날 때 통과).
        (self.home / '.cys/.gui-onboarded').write_text('0.0.0\n')
        (self.home / 'screen.txt').write_text(TRUST_SCREEN)
        fleet = self.home / 'fleet.json'
        recording=json.loads((ROOT/'tests/fixtures/real_cys/rc5_three_status.json').read_text())['response']
        rows=[]
        for role,ref in [('master','surface:5'),('cso','surface:7'),('worker','surface:8')]:
            row=dict(next(r for r in recording['surfaces'] if r['role']==role),surface_ref=ref,created_at=9999999999)
            rows.append(row)
        fleet.write_text(json.dumps({'surfaces':rows[:2]}))
        full = self.home / 'full.json'
        full.write_text(json.dumps({'surfaces':rows}))
        (self.fakebin / 'open').write_text('#!/bin/sh\nexit 0\n')
        (self.fakebin / 'open').chmod(0o755)
        cys = self.wave / 'bin/cys'
        # 첫 status = 좌석 없음 → launch-agent · 네 번째 status 부터 worker 가 살아난다(사람이 창에서 골랐다).
        cys.write_text('#!/bin/sh\necho "cys $*" >> "$CALLS"\ncase "$1" in\n'
                       'read-screen) cat "$SCREEN";;\n'
                       'status) n=$(grep -c "cys status" "$CALLS"); if [ "$n" -le 1 ]; then echo \'{"surfaces": []}\'; '
                       'elif [ "$n" -ge 4 ]; then cat "$FULL"; else cat "$FLEET"; fi;;\n'
                       'launch-agent) touch "$HOME/.cys/.master-bootstrapped"; echo surface:5;;\nesac\n')
        (self.home / '.cys/.master-bootstrapped').write_text(json.dumps({'surface_ref': 'surface:5', 'orchestra_check': 'exit 0'}))
        r = self.bash('step_s07; echo "RC=$?"', FLEET=str(fleet), FULL=str(full))
        self.assertIn('RC=0', r.stdout, r.stderr)
        self.assertEqual(r.stderr.count('골라 주세요'), 1)
        self.assertNotIn('cys send-key', self.calls.read_text())


class WindowsFixtureTests(unittest.TestCase):
    def test_windows_seed_rollback_and_gate_notice(self):
        pwsh = os.environ.get('PWSH') or shutil.which('pwsh')
        if not pwsh:
            self.skipTest('PWSH required')
        with tempfile.TemporaryDirectory(prefix='trust-seed-win-') as home:
            env = {k: v for k, v in os.environ.items() if k not in ('CYS_ACCOUNT_DIR', 'CLAUDE_CONFIG_DIR')}
            r = subprocess.run([pwsh, '-NoProfile', '-File', str(ROOT / 'tests/windows_trust_seed_fixture.ps1')], cwd=ROOT,
                               env=dict(env, TS_FIXTURE_HOME=home, TS_TRUST=TRUST_SCREEN, TS_ECHO=ECHO_ONLY_SCREEN),
                               text=True, capture_output=True, timeout=60)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            for needle in ('PASS fresh', 'PASS rerun', 'PASS preserve', 'PASS rollback', 'PASS skip', 'PASS journal', 'PASS gate notice'):
                self.assertIn(needle, r.stdout)
            self.assertEqual(r.stderr, '')


if __name__ == '__main__':
    unittest.main()
