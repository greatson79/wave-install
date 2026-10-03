"""G8 R1 installer regressions (Noah/Zen r1 verdicts).

No real server is contacted: the Python client uses injected transports, bash uses a fake client, and the
only sockets are loopback listeners owned (and closed) by the test itself.
"""
import hashlib
import importlib
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'lib'))
PWSH = os.environ.get('PWSH') or shutil.which('pwsh')
USER = 'alicesmith'
USER_FRAGMENTS = ('cesmith', 'esmith', 'smith', 'alices')
TOKEN = 'sk-SECRETTOKENVALUE1234567890'
FAKE_CLIENT = '''import json, os, sys, time
with open(os.environ["FAKE_HELP_LOG"], "a") as h:
    h.write(json.dumps(sys.argv[1:]) + "\\n")
time.sleep(float(os.environ.get("FAKE_HELP_SLEEP", "0")))
sys.exit(int(os.environ.get("FAKE_HELP_RC", "0")))
'''


def functions_sh(directory):
    source = (ROOT / 'bootstrap.sh').read_text()
    marker = '\nmain "$@"\n'
    assert source.count(marker) == 1
    lib = Path(directory) / 'functions.sh'
    lib.write_text(source.rsplit(marker, 1)[0] + '\n')
    return lib


def split_file(path, window, prefix, secret, cut, filler_unit):
    """Write prefix+secret+filler so that a reader keeping the last `window` bytes starts `cut` chars into secret."""
    after = secret[cut:]
    need = window - len(after.encode())
    filler = filler_unit * ((need - 1) // len(filler_unit))
    filler += ' ' * (need - len(filler) - 1) + '\n'
    data = prefix + secret + filler
    Path(path).write_text(data)
    assert len(data.encode()) - window == len((prefix + secret[:cut]).encode())


class RedactBeforeTruncateTests(unittest.TestCase):
    def setUp(self):
        import install_help_client
        self.m = importlib.reload(install_help_client)
        self.addCleanup(importlib.reload, install_help_client)

    def client(self, transport=None):
        return self.m.HelpClient('https://example.test', 'a' * 32, '9.9.9', notice=True, username=USER,
                                 transport=transport or (lambda *a: (500, {})), sleep=lambda s: None,
                                 clock=lambda: 0, emit=lambda line: None)

    def assert_no_fragment(self, text):
        for fragment in USER_FRAGMENTS + ('TOKENVALUE', 'RETTOKEN'):
            self.assertNotIn(fragment, text)

    def test_env_report_state_cut_inside_home_path_or_token_never_leaks(self):
        for secret, cut in (('/Users/' + USER, len('/Users/ali')), (TOKEN, len('sk-SEC'))):
            with self.subTest(secret=secret), tempfile.TemporaryDirectory() as td:
                prefix = '0' * 150000 + '\n  "log": "'
                split_file(Path(td) / 'install-state.json', 96 * 1024, prefix, secret, cut, '1')
                env = self.m._env_report(td, '9.9.9', '1/10')
                payload = self.client().build_help_payload('1/10', 'J-UNK-00', env, '')
                self.assertIn('install-state.json:', payload['env_report'])
                self.assertLessEqual(len(payload['env_report'].encode()), 96 * 1024)
                self.assert_no_fragment(payload['env_report'])

    def test_log_tail_cut_inside_home_path_or_token_never_leaks(self):
        # Long tokens on the same line shrink to <TOKEN> after redaction, so a fragment at the old 2x read
        # window would have landed inside the final 128KB tail.
        for secret, cut in (('/Users/' + USER + '/x', len('/Users/ali')), (TOKEN + ' ', len('sk-SEC'))):
            with self.subTest(secret=secret), tempfile.TemporaryDirectory() as td:
                log = Path(td) / 'install.log'
                split_file(log, 256 * 1024, 'start\n' + 'P' * 1000 + ' ', secret, cut, ' sk-' + 'B' * 996)
                payload = self.client().build_help_payload('1/10', 'J-UNK-00', '', self.m._read_tail(log))
                self.assertIn('<TOKEN>', payload['log_tail'])
                self.assert_no_fragment(payload['log_tail'])

    def test_oversized_source_drops_partial_first_line(self):
        with tempfile.TemporaryDirectory() as td:
            self.m.SOURCE_MAX_BYTES = 64 * 1024
            log = Path(td) / 'install.log'
            split_file(log, 64 * 1024, 'x' * 70000 + ' ', '/Users/' + USER + '/x', len('/Users/ali'), 'line\n')
            text = self.m._read_tail(log)
            self.assertTrue(text.startswith('line'), text[:40])
            self.assert_no_fragment(self.client().build_help_payload('1/10', 'J-UNK-00', '', text)['log_tail'])

    def test_redaction_spanning_lines_happens_before_line_cut(self):
        log = 'Bearer\n' + 'secretvalue\n' + 'ok\n' * 39
        payload = self.client().build_help_payload('1/10', 'J-UNK-00', '', log)
        self.assertNotIn('secretvalue', payload['log_tail'])
        self.assertLessEqual(len(payload['log_tail'].splitlines()), 40)

    def test_progress_post_has_wall_clock_deadline(self):
        gate = threading.Event()
        self.addCleanup(gate.set)

        def hang(*args):
            gate.wait(5)
            return 204, None
        self.m.PROGRESS_DEADLINE = 0.3
        client = self.client(hang)
        started = time.monotonic()
        ok = client.progress('1/10', 'start')
        self.assertFalse(ok)
        self.assertLess(time.monotonic() - started, 2)


class MacBashTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix='wave-g8r1-')
        self.addCleanup(temp.cleanup)
        self.home = Path(temp.name)
        self.pack = self.home / 'pack'
        (self.pack / 'lib').mkdir(parents=True)
        for name in ('steps.json', 'install-state.json'):
            shutil.copyfile(ROOT / name, self.pack / name)
        shutil.copyfile(ROOT / 'lib/help-notice.txt', self.pack / 'lib/help-notice.txt')
        (self.pack / 'lib/install_help_client.py').write_text(FAKE_CLIENT)
        self.lib = functions_sh(self.pack)
        self.calls = self.home / 'calls.jsonl'
        self.env = dict(os.environ, HOME=str(self.home), WAVE_HOME=str(self.home / '.wave'), USER=USER,
                        FAKE_HELP_LOG=str(self.calls), WAVE_NO_PROGRESS='0')
        self.env.pop('WAVE_HELP_BASE_URL', None)

    def bash(self, script, timeout=60, **extra):
        return subprocess.run(['bash', '-c', 'source "$1"; ' + script, 'g8r1', str(self.lib)],
                              env=dict(self.env, **extra), text=True, capture_output=True, timeout=timeout,
                              stdin=subprocess.DEVNULL)

    def count_calls(self):
        return len(self.calls.read_text().splitlines()) if self.calls.exists() else 0

    def test_failing_progress_is_disabled_after_install_budget(self):
        r = self.bash('show_help_notice >/dev/null; for i in 1 2 3 4 5 6 7 8 9 10; do help_progress start; done; echo DONE',
                      FAKE_HELP_RC='3')
        self.assertIn('DONE', r.stdout)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.count_calls(), 5)
        self.assertEqual((r.stdout + r.stderr).count('progress send failed (fail-open)'), 1)

    def test_fast_successful_progress_keeps_sending(self):
        r = self.bash('show_help_notice >/dev/null; for i in 1 2 3 4 5 6 7 8 9 10; do help_progress start; done; echo DONE')
        self.assertIn('DONE', r.stdout)
        self.assertEqual(self.count_calls(), 10)

    def test_hanging_progress_child_is_cut_by_total_wall_clock(self):
        started = time.monotonic()
        r = self.bash('show_help_notice >/dev/null; HELP_PROGRESS_CALL_CAP=1; help_progress start; echo "RC=$?"',
                      timeout=20, FAKE_HELP_SLEEP='30')
        self.assertIn('RC=0', r.stdout)
        self.assertLess(time.monotonic() - started, 8)

    def test_failed_step_reason_is_redacted_and_bounded(self):
        shutil.copyfile(ROOT / 'lib/install_help.py', self.pack / 'lib/install_help.py')
        r = self.bash('init_state; '
                      'step_s02() { python3 -c "print(\'y\' * 200000)" >&2; '
                      'echo "token ' + TOKEN + ' at /Users/' + USER + '/log" >&2; return 7; }; '
                      'run_step S02_CLAUDE_LOGIN || echo "RC=$?" > "$HOME/rc"')
        self.assertEqual((self.home / 'rc').read_text().strip(), 'RC=7', r.stderr[-500:])
        state = json.loads((self.home / '.wave/install-state.json').read_text())
        reason = state['steps']['S02_CLAUDE_LOGIN']['observed']['reason']
        self.assertLessEqual(len(reason.encode()), 4096 + 8)
        self.assertIn('<TOKEN>', reason)
        self.assertNotIn('TOKENVALUE', reason)
        self.assertNotIn(USER, reason)
        self.assertLess((self.home / '.wave/install-state.json').stat().st_size, 64 * 1024)

    def test_failed_step_reason_without_help_lib_still_hides_home(self):
        r = self.bash('init_state; step_s02() { echo "denied at $HOME/log" >&2; return 7; }; '
                      'run_step S02_CLAUDE_LOGIN || echo "RC=$?" > "$HOME/rc"')
        self.assertEqual((self.home / 'rc').read_text().strip(), 'RC=7', r.stderr[-500:])
        reason = json.loads((self.home / '.wave/install-state.json').read_text())['steps']['S02_CLAUDE_LOGIN']['observed']['reason']
        self.assertIn('denied at', reason)
        self.assertNotIn(str(self.home), reason)


class StepsAndNoticeTextTests(unittest.TestCase):
    def test_s05_text_matches_the_real_daemon_step(self):
        steps = json.loads((ROOT / 'steps.json').read_text(encoding='utf-8'))
        s05 = [s for s in steps['steps'] if s['id'] == 'S05_DAEMON_REGISTER'][0]
        text = json.dumps(s05, ensure_ascii=False)
        for stale in ('launchctl', 'plist', 'HKCU', 'Run:', '해제', '기본 on'):
            self.assertNotIn(stale, text)
        for os_name in ('macos', 'windows'):
            self.assertIn('cys daemon install', s05['command'][os_name])
            self.assertIn('cys ping', s05['command'][os_name])
        self.assertIn('bounded_cys daemon install', (ROOT / 'bootstrap.sh').read_text())
        self.assertIn('bounded_cys ping', (ROOT / 'bootstrap.sh').read_text())
        ps1 = (ROOT / 'bootstrap.ps1').read_text(encoding='utf-8-sig')
        self.assertIn("@('daemon', 'install')", ps1)
        self.assertIn("@('ping')", ps1)
        self.assertEqual((ROOT / 'site/steps.json').read_bytes(), (ROOT / 'steps.json').read_bytes())

    def test_notice_names_the_state_file_and_both_os_read_it(self):
        text = (ROOT / 'lib/help-notice.txt').read_text(encoding='utf-8')
        for needle in ('설치 상태 파일', '오류 출력', '96KB', '128KB', '알려진 형식'):
            self.assertIn(needle, text)
        self.assertIn('lib/help-notice.txt', (ROOT / 'bootstrap.sh').read_text())
        self.assertIn("'help-notice.txt'", (ROOT / 'lib/install-help.ps1').read_text(encoding='utf-8'))


class MacResumeAndPackTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix='wave-g8r1-s07-')
        self.addCleanup(temp.cleanup)
        self.home = Path(temp.name)
        self.wave = self.home / 'wave'
        (self.wave / 'bin').mkdir(parents=True)
        (self.wave / 'fleet').mkdir()
        (self.home / '.cys').mkdir()
        (self.home / '.cys/.gui-onboarded').write_text('0.0.0\n')
        self.fakebin = self.home / 'fakebin'
        self.fakebin.mkdir()
        (self.fakebin / 'open').write_text('#!/bin/sh\nexit 0\n')
        (self.fakebin / 'open').chmod(0o755)
        self.log = self.home / 'cys-calls.log'
        cys = self.wave / 'bin/cys'
        cys.write_text('#!/bin/sh\necho "$*" >> "$CYS_LOG"\ncase "$1" in\n'
                       'status) cat "$FLEET_JSON";;\nsend) [ "${SEND_RC:-0}" = 0 ] && [ -n "$FLEET_AFTER_SEND" ] && cp "$FLEET_AFTER_SEND" "$FLEET_JSON"; exit "${SEND_RC:-0}";;\n'
                       'launch-agent) [ -n "$FLEET_AFTER" ] && cp "$FLEET_AFTER" "$FLEET_JSON"; touch "$HOME/.cys/.master-bootstrapped"; echo surface:5;;\n'
                       'pack-manifest) cat "$MANIFEST_JSON";;\ninit-pack) sh -c "$INIT_PACK_ACTION";;\nesac\n')
        cys.chmod(0o755)
        self.lib = functions_sh(self.home)
        self.fleet = self.home / 'fleet.json'
        self.since = int(time.time()) - 30
        self.env = dict(os.environ, HOME=str(self.home), WAVE_HOME=str(self.wave), CYS_LOG=str(self.log),
                        FLEET_JSON=str(self.fleet), PATH=str(self.fakebin) + ':' + os.environ['PATH'],
                        MANIFEST_JSON=str(self.home / 'manifest.json'), INIT_PACK_ACTION=':')

    def bash(self, script):
        return subprocess.run(['bash', '-c', 'source "$1"; ' + script, 'g8r1', str(self.lib)], env=self.env,
                              text=True, capture_output=True, timeout=60, stdin=subprocess.DEVNULL)

    def seat(self, ref, role, created):
        return dict(surface_ref=ref, role=role, exited=False, agent_alive=True, created_at=created)

    def prepare(self, masters, saved_ref='surface:5', master_created=None):
        created = self.since + 5 if master_created is None else master_created
        rows = [self.seat(ref, 'master', created) for ref in masters]
        rows += [self.seat('surface:20', 'cso', self.since + 6), self.seat('surface:21', 'worker-1', self.since + 7)]
        self.fleet.write_text(json.dumps({'surfaces': rows}))
        (self.home / '.cys/.master-bootstrapped').write_text(json.dumps({'surface_ref': 'surface:5', 'orchestra_check': 'exit 0'}))
        if saved_ref:
            (self.wave / 'fleet/master-ref').write_text(saved_ref + '\n')
            (self.wave / 'fleet/started-at').write_text(str(self.since) + '\n')

    def new_surface_called(self):
        return self.log.exists() and 'launch-agent' in self.log.read_text()

    def test_resume_reuses_verified_master_of_this_install(self):
        self.prepare(['surface:5'])
        r = self.bash('step_s07; echo "RC=$?"; echo "$STEP_OBSERVED"')
        self.assertIn('RC=0', r.stdout, r.stderr)
        self.assertFalse(self.new_surface_called())
        self.assertEqual((self.wave / 'fleet/master-ref').read_text().strip(), 'surface:5')
        self.assertEqual((self.wave / 'fleet/started-at').read_text().strip(), str(self.since))
        self.assertIn('"master_reused":true', r.stdout.replace(' ', ''))
        self.assertNotIn('send ', self.log.read_text())

    def test_declared_reuse_sends_nothing(self):
        self.prepare(['surface:5'])
        (self.wave / 'fleet/declared').write_text('')
        r = self.bash('step_s07; echo "RC=$?"')
        self.assertIn('RC=0', r.stdout, r.stderr)
        self.assertNotIn('send ', self.log.read_text())
        self.assertFalse(self.new_surface_called())

    def test_declaration_failure_then_rerun_resends_once(self):
        future = int(time.time()) + 100
        self.prepare([], saved_ref=None)
        master_only = self.home / 'fleet-master.json'
        master_only.write_text(json.dumps({'surfaces': [self.seat('surface:5', 'master', future)]}))
        full = self.home / 'fleet-full.json'
        full.write_text(json.dumps({'surfaces': [self.seat('surface:5', 'master', future), self.seat('surface:20', 'cso', future),
                                                 self.seat('surface:21', 'worker-1', future)]}))
        self.env.update(FLEET_AFTER=str(master_only), FLEET_AFTER_SEND=str(full), SEND_RC='3')
        r = self.bash('step_s07; echo "RC=$?"')
        self.assertNotIn('RC=0', r.stdout)
        self.assertIn('J-PATH-02', r.stderr)
        self.assertFalse((self.wave / 'fleet/declared').exists())
        # 재실행 복구 두 꼴: 선언 전달 실패(master-ref 있음) · launch-agent 상한(master-ref 없음).
        for name, drop_ref in (('send-failed', False), ('launch-capped', True)):
            with self.subTest(name):
                self.log.unlink(missing_ok=True)
                (self.wave / 'fleet/declared').unlink(missing_ok=True)
                if drop_ref:
                    (self.wave / 'fleet/master-ref').unlink()
                self.fleet.write_text(master_only.read_text())
                (self.home / '.cys/.master-bootstrapped').write_text(json.dumps({'surface_ref': 'surface:5', 'orchestra_check': 'exit 0'}))
                self.env['SEND_RC'] = '0'
                r = self.bash('step_s07; echo "RC=$?"')
                self.assertIn('RC=0', r.stdout, r.stderr)
                calls = self.log.read_text().splitlines()
                self.assertEqual(sum(c.startswith('send --queued --to master') for c in calls), 1)
                self.assertFalse(self.new_surface_called())
                self.assertTrue((self.wave / 'fleet/declared').exists())
                self.assertEqual((self.wave / 'fleet/master-ref').read_text().strip(), 'surface:5')

    def test_new_master_gets_queued_declaration_after_launch_agent(self):
        future = int(time.time()) + 100
        self.prepare([], saved_ref=None)
        after = self.home / 'fleet-after.json'
        after.write_text(json.dumps({'surfaces': [self.seat('surface:5', 'master', future), self.seat('surface:20', 'cso', future),
                                                  self.seat('surface:21', 'worker-1', future)]}))
        self.env['FLEET_AFTER'] = str(after)
        r = self.bash('step_s07; echo "RC=$?"')
        self.assertIn('RC=0', r.stdout, r.stderr)
        calls = self.log.read_text().splitlines()
        launch = next(i for i, c in enumerate(calls) if c.startswith('launch-agent --role master'))
        send = next(i for i, c in enumerate(calls) if c.startswith('send --queued --to master 너는 마스터다 — '))
        self.assertLess(launch, send)
        self.assertNotIn('\n', calls[send])
        self.log.unlink(); self.fleet.write_text(json.dumps({'surfaces': []})); self.env['SEND_RC'] = '3'
        (self.wave / 'fleet/master-ref').unlink(); (self.wave / 'fleet/started-at').unlink()
        r = self.bash('step_s07; echo "RC=$?"')
        self.assertNotIn('RC=0', r.stdout)
        self.assertIn('J-PATH-02', r.stderr)

    def test_foreign_duplicate_or_older_master_is_still_refused(self):
        cases = {'foreign': (['surface:5'], 'surface:4', None), 'no-ref': (['surface:5'], None, None),
                 'duplicate': (['surface:5', 'surface:6'], 'surface:5', None),
                 'older': (['surface:5'], 'surface:5', self.since - 100)}
        for name, (masters, saved, created) in cases.items():
            with self.subTest(name):
                for path in (self.wave / 'fleet/master-ref', self.wave / 'fleet/started-at', self.log):
                    path.unlink(missing_ok=True)
                self.prepare(masters, saved, created)
                r = self.bash('step_s07')
                self.assertNotEqual(r.returncode, 0, r.stdout + r.stderr)
                self.assertFalse(self.new_surface_called())

    def directive_fixture(self):
        pack = self.home / '.cys/pack'
        (pack / 'directives').mkdir(parents=True, exist_ok=True)
        body = b'full app directive\n'
        files = {}
        for role in ('MASTER', 'CSO', 'WORKER'):
            (pack / f'directives/{role}_DIRECTIVE.md').write_bytes(body)
            files[f'directives/{role}_DIRECTIVE.md'] = hashlib.sha256(body).hexdigest()
        (self.home / 'manifest.json').write_text(json.dumps({'files': files}))
        return pack

    def test_seed_once_product_profile_new_does_not_halt_s06_or_s08(self):
        pack = self.directive_fixture()
        (pack / 'preflight-product-profile.json').write_text('{"warnings": {}}\n')
        self.env['INIT_PACK_ACTION'] = 'printf vendor > "$HOME/.cys/pack/preflight-product-profile.json.new"'
        r = self.bash('SCRIPT_DIR="' + str(ROOT) + '"; step_s06; echo "RC=$?"; verify_original_injection >/dev/null; echo "G3=$?"')
        self.assertIn('RC=0', r.stdout, r.stderr)
        self.assertIn('G3=0', r.stdout, r.stderr)
        self.assertEqual((pack / 'preflight-product-profile.json').read_text(), '{"warnings": {}}\n')
        self.env['INIT_PACK_ACTION'] = 'printf vendor > "$HOME/.cys/pack/soul.md.new"'
        r = self.bash('SCRIPT_DIR="' + str(ROOT) + '"; step_s06; echo "RC=$?"; verify_original_injection >/dev/null; echo "G3=$?"')
        self.assertNotIn('RC=0', r.stdout)
        self.assertNotIn('G3=0', r.stdout)

    def test_s06_exposes_pack_cys_dept_next_to_cys_like_preflight_c11b(self):
        pack = self.directive_fixture()
        self.env['INIT_PACK_ACTION'] = ('mkdir -p "$HOME/.cys/pack/bin" && printf "#!/bin/sh\\necho dept\\n" '
                                        '> "$HOME/.cys/pack/bin/cys-dept" && chmod 644 "$HOME/.cys/pack/bin/cys-dept"')
        r = self.bash('SCRIPT_DIR="' + str(ROOT) + '"; step_s06; echo "RC=$?"; echo "$STEP_OBSERVED"')
        self.assertIn('RC=0', r.stdout, r.stderr)
        link, src = self.wave / 'bin/cys-dept', pack / 'bin/cys-dept'
        self.assertTrue(link.is_symlink())
        self.assertEqual(os.path.realpath(link), os.path.realpath(src))
        self.assertTrue(os.access(link, os.X_OK))
        self.assertEqual(json.loads(r.stdout.strip().splitlines()[-1])['cys_dept'], 'linked')
        link.unlink()
        link.write_text('user owned\n')
        r = self.bash('SCRIPT_DIR="' + str(ROOT) + '"; step_s06; echo "RC=$?"; echo "$STEP_OBSERVED"')
        self.assertIn('RC=0', r.stdout, r.stderr)
        self.assertEqual(link.read_text(), 'user owned\n')
        self.assertEqual(json.loads(r.stdout.strip().splitlines()[-1])['cys_dept'], 'user_file_preserved')

    def test_cdhash_pin_must_be_present(self):
        steps = json.loads((ROOT / 'steps.json').read_text())
        good = steps['release']['cdhash']['macos_arm64']
        for name, value, ok in (('valid', good, True), ('empty', '', False), ('null', None, False),
                                ('placeholder', '__CDHASH__', False), ('short', 'abc', False), ('missing', ..., False)):
            with self.subTest(name):
                config = json.loads(json.dumps(steps))
                if value is ...:
                    del config['release']['cdhash']['macos_arm64']
                else:
                    config['release']['cdhash']['macos_arm64'] = value
                path = self.home / 'steps.json'
                path.write_text(json.dumps(config))
                r = self.bash('STEPS_FILE="' + str(path) + '"; RELEASE_PLATFORM=macos_arm64; release_cdhash_pin')
                self.assertEqual(r.returncode == 0, ok, r.stdout + r.stderr)
                if ok:
                    self.assertEqual(r.stdout.strip(), good)
                self.assertNotIn('Traceback', r.stderr)
        body = (ROOT / 'bootstrap.sh').read_text().split('step_s03() {', 1)[1].split('\n}\n', 1)[0]
        self.assertIn('release_cdhash_pin', body)
        self.assertLess(body.index('release_cdhash_pin'), body.index('curl --fail'))


class MacArchGateTests(unittest.TestCase):
    """S00 stops on Intel macs; arm64 and Rosetta (proc_translated=1) pass. uname/sysctl are faked."""
    def run_s00(self, machine, translated, arm64_flag):
        with tempfile.TemporaryDirectory(prefix='wave-arch-') as tmp:
            home = Path(tmp)
            fakebin = home / 'fakebin'; fakebin.mkdir()
            (fakebin / 'uname').write_text('#!/bin/sh\n[ "$1" = -m ] && echo %s || echo Darwin\n' % machine)
            (fakebin / 'sysctl').write_text('#!/bin/sh\ncase "$2" in sysctl.proc_translated) %s;; hw.optional.arm64) %s;; esac\n'
                                            % (translated, arm64_flag))
            for f in fakebin.iterdir():
                f.chmod(0o755)
            steps = home / 'steps.json'
            steps.write_text(json.dumps({'tooling': {'min_free_bytes': 1}}))
            env = dict(os.environ, HOME=str(home), WAVE_HOME=str(home / 'wave'), STEPS_FILE=str(steps),
                       PATH=str(fakebin) + ':' + os.environ['PATH'])
            return subprocess.run(['bash', '-c', 'source "$1"; STEPS_FILE="$STEPS_FILE"; step_s00; echo "RC=$?"', 'arch',
                                   str(functions_sh(home))], env=env, text=True, capture_output=True, timeout=30)

    def test_intel_mac_stops_at_s00_with_message(self):
        r = self.run_s00('x86_64', 'echo 0', 'echo 0')
        self.assertNotIn('RC=0', r.stdout)
        self.assertIn('J-VER-03', r.stderr)
        self.assertIn('이 판은 Apple Silicon(M1 이후) 맥 전용입니다 — Intel 맥은 아직 지원하지 않습니다', r.stderr)

    def test_arm64_and_rosetta_shell_pass(self):
        for name, args in (('arm64', ('arm64', 'exit 1', 'exit 1')), ('rosetta', ('x86_64', 'echo 1', 'echo 0'))):
            with self.subTest(name):
                r = self.run_s00(*args)
                self.assertIn('RC=0', r.stdout, r.stderr)


class RedactionPatternTests(unittest.TestCase):
    SAMPLES = [
        'key AIzaSyA1234567890abcdefghijklmnopqrstuv end',
        'slack xoxb-1234567890-abcdefghij and xoxp-0987654321-zyxwvutsrq',
        'jwt eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.dozjgNryP4J3jVmNHl0w5N_XgL0n3I9PlFUP0THsR8U',
        'npm npm_abcdefghijklmnopqrstuvwxyz0123456789',
        'aws AKIAIOSFODNN7EXAMPLE',
        'API_KEY=supersecretvalue', 'MY_TOKEN: "abc123def"', '"client_secret": "hunter2hunter2"',
        'prefixghp_abcdefghijklmnopqrstuvwxyz', 'API_KEY_sk-abcdefghijklmn',
        r'C:\Users\Kyle Choi\AppData\x.log', '/Users/Kyle Choi/Library/x.log',
    ]
    LEAKS = ['AIzaSyA1234567890', 'xoxb-1234567890', 'xoxp-0987654321', 'eyJzdWIi', 'npm_abcdefghij',
             'AKIAIOSFODNN7', 'supersecretvalue', 'abc123def', 'hunter2', 'ghp_abcdef', 'sk-abcdefghijklmn', 'Choi']

    def safe(self, text, username='kyle'):
        import install_help
        return importlib.reload(install_help).safe_text(text, username)

    def test_new_patterns_are_redacted(self):
        for sample in self.SAMPLES:
            with self.subTest(sample=sample):
                out = self.safe(sample)
                for leak in self.LEAKS:
                    self.assertNotIn(leak, out)

    def test_ordinary_words_survive(self):
        self.assertEqual(self.safe('run task-runner now; keyboard ok'), 'run task-runner now; keyboard ok')

    @unittest.skipUnless(PWSH, 'PowerShell is required for OS parity')
    def test_windows_and_mac_same_new_redaction(self):
        with tempfile.TemporaryDirectory() as td:
            data = Path(td) / 'input.json'
            data.write_text(json.dumps(self.SAMPLES), encoding='utf-8')
            script = Path(td) / 'parity.ps1'
            script.write_text("param($Module,$InputFile)\n$ErrorActionPreference='Stop'\n. $Module\n@((Get-Content $InputFile -Raw | ConvertFrom-Json) | ForEach-Object { ConvertTo-HelpSafeText $_ 'kyle' }) | ConvertTo-Json -Compress\n", encoding='utf-8-sig')
            result = subprocess.run([PWSH, '-NoProfile', '-File', str(script), str(ROOT / 'lib/install-help.ps1'), str(data)],
                                    capture_output=True, text=True, timeout=20)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(result.stdout.lstrip('\ufeff')), [self.safe(x) for x in self.SAMPLES])


class SilentListener:
    """Loopback TCP listener that accepts and never answers (DNS/TLS-stall stand-in). Owned and closed here."""
    def __enter__(self):
        self.sock = socket.socket()
        self.sock.bind(('127.0.0.1', 0))
        self.sock.listen(4)
        self.port = self.sock.getsockname()[1]
        self.conns = []
        self.stop = False
        self.thread = threading.Thread(target=self.serve, daemon=True)
        self.thread.start()
        return self

    def serve(self):
        self.sock.settimeout(0.2)
        while not self.stop:
            try:
                self.conns.append(self.sock.accept()[0])
            except OSError:
                pass

    def __exit__(self, *exc):
        self.stop = True
        self.thread.join(2)
        for conn in self.conns:
            conn.close()
        self.sock.close()


@unittest.skipUnless(PWSH, 'PowerShell is required')
class WindowsProgressAndPackTests(unittest.TestCase):
    def run_ps(self, body, extra_env=None):
        with tempfile.TemporaryDirectory(dir=ROOT, prefix='.g8r1-win-') as tmp:
            home = Path(tmp)
            source = (ROOT / 'bootstrap.ps1').read_text(encoding='utf-8-sig').split('\nLoad-Config\nif ($DryRun)')[0]
            source = source.replace('https://waveainetworks.com', 'https://127.0.0.1:9')
            script = home / 'harness.ps1'
            script.write_text(source + '\n' + body, encoding='utf-8-sig')
            env = dict(os.environ, USERPROFILE=str(home), WAVE_HOME=str(home / 'wave'), WAVE_NO_PROGRESS='1')
            env.update(extra_env or {})
            result = subprocess.run([PWSH, '-NoProfile', '-NonInteractive', '-File', str(script)], env=env,
                                    capture_output=True, text=True, encoding='utf-8', timeout=60)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            return result.stdout

    def test_failing_progress_is_disabled_after_install_budget(self):
        self.run_ps(r'''
$env:WAVE_NO_PROGRESS = '0'
$script:HelpNoticeShown = $true
$script:calls = 0
New-Item -ItemType Directory -Force -Path $WaveHome | Out-Null
function Invoke-ProgressPost { param($Uri, $Body, $TimeoutMs) $script:calls++; throw 'network down' }
function Write-Log { }
1..10 | ForEach-Object { Send-Progress '1/10' 'start' }
if ($calls -ne 5) { throw "budget not enforced: $calls" }
''')

    def test_progress_post_wall_clock_against_silent_listener(self):
        with SilentListener() as listener:
            out = self.run_ps(r'''
$sw = [Diagnostics.Stopwatch]::StartNew()
$failed = $false
try { Invoke-ProgressPost ([uri]('https://127.0.0.1:' + $env:SILENT_PORT + '/api/progress')) ([Text.Encoding]::UTF8.GetBytes('{}')) 800 } catch { $failed = $true }
if (-not $failed) { throw 'silent endpoint reported success' }
if ($sw.ElapsedMilliseconds -lt 500) { throw "no real attempt: $($sw.ElapsedMilliseconds)" }
if ($sw.ElapsedMilliseconds -gt 2500) { throw "deadline exceeded: $($sw.ElapsedMilliseconds)" }
Write-Host "ELAPSED=$($sw.ElapsedMilliseconds)"
''', {'SILENT_PORT': str(listener.port)})
        self.assertIn('ELAPSED=', out)

    def test_progress_post_refuses_redirects_and_send_progress_uses_it(self):
        source = (ROOT / 'bootstrap.ps1').read_text(encoding='utf-8-sig')
        post = source.split('function Invoke-ProgressPost', 1)[1].split('\n}\n', 1)[0]
        self.assertIn('$handler.AllowAutoRedirect = $false', post)
        self.assertIn('$task.Wait($TimeoutMs)', post)
        send = source.split('function Send-Progress', 1)[1].split('\n}\n', 1)[0]
        self.assertIn('Invoke-ProgressPost', send)
        self.assertNotIn('Invoke-WebRequest', send)

    def test_seed_once_product_profile_new_does_not_halt_s06_or_g3(self):
        self.run_ps(r'''
New-Item -ItemType Directory -Force (Join-Path $ScriptDir 'wave-pack/directives'), (Join-Path $PackHome 'directives') | Out-Null
$target = Join-Path $PackHome 'directives/MASTER_DIRECTIVE.md'
[IO.File]::WriteAllText((Join-Path $PackHome 'preflight-product-profile.json'), '{"warnings": {}}')
$script:NewName = 'preflight-product-profile.json.new'
function Invoke-BoundedCheck($FilePath, $Arguments, $Name, $TimeoutMs) {
  if ($Arguments[0] -eq 'init-pack') {
    [IO.File]::WriteAllText($target, 'full app directive')
    [IO.File]::WriteAllText((Join-Path $PackHome $script:NewName), 'vendor')
    return [pscustomobject]@{ timed_out = $false; exit_code = 0; stderr = ''; stdout = '' }
  }
  $hash = Get-ArtifactHash $target
  return [pscustomobject]@{ timed_out = $false; exit_code = 0; stderr = ''; stdout = ('{"files":{"directives/MASTER_DIRECTIVE.md":"' + $hash + '","directives/CSO_DIRECTIVE.md":"' + $hash + '","directives/WORKER_DIRECTIVE.md":"' + $hash + '"}}') }
}
foreach ($role in 'CSO','WORKER') { [IO.File]::WriteAllText((Join-Path $PackHome "directives/${role}_DIRECTIVE.md"), 'full app directive') }
Run-S06
$null = Test-OriginalInjection
if ([IO.File]::ReadAllText((Join-Path $PackHome 'preflight-product-profile.json')) -ne '{"warnings": {}}') { throw 'user profile touched' }
$script:NewName = 'soul.md.new'
$blocked = $false
try { Run-S06 } catch { $blocked = $true }
if (-not $blocked) { throw 'other .new accepted by S06' }
$blocked = $false
try { $null = Test-OriginalInjection } catch { $blocked = $true }
if (-not $blocked) { throw 'other .new accepted by G3' }
''')


    def test_s06_writes_the_exact_c11b_cys_dept_launcher(self):
        out = self.run_ps(r'''
New-Item -ItemType Directory -Force (Join-Path $ScriptDir 'wave-pack/directives'), (Join-Path $PackHome 'directives'), (Join-Path $WaveHome 'bin') | Out-Null
$target = Join-Path $PackHome 'directives/MASTER_DIRECTIVE.md'
function Invoke-BoundedCheck($FilePath, $Arguments, $Name, $TimeoutMs) {
  if ($Arguments[0] -eq 'init-pack') {
    [IO.File]::WriteAllText($target, 'full app directive')
    New-Item -ItemType Directory -Force (Join-Path $PackHome 'bin') | Out-Null
    [IO.File]::WriteAllText((Join-Path $PackHome 'bin/cys-dept'), 'dept')
    return [pscustomobject]@{ timed_out = $false; exit_code = 0; stderr = ''; stdout = '' }
  }
  return [pscustomobject]@{ timed_out = $false; exit_code = 0; stderr = ''; stdout = ('{"files":{"directives/MASTER_DIRECTIVE.md":"' + (Get-ArtifactHash $target) + '"}}') }
}
Run-S06
if ($StepObserved.cys_dept -ne 'linked') { throw "first: $($StepObserved.cys_dept)" }
Write-Host ('PACK=' + (Join-Path $PackHome 'bin/cys-dept'))
Write-Host ('LAUNCHER=' + [Convert]::ToBase64String([IO.File]::ReadAllBytes((Join-Path $WaveHome 'bin/cys-dept.cmd'))))
Run-S06
if ($StepObserved.cys_dept -ne 'linked') { throw "idempotent: $($StepObserved.cys_dept)" }
[IO.File]::WriteAllText((Join-Path $WaveHome 'bin/cys-dept.cmd'), 'user owned')
Run-S06
if ($StepObserved.cys_dept -ne 'user_file_preserved') { throw "preserve: $($StepObserved.cys_dept)" }
if ([IO.File]::ReadAllText((Join-Path $WaveHome 'bin/cys-dept.cmd')) -ne 'user owned') { throw 'user launcher overwritten' }
''')
        import base64
        values = dict(line.split('=', 1) for line in out.splitlines() if line.startswith(('PACK=', 'LAUNCHER=')))
        src = values['PACK']
        raw = base64.b64decode(values['LAUNCHER'])
        self.assertFalse(raw.startswith(b'\xef\xbb\xbf'))
        self.assertIn(b'\r\n', raw)
        # javis_preflight.py C11b(Windows) reads the file in text mode and compares to exactly this body.
        expected = '@echo off\nbash "' + src.replace('\\', '/').replace('%', '%%') + '" %*\n'
        self.assertEqual(raw.decode('utf-8').replace('\r\n', '\n'), expected)

    def test_failed_step_reason_is_redacted_and_bounded(self):
        for with_lib in (True, False):
            with self.subTest(with_lib=with_lib):
                load = (". '" + str(ROOT / 'lib/install-help.ps1') + "'") if with_lib else ''
                out = self.run_ps(load + r'''
$env:USERNAME = 'alicesmith'
$script:Config = [pscustomobject]@{ steps = @([pscustomobject]@{ id = 'S02_CLAUDE_LOGIN'; optional = $false; on_fail = [pscustomobject]@{ error_id = 'E-S02' } }) }
$script:Recorded = $null
function Update-Step($Id, $Status, $ExitCode, $ErrorId, $Observed) { if ($Status -eq 'failed') { $script:Recorded = $Observed } }
function Write-JCode { }
$logged = ''
function Write-Log([string]$Message) { $script:logged += $Message }
$secret = 'token sk-SECRETTOKENVALUE1234567890 at ' + $env:USERPROFILE + '/alicesmith/log'
try { Invoke-Step 'S02_CLAUDE_LOGIN' { throw ("init-pack 실패: " + ('y' * 200000) + "`n" + $secret) } } catch { }
$reason = [string]$Recorded.reason
Write-Host ('BYTES=' + [Text.Encoding]::UTF8.GetByteCount($reason))
Write-Host ('REASON=' + $reason.Substring([Math]::Max(0, $reason.Length - 200)).Replace("`n", ' '))
Write-Host ('HEAD=' + $reason.Substring(0, 3))
Write-Host ('POSITION_HAS_HOME=' + ([string]$Recorded.position).Contains($env:USERPROFILE))
Write-Host ('LOG_FULL=' + $logged.Contains('SECRETTOKENVALUE') + '/' + ($logged.Length -gt 200000))
''')
                values = dict(line.split('=', 1) for line in out.splitlines() if '=' in line and line.split('=', 1)[0].isupper())
                self.assertLessEqual(int(values['BYTES']), 4096 + 8)
                self.assertEqual(values['HEAD'], '...')
                self.assertIn('at ', values['REASON'])
                self.assertNotIn('alicesmith', values['REASON'])
                if with_lib:
                    self.assertIn('/Users/<USER>/', values['REASON'])
                else:
                    self.assertNotIn('.g8r1-win-', values['REASON'])
                    self.assertEqual(values['POSITION_HAS_HOME'], 'False')
                self.assertEqual(values['LOG_FULL'], 'True/True')
                if with_lib:
                    self.assertIn('<TOKEN>', values['REASON'])
                    self.assertNotIn('TOKENVALUE', values['REASON'])


if __name__ == '__main__':
    unittest.main()
