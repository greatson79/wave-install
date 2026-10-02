"""R5 install-help client (macOS/Python side). Transport, sleep and clock are injected: no real network."""
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'lib'))


class HelpClientTests(unittest.TestCase):
    def client(self, responses, notice=True, interactive=True):
        self.assertTrue((ROOT / 'lib/install_help_client.py').exists(), 'R5 transport module missing')
        import install_help_client as m
        self.calls = []; self.sleeps = []; self.output = []; self.tick = 0

        def send(method, path, payload, token, timeout):
            self.calls.append((method, path, payload, token, timeout))
            value = responses.pop(0)
            if isinstance(value, Exception):
                raise value
            return value

        def sleep(seconds):
            self.sleeps.append(seconds); self.tick += seconds
        return m.HelpClient('https://example.test', 'a' * 32, '9.9.9', notice=notice, username='alice',
                            transport=send, sleep=sleep, clock=lambda: self.tick, emit=self.output.append)

    def test_notice_gate_and_progress_failure(self):
        c = self.client([], False)
        c.progress('1/10', 'start')
        c.help('1/10', 'J-UNK-00', 'env', 'log', True)
        self.assertEqual(self.calls, [])
        c = self.client([OSError('secret raw error'), (503, {})])
        c.progress('1/10', 'start'); c.progress('2/10', 'fail', detail='J-UNK-00')
        self.assertEqual(len(self.calls), 2)
        self.assertEqual(self.calls[0][4], 3)
        self.assertEqual(self.calls[1][2]['detail'], 'J-UNK-00')
        self.assertEqual(len(self.output), 1)  # warn once, never the raw error
        self.assertNotIn('secret', ''.join(self.output))
        self.assertEqual(self.sleeps, [])  # progress 503 is dropped, never retried

    def test_progress_payload_shape_and_detail_filter(self):
        c = self.client([(204, None)])
        c.progress('3/10', 'start', detail='raw /Users/alice/secret')
        method, path, payload, token, timeout = self.calls[0]
        self.assertEqual((method, path, token), ('POST', '/api/progress', None))
        self.assertEqual(set(payload), {'install_id', 'installer_version', 'os', 'step', 'event', 'at'})
        self.assertEqual(payload['os'], 'mac')
        self.assertLessEqual(len(json.dumps(payload).encode()), 8 * 1024)

    def test_busy_retry_redaction_poll_dedup_and_close(self):
        token = 'b' * 64; rid = 'c' * 32
        reply = {'state': 'answered', 'messages': [
            {'seq': 1, 'kind': 'text', 'body': 'hello\x1b[31m world\x07'},
            {'seq': 2, 'kind': 'command', 'body': 'touch /tmp/no'}]}
        c = self.client([(503, {'error': 'busy'}), (201, {'id': rid, 'client_token': token}),
                         (200, reply), (200, reply), (410, {'state': 'closed'}), (200, {})])
        c.help('3/10', 'J-UNK-00', 'alice@example.com', 'Bearer secretvalue\n/Users/alice/log', True)
        self.assertEqual(self.sleeps, [60, 20, 20])
        self.assertEqual([x for x in self.output if 'hello' in x], ['hello world'])
        self.assertFalse(any('touch' in x for x in self.output))
        sent = self.calls[0][2]
        self.assertNotIn('alice', json.dumps(sent)); self.assertNotIn('secretvalue', json.dumps(sent))
        self.assertIs(sent['notice_shown'], True)
        self.assertEqual(self.calls[0][4], 20)
        self.assertEqual([c[1] for c in self.calls[2:5]], ['/api/help/' + rid] * 3)
        self.assertTrue(all(c[3] == token for c in self.calls[2:]))
        self.assertEqual(self.calls[-1][1], '/api/help/' + rid + '/close')
        self.assertNotIn(token, ''.join(self.output))

    def test_busy_retry_only_once(self):
        c = self.client([(503, {}), (503, {})])
        c.help('1/10', 'J-UNK-00', '', '', True)
        self.assertEqual(len(self.calls), 2); self.assertEqual(self.sleeps, [60])

    def test_invalid_receipt_or_failure_never_polls(self):
        for response in ((201, {'id': '../bad', 'client_token': 'x'}), (201, {'id': 'c' * 32, 'client_token': 'B' * 64}),
                         (500, {}), (302, {}), OSError('down')):
            c = self.client([response])
            c.help('1/10', 'J-UNK-00', '', '', True)
            self.assertEqual(len(self.calls), 1)

    def test_non_interactive_submits_and_returns_without_waiting(self):
        c = self.client([(201, {'id': 'c' * 32, 'client_token': 'b' * 64})])
        c.help('1/10', 'J-UNK-00', '', '', False)
        self.assertEqual(len(self.calls), 1); self.assertEqual(self.sleeps, [])

    def test_poll_stops_at_deadline_and_on_404_and_close_failure_is_swallowed(self):
        ok = (201, {'id': 'c' * 32, 'client_token': 'b' * 64})
        c = self.client([ok] + [(200, {'state': 'open', 'messages': []})] * 400 + [OSError('close down')])
        c.help('1/10', 'J-UNK-00', '', '', True)
        self.assertLessEqual(self.tick, 7200)
        self.assertEqual(set(self.sleeps), {20})
        self.assertEqual(self.calls[-1][1].split('/')[-1], 'close')
        c = self.client([ok, (404, {}), (200, {})])
        c.help('1/10', 'J-UNK-00', '', '', True)
        self.assertEqual(len([x for x in self.calls if x[0] == 'GET']), 1)

    def test_payload_byte_limits_after_redaction(self):
        c = self.client([(500, {})])
        c.help('1/10', 'J-UNK-00', '한' * 100000, '줄\n' * 100000, False)
        payload = self.calls[0][2]
        self.assertLessEqual(len(payload['env_report'].encode()), 96 * 1024)
        self.assertLessEqual(len(payload['log_tail'].encode()), 128 * 1024)
        self.assertLessEqual(len(payload['log_tail'].splitlines()), 40)
        self.assertLessEqual(len(json.dumps(payload).encode()), 4 * 1024 * 1024)
        self.assertNotIn('attachments', payload)

    def test_base_url_must_be_https(self):
        import install_help_client as m
        for bad in ('http://example.test', 'file:///etc', 'ftp://x'):
            with self.assertRaises(ValueError):
                m.HelpClient(bad, 'a' * 32, '9.9.9', notice=True)

    def test_real_transport_blocks_redirects_and_caps_response(self):
        import install_help_client as m
        handler = m._NoRedirect()
        req = urllib.request.Request('https://example.test/api/help')
        self.assertIsNone(handler.redirect_request(req, None, 302, 'Found', {}, 'https://evil.test/'))
        self.assertEqual(m._read_capped(io.BytesIO(b'{"a":1}'), 64), {'a': 1})
        with self.assertRaises(ValueError):
            m._read_capped(io.BytesIO(b'x' * 65), 64)

    def test_cli_disabled_by_no_progress_and_without_notice(self):
        with tempfile.TemporaryDirectory() as td:
            env = dict(os.environ, HOME=td, WAVE_HOME=str(Path(td) / '.wave'),
                       WAVE_HELP_BASE_URL='https://127.0.0.1:1', WAVE_NO_PROGRESS='1')
            cmd = [sys.executable, str(ROOT / 'lib/install_help_client.py'), 'progress', '--notice-shown',
                   '--version', '9.9.9', '--step', '1/10', '--event', 'start']
            r = subprocess.run(cmd, env=env, capture_output=True, text=True, timeout=10)
            self.assertEqual((r.returncode, r.stdout, r.stderr), (0, '', ''))
            self.assertFalse((Path(td) / '.wave/install-id.txt').exists())
            env['WAVE_NO_PROGRESS'] = '0'
            r = subprocess.run(cmd[:3] + cmd[4:], env=env, capture_output=True, text=True, timeout=10)
            self.assertEqual((r.returncode, r.stdout, r.stderr), (0, '', ''))

    def test_notice_text_is_shared_and_covers_what_why_retention(self):
        text = (ROOT / 'lib/help-notice.txt').read_text(encoding='utf-8')
        for needle in ('보내는 것', '이유', '30일', 'WAVE_NO_PROGRESS=1'):
            self.assertIn(needle, text)


if __name__ == '__main__':
    unittest.main()
