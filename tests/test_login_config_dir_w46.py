import json
import unittest
from test_one_line import ROOT, Sandbox


FAKE_CLAUDE = r'''
[ "$1" = auth ] || exit 2
printf '%s|%s\n' "$2" "${CLAUDE_CONFIG_DIR:-unset}" >> "$FAKE/auth-calls"
case "$2" in
  status) [ -f "$CLAUDE_CONFIG_DIR/loggedin" ] ;;
  login) [ "$FAKE_LOGIN_OK" = 1 ] && touch "$CLAUDE_CONFIG_DIR/loggedin"; exit 0 ;;
esac
'''


class LoginConfigDir(unittest.TestCase):
    def setUp(self):
        self.sb = Sandbox(self)
        self.sb.stub('claude', FAKE_CLAUDE)
        self.seat = self.sb.home / '.cys' / 'claude'

    def calls(self):
        return (self.sb.fake / 'auth-calls').read_text().splitlines()

    def test_resume_rechecks_login_when_saved_state_says_passed(self):
        self.sb.stub('claude', FAKE_CLAUDE)
        state = json.loads((ROOT / 'install-state.json').read_text())
        state['status'] = 'running'
        for step in state['steps'].values():
            step.update(status='passed', exit_code=0, error_id=None, observed={})
        wave = self.sb.home / '.wave'
        wave.mkdir()
        (wave / 'install-state.json').write_text(json.dumps(state))

        script = '''
        ensure_pack(){ :; }; load_config(){ :; }; show_help_notice(){ :; }
        show_permission_notice(){ :; }; attempt_start(){ :; }
        wave_visible_app(){ printf '%s\\n' "$HOME/Applications/Wave Terminal.app"; }
        wave_migrate_app(){ return 0; }; wave_show_app(){ return 0; }
        step_s00(){ :; }; step_s01(){ :; }; step_s03(){ :; }; step_s04(){ :; }
        step_s05(){ :; }; step_s06(){ :; }; step_s07(){ :; }; step_s08(){ :; }
        set +e; main --resume; printf 'MAIN_RC=%s\\n' "$?"
        '''
        r = self.sb.call(script, FAKE_LOGIN_OK='1')
        self.assertIn('MAIN_RC=0', r.stdout + r.stderr)
        self.assertEqual(self.calls(), [f'status|{self.seat}', f'login|{self.seat}', f'status|{self.seat}'])
        saved = json.loads((wave / 'install-state.json').read_text())
        self.assertEqual(saved['steps']['S02_CLAUDE_LOGIN']['status'], 'passed')

    def test_default_only_logged_in_still_logs_in_seat(self):
        (self.sb.home / '.claude').mkdir()
        (self.sb.home / '.claude' / 'loggedin').touch()
        r = self.sb.call('step_s02', FAKE_LOGIN_OK='1')
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.calls(), [f'status|{self.seat}', f'login|{self.seat}', f'status|{self.seat}'])

    def test_seat_only_logged_in_skips_login(self):
        self.seat.mkdir(parents=True)
        (self.seat / 'loggedin').touch()
        r = self.sb.call('step_s02')
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.calls(), [f'status|{self.seat}'])

    def test_neither_logged_in_fails(self):
        r = self.sb.call('step_s02', FAKE_LOGIN_OK='0')
        self.assertNotEqual(r.returncode, 0)
        self.assertEqual(self.calls(), [f'status|{self.seat}', f'login|{self.seat}', f'status|{self.seat}'])

    def test_custom_account_dir(self):
        custom = self.sb.home / 'custom'
        r = self.sb.call('step_s02', CYS_ACCOUNT_DIR=str(custom), FAKE_LOGIN_OK='1')
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue((custom / 'loggedin').exists())
        self.assertEqual(self.calls(), [f'status|{custom}', f'login|{custom}', f'status|{custom}'])

    def test_s07_rechecks_after_s02_passed(self):
        r = self.sb.call('step_s02; awakening_command(){ return 9; }; step_s07', FAKE_LOGIN_OK='1')
        self.assertNotEqual(r.returncode, 0)
        self.assertEqual(self.calls(), [f'status|{self.seat}', f'login|{self.seat}', f'status|{self.seat}', f'status|{self.seat}'])

    def test_s07_login_loss_stops_before_timeout(self):
        script = '''
        step_s02
        awakening_command(){ if [[ "$*" == *"status --json"* ]]; then echo '{"surfaces":[]}'; fi; }
        wait_gui_onboarded(){ return 0; }
        seed_claude_trust(){ return 0; }
        send_master_declaration(){ return 0; }
        bounded_cys(){
          if [[ "$*" == *"status --json"* ]]; then echo '{"surfaces":[]}';
          elif [[ "$*" == *"launch-agent"* ]]; then rm "$HOME/.cys/claude/loggedin"; echo surface:1;
          fi
        }
        RUN_STARTED=$(date +%s)
        set +e
        step_s07; printf 'RC=%s OBS=%s\\n' "$?" "$STEP_OBSERVED"
        '''
        r = self.sb.call(script, FAKE_LOGIN_OK='1')
        self.assertIn('RC=3', r.stdout, r.stderr)
        self.assertIn('J-LOGIN-03', r.stdout + r.stderr)
