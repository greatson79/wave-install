"""Portable checks of the fixture, not a substitute for Windows execution."""
import hashlib
import http.client
import socket
import threading
import unittest
import urllib.error
import urllib.request

from serve_fixture import BOM, EXPECTED_SHA, PAYLOAD, FixtureServer, bootstrap, stub


class FixtureTests(unittest.TestCase):
    def setUp(self):
        self.server = FixtureServer()
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=3)
        self.assertFalse(self.thread.is_alive())
        with socket.socket() as client:
            self.assertNotEqual(client.connect_ex(self.server.server_address), 0)

    def fetch(self, path):
        return urllib.request.urlopen(self.server.base + path, timeout=3)

    def test_redirect_ascii_stub_and_bom_bootstrap(self):
        with self.fetch('/health') as result:
            self.assertEqual(result.read(), b'ready')
        with self.fetch('/win') as result:
            body = result.read()
            self.assertEqual(result.url, self.server.base + '/win-start.ps1')
        self.assertEqual(body, stub(self.server.base))
        self.assertTrue(body.isascii())
        self.assertFalse(body.startswith(BOM))
        self.assertIn(b'& powershell.exe -NoProfile -ExecutionPolicy Bypass -File $f', body)
        with self.fetch('/bootstrap.ps1') as result:
            script = result.read()
        self.assertTrue(script.startswith(BOM))
        self.assertIn("'한글 정상'", script.decode('utf-8-sig'))
        self.assertIn(EXPECTED_SHA.encode(), script)
        self.assertEqual([ord(c) for c in '한글 정상'], [54620, 44544, 32, 51221, 49345])

    def test_corrupt_changes_payload_only(self):
        original = bootstrap(self.server.base)
        with self.fetch('/payload') as result:
            self.assertEqual(result.read(), PAYLOAD)
        request = urllib.request.Request(self.server.base + '/corrupt', data=b'', method='POST')
        with urllib.request.urlopen(request, timeout=3) as result:
            self.assertEqual(result.status, 200)
        with self.fetch('/payload') as result:
            self.assertNotEqual(hashlib.sha256(result.read()).hexdigest(), EXPECTED_SHA)
        with self.fetch('/bootstrap.ps1') as result:
            self.assertEqual(result.read(), original)
        self.assertEqual(hashlib.sha256(PAYLOAD).hexdigest(), EXPECTED_SHA)

    def test_bootstrap_404(self):
        self.server.mode = 'bootstrap404'
        with self.assertRaises(urllib.error.HTTPError) as error:
            self.fetch('/bootstrap.ps1')
        self.assertEqual(error.exception.code, 404)
        error.exception.close()

    def test_interrupted_is_truncated_transfer(self):
        self.server.mode = 'interrupted'
        with self.fetch('/bootstrap.ps1') as result:
            with self.assertRaises(http.client.IncompleteRead):
                result.read()

    def test_child7_has_no_completion(self):
        self.server.mode = 'child7'
        with self.fetch('/bootstrap.ps1') as result:
            body = result.read()
        self.assertIn(b"'CHILD_EXIT_7'; exit 7", body)
        self.assertNotIn(b'FIXTURE_DONE', body)


class StubPinTests(unittest.TestCase):
    def test_download_hash_checked_before_child_execution(self):
        body = stub('http://127.0.0.1:12345')
        expected = hashlib.sha256(bootstrap('http://127.0.0.1:12345')).hexdigest().encode()
        self.assertIn(expected, body)
        self.assertLess(body.index(b'BOOTSTRAP_SHA_MISMATCH'), body.index(b'& powershell.exe'))
        self.assertNotEqual(hashlib.sha256(bootstrap('http://127.0.0.1:12345')[:8]).hexdigest().encode(), expected)

    def test_product_renderer_requires_https_and_bom(self):
        from render_win_start import render
        content = BOM + b"Write-Output 'fixture'"
        for url in ('http://example.com/bootstrap.ps1', "https://example.com/a'b", 'https://example.com/a\n'):
            with self.assertRaises(ValueError):
                render(content, url)
        with self.assertRaises(ValueError):
            render(b'no-bom', 'https://example.com/bootstrap.ps1')
        result = render(content, 'https://example.com/releases/v1/bootstrap.ps1')
        self.assertTrue(result.isascii())
        self.assertIn(hashlib.sha256(content).hexdigest().encode(), result)


if __name__ == '__main__':
    unittest.main(verbosity=2)
