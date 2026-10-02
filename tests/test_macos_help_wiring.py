"""R5 macOS bootstrap wiring: notice gate, progress start/end/fail, final-failure help, fail-open.

A fake lib/install_help_client.py records its arguments (no network). The fail-open check with the
real client targets a loopback port that has no listener (proved free before and after) — no server.
"""
import json
import os
import shutil
import socket
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FAKE_CLIENT = '''import json, os, sys
with open(os.environ["FAKE_HELP_LOG"], "a") as h:
    h.write(json.dumps(sys.argv[1:]) + "\\n")
sys.exit(int(os.environ.get("FAKE_HELP_RC", "0")))
'''


def free_port():
    with socket.socket() as s:
        s.bind(('127.0.0.1', 0))
        return s.getsockname()[1]


def port_is_free(port):
    with socket.socket() as s:
        return s.connect_ex(('127.0.0.1', port)) != 0


class MacHelpWiringTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix='wave-r5-mac-')
        self.addCleanup(temp.cleanup)
        self.home = Path(temp.name)
        self.pack = self.home / 'pack'
        (self.pack / 'lib').mkdir(parents=True)
        (self.pack / 'wave-pack').mkdir()
        for name in ('steps.json', 'install-state.json'):
            shutil.copyfile(ROOT / name, self.pack / name)
        shutil.copyfile(ROOT / 'lib/help-notice.txt', self.pack / 'lib/help-notice.txt')
        (self.pack / 'lib/install_help_client.py').write_text(FAKE_CLIENT)
        source = (ROOT / 'bootstrap.sh').read_text()
        marker = '\nmain "$@"\n'
        self.assertEqual(source.count(marker), 1)
        self.lib = self.pack / 'functions.sh'
        self.lib.write_text(source.rsplit(marker, 1)[0] + '\n')
        self.calls = self.home / 'calls.jsonl'
        self.env = dict(os.environ, HOME=str(self.home), WAVE_HOME=str(self.home / '.wave'),
                        FAKE_HELP_LOG=str(self.calls), WAVE_NO_PROGRESS='0')
        self.env.pop('WAVE_HELP_BASE_URL', None)

    def bash(self, script, **extra):
        return subprocess.run(['bash', '-c', 'source "$1"; ' + script, 'r5', str(self.lib)],
                              env=dict(self.env, **extra), text=True, capture_output=True, timeout=60,
                              stdin=subprocess.DEVNULL)

    def recorded(self):
        if not self.calls.exists():
            return []
        return [json.loads(line) for line in self.calls.read_text().splitlines()]

    def test_nothing_is_sent_before_notice_or_with_no_progress(self):
        r = self.bash('HELP_STEP=1/10; help_progress start; help_request')
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.recorded(), [])
        r = self.bash('show_help_notice; help_progress start; help_request', WAVE_NO_PROGRESS='1')
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertNotIn('30일', r.stdout + r.stderr)
        self.assertEqual(self.recorded(), [])

    def test_main_failure_sends_start_fail_help_and_keeps_exit_and_state(self):
        script = ('step_s00() { echo "boom /Users/alice" >&2; return 7; }; '
                  'set +e; (set -e; main); echo "MAIN_RC=$?"')
        r = self.bash(script, FAKE_HELP_RC='3')
        out = r.stdout + r.stderr
        self.assertIn('MAIN_RC=1', out)
        self.assertIn('30일', out)
        calls = self.recorded()
        self.assertEqual([c[0] for c in calls], ['progress', 'progress', 'help'])
        self.assertIn('start', calls[0]); self.assertIn('fail', calls[1]); self.assertIn('J-UNK-00', calls[1])
        for call in calls:
            self.assertIn('--notice-shown', call)
            self.assertIn('1/10', call)
            self.assertIn('--version', call)
        self.assertNotIn('--interactive', calls[2])  # stdin is not a TTY here
        self.assertIn(str(self.home / '.wave/install.log'), calls[2])
        self.assertEqual(out.count('progress send failed (fail-open)'), 1)
        state = json.loads((self.home / '.wave/install-state.json').read_text())
        self.assertEqual(state['steps']['S00_PREFLIGHT']['status'], 'failed')
        self.assertEqual(state['steps']['S00_PREFLIGHT']['exit_code'], 7)

    def test_success_and_optional_failure_send_end_and_fail_without_help(self):
        r = self.bash('init_state; show_help_notice; HELP_VERSION=9.9.9; '
                      'HELP_STEP=3/10; step_s02() { return 0; }; run_step S02_CLAUDE_LOGIN; '
                      'HELP_STEP=7/10; step_s05() { return 4; }; run_step S05_DAEMON_REGISTER; echo "RC=$?"')
        self.assertIn('RC=0', r.stdout + r.stderr)
        events = [(c[c.index('--step') + 1], c[c.index('--event') + 1]) for c in self.recorded()]
        self.assertEqual(events, [('3/10', 'start'), ('3/10', 'end'), ('7/10', 'start'), ('7/10', 'fail')])

    def test_real_client_against_dead_endpoint_is_fail_open(self):
        port = free_port()
        self.assertTrue(port_is_free(port))
        client = (ROOT / 'lib/install_help_client.py').read_text()
        self.assertEqual(client.count("'https://waveainetworks.com'"), 1)
        # Safety net: in this test copy the production default endpoint points at a closed loopback port.
        (self.pack / 'lib/install_help_client.py').write_text(client.replace("'https://waveainetworks.com'", "'https://127.0.0.1:9'"))
        shutil.copyfile(ROOT / 'lib/install_help.py', self.pack / 'lib/install_help.py')
        script = 'step_s00() { echo "boom" >&2; return 7; }; set +e; (set -e; main); echo "MAIN_RC=$?"'
        dead = self.bash(script, WAVE_HELP_BASE_URL=f'https://127.0.0.1:{port}')
        dead_state = json.loads((self.home / '.wave/install-state.json').read_text())
        shutil.rmtree(self.home / '.wave')
        off = self.bash(script, WAVE_NO_PROGRESS='1')
        off_state = json.loads((self.home / '.wave/install-state.json').read_text())
        self.assertTrue(port_is_free(port))
        for r in (dead, off):
            self.assertIn('MAIN_RC=1', r.stdout + r.stderr)
            self.assertNotIn('Traceback', r.stdout + r.stderr)
        self.assertIn('도움 요청을 보내지 못했습니다', dead.stdout + dead.stderr)
        strip = lambda s: {k: (v['status'], v['exit_code'], v['error_id']) for k, v in s['steps'].items()}
        self.assertEqual(strip(dead_state), strip(off_state))
        self.assertEqual(dead_state['status'], off_state['status'])
        self.assertTrue((self.home / '.wave/install-id.txt').exists() is False)  # off run never created an id

    def test_release_pack_ships_help_libs(self):
        with tempfile.TemporaryDirectory() as out:
            r = subprocess.run(['bash', str(ROOT / 'scripts/make-release.sh'),
                                json.loads((ROOT / 'steps.json').read_text())['version'],
                                'https://example.test/rel', out], capture_output=True, text=True, timeout=120)
            self.assertEqual(r.returncode, 0, r.stderr)
            version = json.loads((ROOT / 'steps.json').read_text())['version']
            listing = subprocess.run(['tar', '-tzf', str(Path(out) / f'wave-install-{version}.tar.gz')],
                                     capture_output=True, text=True).stdout.split()
            import zipfile
            names = zipfile.ZipFile(Path(out) / f'wave-install-{version}.zip').namelist()
            self.assertFalse([n for n in listing + names if '__pycache__' in n])
            for rel in ('lib/install_help.py', 'lib/install_help_client.py', 'lib/install-help.ps1', 'lib/help-notice.txt'):
                self.assertIn(f'wave-install-{version}/{rel}', listing)
                self.assertIn(f'wave-install-{version}/{rel}', names)


if __name__ == '__main__':
    unittest.main()
