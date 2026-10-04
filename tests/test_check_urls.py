"""scripts/ci/check-urls.py 시험: 주소 추출 · 게시 전/후 두 방식의 404 판정 · 종료값 · 실제 로컬 서버를 거친 CLI. 네트워크(실서버)는 쓰지 않는다."""
import importlib.util
import io
import json
import subprocess
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/ci/check-urls.py"
spec = importlib.util.spec_from_file_location("check_urls", SCRIPT)
cu = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cu)

PENDING = "https://github.com/o/r/releases/download/v9.9.9-rc.1/app.dmg"
GONE = "https://github.com/o/r/releases/download/v0.3.0/bootstrap.sh"
LIVE = "https://waveainetworks.com/mac"


def fake(codes):
    return lambda url: codes.get(url, 200)


def run(files_text, codes, tags=()):
    with tempfile.TemporaryDirectory() as td:
        for name, text in files_text.items():
            (Path(td) / name).write_text(text, encoding="utf-8")
        out = io.StringIO()
        rc = cu.run(list(files_text), fetch=fake(codes), tags=tags, root=td, out=out)
        return rc, out.getvalue()


class Extract(unittest.TestCase):
    def test_urls_stop_at_quotes_brackets_backslashes_and_trailing_punctuation(self):
        text = 'a "https://a.test/x" b [t](https://b.test/y). c \'https://c.test/z\' d \\"https://d.test/w\\" e `https://e.test/v`, <https://f.test/u>'
        self.assertEqual([u for _, u in cu.extract_urls(text)], ["https://a.test/x", "https://b.test/y", "https://c.test/z", "https://d.test/w", "https://e.test/v", "https://f.test/u"])

    def test_loopback_is_skipped_unless_asked(self):
        with tempfile.TemporaryDirectory() as td:
            (Path(td) / "f.md").write_text("http://127.0.0.1:9/x https://ok.test/", encoding="utf-8")
            self.assertEqual(list(cu.collect(["f.md"], td)), ["https://ok.test/"])
            self.assertEqual(len(cu.collect(["f.md"], td, include_loopback=True)), 2)

    def test_default_files_cover_steps_readme_and_site_copy(self):
        where = cu.collect(cu.DEFAULT_FILES)
        files = {p.split(":")[0] for places in where.values() for p in places}
        self.assertTrue({"steps.json", "README.md", "site/index.html", "site/steps.json"} <= files, files)


class Modes(unittest.TestCase):
    TEXT = {"steps.json": json.dumps({"a": PENDING, "b": LIVE}), "README.md": "ok " + LIVE}

    def test_before_publish_pending_tag_404_is_an_exception_not_a_failure(self):
        rc, out = run(self.TEXT, {PENDING: 404}, tags=("v9.9.9-rc.1",))
        self.assertEqual(rc, 0, out)
        self.assertIn("404 | 예외 |", out)
        self.assertIn("예외(게시 전 대기 태그) 1개", out)

    def test_after_publish_the_same_404_fails(self):
        rc, out = run(self.TEXT, {PENDING: 404})
        self.assertEqual(rc, 1, out)
        self.assertIn("404 | 404 |", out)

    def test_any_other_404_fails_even_before_publish(self):
        rc, out = run({"README.md": GONE + " " + PENDING}, {PENDING: 404, GONE: 404}, tags=("v9.9.9-rc.1",))
        self.assertEqual(rc, 1, out)
        self.assertIn(GONE, out.split("합계")[0].split("404 | 404 |")[1])

    def test_exception_is_by_tag_only(self):
        rc, _ = run({"README.md": PENDING}, {PENDING: 404}, tags=("v0.3.0-rc.5",))
        self.assertEqual(rc, 1)

    def test_published_pending_url_is_reported_as_already_published(self):
        rc, out = run(self.TEXT, {}, tags=("v9.9.9-rc.1",))
        self.assertEqual(rc, 0, out)
        self.assertIn("OK(이미 게시됨)", out)

    def test_unmeasured_is_not_a_pass(self):
        rc, out = run({"README.md": LIVE}, {LIVE: None})
        self.assertEqual(rc, 3, out)

    def test_gone_410_counts_as_missing(self):
        rc, _ = run({"README.md": LIVE}, {LIVE: 410})
        self.assertEqual(rc, 1)


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a): pass

    def do_HEAD(self):
        self.send_response(404 if self.path.startswith("/missing") else 405 if self.path == "/head-blocked" else 200); self.end_headers()

    def do_GET(self):
        self.send_response(404 if self.path.startswith("/missing") else 200); self.send_header("Content-Length", "0"); self.end_headers()


class Cli(unittest.TestCase):
    def setUp(self):
        self.srv = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        self.addCleanup(self.srv.server_close); self.addCleanup(self.srv.shutdown)
        self.base = "http://127.0.0.1:%d" % self.srv.server_address[1]

    def cli(self, text, *flags):
        with tempfile.TemporaryDirectory() as td:
            (Path(td) / "f.md").write_text(text, encoding="utf-8")
            return subprocess.run([sys.executable, str(SCRIPT), *flags, "--files", "f.md", "--root", td, "--include-loopback"], capture_output=True, text=True)

    def test_real_http_200_head_blocked_and_404(self):
        ok = self.cli("%s/a %s/head-blocked" % (self.base, self.base), "--after-publish")
        self.assertEqual(ok.returncode, 0, ok.stdout + ok.stderr)
        bad = self.cli("%s/a %s/missing/x" % (self.base, self.base), "--after-publish")
        self.assertEqual(bad.returncode, 1, bad.stdout)
        self.assertIn("404 | 404 | %s/missing/x | f.md:1" % self.base, bad.stdout)

    def test_pending_tag_mode_over_http(self):
        text = "%s/missing/releases/download/v1.2.3-rc.9/a.dmg" % self.base
        self.assertEqual(self.cli(text, "--pending-tag", "v1.2.3-rc.9").returncode, 0)
        self.assertEqual(self.cli(text, "--after-publish").returncode, 1)

    def test_mode_flag_is_required(self):
        r = self.cli("x")
        self.assertEqual(r.returncode, 2)


if __name__ == "__main__":
    unittest.main()
