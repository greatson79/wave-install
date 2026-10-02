"""R5 install-help client parity: PowerShell (lib/install-help.ps1) vs Python (lib/install_help_client.py).

Both run the same scripted fake transport; no real network. pwsh on macOS proves the
PowerShell logic only — not Windows PowerShell 5.1 or HttpWebRequest behaviour on Windows.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PWSH = os.environ.get('PWSH') or shutil.which('pwsh')
sys.path.insert(0, str(ROOT / 'lib'))

RID, TOKEN = 'c' * 32, 'b' * 64
REPLY = {'state': 'answered', 'messages': [
    {'seq': 2, 'kind': 'text', 'body': '둘째\x1b]0;t\x07 줄\r\n다음'},
    {'seq': 1, 'kind': 'text', 'body': 'hello\x1b[31m world\x00'},
    {'seq': 3, 'kind': 'command', 'body': 'touch /tmp/no'}]}
SCENARIOS = {
    'busy_poll_close': {'interactive': True, 'responses': [
        [503, {'error': 'busy'}], [201, {'id': RID, 'client_token': TOKEN}],
        [200, REPLY], [200, REPLY], [410, {'state': 'closed'}], [200, {}]]},
    'busy_twice': {'interactive': True, 'responses': [[503, {}], [503, {}]]},
    'bad_receipt': {'interactive': True, 'responses': [[201, {'id': '../x', 'client_token': TOKEN}]]},
    'down': {'interactive': True, 'responses': ['raise']},
    'non_interactive': {'interactive': False, 'responses': [[201, {'id': RID, 'client_token': TOKEN}]]},
    'gone_404': {'interactive': True, 'responses': [[201, {'id': RID, 'client_token': TOKEN}], [404, {}], [200, {}]]},
}
ENV = 'user alice@example.com\nUSERNAME=alice\nC:\\Users\\alice\\x /Users/alice/y\n' + '환경' * 40000
LOG = ''.join(f'line {i} Bearer tok{i} sk-abcdefghij{i}\r\n' for i in range(200)) + '끝' * 70000


def run_python(scenario):
    import install_help_client as m
    responses = [x for x in scenario['responses']]
    calls, sleeps, output, tick = [], [], [], [0]

    def send(method, path, payload, token, timeout):
        calls.append({'method': method, 'path': path, 'payload': payload, 'token': token, 'timeout': timeout})
        value = responses.pop(0)
        if value == 'raise':
            raise OSError('down /Users/alice')
        return value[0], value[1]

    def sleep(seconds):
        sleeps.append(seconds); tick[0] += seconds
    client = m.HelpClient('https://example.test', 'a' * 32, '9.9.9', notice=True, username='alice',
                          transport=send, sleep=sleep, clock=lambda: tick[0], emit=output.append)
    client.help('3/10', 'J-NET-01', ENV, LOG, scenario['interactive'])
    return {'calls': calls, 'sleeps': sleeps, 'output': output}


@unittest.skipUnless(PWSH, 'PowerShell is required for OS parity')
class WindowsHelpClientParity(unittest.TestCase):
    def run_ps(self, extra_env=None):
        with tempfile.TemporaryDirectory() as td:
            data = Path(td) / 'scenarios.json'
            data.write_text(json.dumps({'scenarios': SCENARIOS, 'env': ENV, 'log': LOG}), encoding='utf-8')
            env = dict(os.environ, USERPROFILE=td, HOME=td, WAVE_NO_PROGRESS='0', **(extra_env or {}))
            result = subprocess.run([PWSH, '-NoProfile', '-NonInteractive', '-File',
                                     str(ROOT / 'tests/windows_help_client_fixture.ps1'), str(data)],
                                    capture_output=True, text=True, encoding='utf-8', env=env, timeout=120)
            self.assertEqual(result.returncode, 0, result.stdout[-2000:] + result.stderr[-2000:])
            marker = result.stdout.rindex('RESULT:')
            return json.loads(result.stdout[marker + 7:].strip())

    def test_same_payload_polling_and_display_as_python(self):
        ps = self.run_ps()
        self.assertTrue(ps['gate']['no_call_before_notice'])
        self.assertTrue(ps['gate']['no_progress_blocks_help'])
        for name, scenario in SCENARIOS.items():
            with self.subTest(name):
                py, win = run_python(scenario), ps['results'][name]
                self.assertEqual(win['sleeps'], py['sleeps'])
                self.assertEqual(win['output'], py['output'])
                self.assertEqual(len(win['calls']), len(py['calls']))
                for a, b in zip(win['calls'], py['calls']):
                    self.assertEqual((a['method'], a['path'], a['token'], a['timeout']),
                                     (b['method'], b['path'], b['token'], b['timeout']))
                    pa, pb = dict(a['payload'] or {}), dict(b['payload'] or {})
                    self.assertEqual(pa.pop('os', None), 'win' if pb else None)
                    pb.pop('os', None)
                    self.assertEqual(pa, pb)
        sent = json.dumps(ps['results']['busy_poll_close']['calls'][0]['payload'])
        for leak in ('alice', 'tok1', 'sk-abcdefghij'):
            self.assertNotIn(leak, sent)
        self.assertNotIn(TOKEN, json.dumps(ps['results']['busy_poll_close']['output']))
        self.assertFalse(any('touch' in x for x in ps['results']['busy_poll_close']['output']))

    def test_notice_text_identical_on_both_oses(self):
        ps = self.run_ps()
        self.assertEqual(ps['notice'].strip(), (ROOT / 'lib/help-notice.txt').read_text(encoding='utf-8').strip())


if __name__ == '__main__':
    unittest.main()
