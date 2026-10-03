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
    def setUp(self):
        t = tempfile.TemporaryDirectory(prefix='trust-seed-')
        self.addCleanup(t.cleanup)
        self.dir = Path(t.name) / 'cys-claude'
        self.cfg = self.dir / '.claude.json'
        self.journal = Path(t.name) / 'wave/trust-seed.json'
        self.home = '/Users/first.last'  # 마침표 든 홈(맥 미니 실기와 같은 꼴)도 한 열쇠로 다룬다

    def seed(self, auth='verified'):
        return trust_seed.seed(str(self.dir), str(self.journal), auth, [self.home])

    def test_fresh_creates_keys_then_rerun_is_noop_then_rollback_removes_file(self):
        self.assertEqual(self.seed(), 'changed 2')
        data = json.loads(self.cfg.read_text())
        self.assertEqual(data, {'hasCompletedOnboarding': True, 'projects': {self.home: {'hasTrustDialogAccepted': True}}})
        self.assertEqual(self.cfg.stat().st_mode & 0o777, 0o600)
        before, jbefore = sha(self.cfg), sha(self.journal)
        self.assertEqual(self.seed(), 'unchanged')
        self.assertEqual((sha(self.cfg), sha(self.journal)), (before, jbefore))
        self.assertEqual(trust_seed.rollback(str(self.journal)), 'rolled back 2')
        self.assertFalse(self.cfg.exists())
        self.assertFalse(self.journal.exists())

    def test_existing_keys_are_preserved_false_is_raised_and_rollback_restores_prior(self):
        self.dir.mkdir(parents=True)
        original = {'oauthAccount': {'emailAddress': 'x'}, 'numStartups': 9007199254740993, 'hasCompletedOnboarding': False,
                    'projects': {'/other': {'hasTrustDialogAccepted': False, 'allowedTools': []},
                                 self.home: {'hasTrustDialogAccepted': False, 'history': ['a']}}}
        self.cfg.write_text(json.dumps(original))
        self.cfg.chmod(0o644)
        self.assertEqual(self.seed(), 'changed 2')
        data = json.loads(self.cfg.read_text())
        self.assertIs(data['hasCompletedOnboarding'], True)
        self.assertEqual(data['projects'][self.home], {'hasTrustDialogAccepted': True, 'history': ['a']})
        self.assertEqual(data['projects']['/other'], original['projects']['/other'])
        self.assertEqual((data['oauthAccount'], data['numStartups']), (original['oauthAccount'], 9007199254740993))
        self.assertEqual(self.cfg.stat().st_mode & 0o777, 0o644)
        self.assertEqual(json.loads((self.dir / '.claude.json.wave-bak').read_text()), original)
        priors = [c['prior'] for c in json.loads(self.journal.read_text())['changes']]
        self.assertEqual(priors, [False, False])
        trust_seed.rollback(str(self.journal))
        self.assertEqual(json.loads(self.cfg.read_text()), original)

    def test_rollback_leaves_values_changed_after_the_seed(self):
        self.dir.mkdir(parents=True)
        self.cfg.write_text(json.dumps({'projects': {}}))
        self.seed()
        data = json.loads(self.cfg.read_text())
        data['projects'][self.home]['hasTrustDialogAccepted'] = False  # 그 뒤 사람이 바꿨다
        data['projects']['/new'] = {'hasTrustDialogAccepted': True}
        self.cfg.write_text(json.dumps(data))
        trust_seed.rollback(str(self.journal))
        self.assertEqual(json.loads(self.cfg.read_text()),
                         {'projects': {self.home: {'hasTrustDialogAccepted': False}, '/new': {'hasTrustDialogAccepted': True}}})

    def test_unproven_login_writes_trust_only(self):
        self.assertEqual(self.seed('unproven'), 'changed 1')
        self.assertNotIn('hasCompletedOnboarding', json.loads(self.cfg.read_text()))

    def test_unknown_shape_is_refused_without_writing(self):
        self.dir.mkdir(parents=True)
        self.cfg.write_text('{"projects": []}')
        self.assertEqual(trust_seed.main(['seed', str(self.dir), str(self.journal), 'verified', self.home]), 1)
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
        # 사용자 개인 설정(가짜) — 설치 전후 바이트가 같아야 한다.
        (self.home / '.claude').mkdir()
        (self.home / '.claude.json').write_text('{"projects": {}}')
        (self.home / '.claude/settings.json').write_text('{"theme": "light"}')
        self.fakebin = self.home / 'fakebin'
        self.fakebin.mkdir()
        self.calls = self.home / 'calls.log'
        claude = self.fakebin / 'claude'
        claude.write_text('#!/bin/sh\necho "claude $* CFG=$CLAUDE_CONFIG_DIR" >> "$CALLS"\nexit "${AUTH_RC:-0}"\n')
        claude.chmod(0o755)
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
        r = self.bash('seed_claude_trust; seed_claude_trust')
        self.assertEqual(r.returncode, 0, r.stderr)
        real = os.path.realpath(self.home)  # 임시 폴더가 /var → /private/var 처럼 바로가기면 실경로도 함께 신뢰한다
        self.assertIn('폴더 신뢰 사전 기록: changed %d' % (2 + (real != str(self.home))), r.stderr)
        self.assertIn('폴더 신뢰 사전 기록: unchanged', r.stderr)
        data = json.loads((self.home / '.cys/claude/.claude.json').read_text())
        self.assertIs(data['hasCompletedOnboarding'], True)
        self.assertIs(data['projects'][str(self.home)]['hasTrustDialogAccepted'], True)
        self.assertIs(data['projects'][real]['hasTrustDialogAccepted'], True)
        self.assertEqual(self.personal(), before)
        self.assertIn('CFG=%s/.cys/claude' % self.home, self.calls.read_text())  # 로그인 확인도 좌석 설정 폴더로
        self.assertTrue((self.wave / 'trust-seed.json').is_file())

    def test_unproven_login_does_not_write_onboarding(self):
        r = self.bash('seed_claude_trust', AUTH_RC='1')
        self.assertIn('로그인 unproven', r.stderr)
        data = json.loads((self.home / '.cys/claude/.claude.json').read_text())
        self.assertNotIn('hasCompletedOnboarding', data)
        self.assertIs(data['projects'][str(self.home)]['hasTrustDialogAccepted'], True)

    def test_cys_account_dir_is_honoured(self):
        acct = self.home / 'acct'
        self.bash('seed_claude_trust', CYS_ACCOUNT_DIR=str(acct))
        self.assertTrue((acct / '.claude.json').is_file())
        self.assertFalse((self.home / '.cys/claude/.claude.json').exists())

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
        (self.home / '.cys').mkdir()
        (self.home / '.cys/.gui-onboarded').write_text('0.0.0\n')
        (self.home / 'screen.txt').write_text(TRUST_SCREEN)
        fleet = self.home / 'fleet.json'
        master = {'surface_ref': 'surface:5', 'role': 'master', 'exited': False, 'agent_alive': True, 'created_at': 9999999999}
        fleet.write_text(json.dumps({'surfaces': [master, {'surface_ref': 'surface:7', 'role': 'cso', 'exited': False, 'agent_alive': True,
                                                           'created_at': 9999999999}]}))
        full = self.home / 'full.json'
        full.write_text(json.dumps({'surfaces': [master, {'surface_ref': 'surface:7', 'role': 'cso', 'exited': False, 'agent_alive': True, 'created_at': 9999999999},
                                                 {'surface_ref': 'surface:8', 'role': 'worker-1', 'exited': False, 'agent_alive': True, 'created_at': 9999999999}]}))
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
    def test_windows_seed_rollback_auth_and_gate_notice(self):
        pwsh = os.environ.get('PWSH') or shutil.which('pwsh')
        if not pwsh:
            self.skipTest('PWSH required')
        with tempfile.TemporaryDirectory(prefix='trust-seed-win-') as home:
            env = {k: v for k, v in os.environ.items() if k not in ('CYS_ACCOUNT_DIR', 'CLAUDE_CONFIG_DIR')}
            r = subprocess.run([pwsh, '-NoProfile', '-File', str(ROOT / 'tests/windows_trust_seed_fixture.ps1')], cwd=ROOT,
                               env=dict(env, TS_FIXTURE_HOME=home, TS_TRUST=TRUST_SCREEN, TS_ECHO=ECHO_ONLY_SCREEN),
                               text=True, capture_output=True, timeout=60)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            for needle in ('PASS fresh', 'PASS preserve', 'PASS rerun', 'PASS rollback', 'PASS unproven', 'PASS gate notice'):
                self.assertIn(needle, r.stdout)
            self.assertEqual(r.stderr, '')


class NoticeTextTests(unittest.TestCase):
    def test_notice_is_shared_and_shown_by_both_os(self):
        text = (ROOT / 'lib/trust-notice.txt').read_text(encoding='utf-8')
        self.assertIn('설치기가 Wave 전용 Claude 설정에 작업 폴더 신뢰를 미리 기록합니다', text)
        self.assertIn('홈 폴더', text)
        self.assertIn('lib/trust-notice.txt', (ROOT / 'bootstrap.sh').read_text())
        self.assertIn("'trust-notice.txt'", (ROOT / 'bootstrap.ps1').read_text(encoding='utf-8-sig'))


if __name__ == '__main__':
    unittest.main()
