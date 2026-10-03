"""윈 짧은 한 줄 stub(win-start.ps1) — 자식 설치기 종료값 0/2/1/7 에 따른 화면 글자·종료값 전달을 PowerShell 로 실제 실행해 단정한다.
가짜 powershell.exe(sh)가 받은 -File 안의 EXIT=N 대로 끝난다. PWSH 환경변수(기본 /tmp/wave-v024-pwsh/pwsh)가 없으면 건너뜀. 실행: python3 -m unittest tests.rc.test_win_start_stub"""
import os, pathlib, subprocess, sys, tempfile, threading, unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1] / "scripts"))
import render_win_start
PWSH = os.environ.get("PWSH", "/tmp/wave-v024-pwsh/pwsh")

class Quiet(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def do_GET(self):
        body = self.server.files.get(self.path)
        self.send_response(200 if body is not None else 404); self.end_headers()
        if body is not None: self.wfile.write(body)

@unittest.skipUnless(os.path.exists(PWSH) and os.name != "nt", "pwsh 없음")
class WinStartStub(unittest.TestCase):
    def run_stub(self, code):
        with tempfile.TemporaryDirectory() as d:
            bs = ("﻿# fake installer\nEXIT=%d\n" % code).encode("utf-8")
            srv = ThreadingHTTPServer(("127.0.0.1", 0), Quiet); base = "http://127.0.0.1:%d" % srv.server_address[1]
            srv.files = {"/bootstrap.ps1": bs, "/win-start.ps1": render_win_start.render(bs, base + "/bootstrap.ps1", fixture=True)}
            threading.Thread(target=srv.serve_forever, daemon=True).start()
            bindir = pathlib.Path(d) / "bin"; bindir.mkdir()
            fake = bindir / "powershell.exe"   # -File <경로> 를 찾아 그 안의 EXIT=N 으로 종료
            fake.write_text('#!/bin/sh\nwhile [ $# -gt 0 ]; do [ "$1" = -File ] && f="$2"; shift; done\nexit "$(sed -n \'s/^EXIT=//p\' "$f")"\n'); fake.chmod(0o755)
            env = dict(os.environ, PATH=str(bindir) + os.pathsep + os.environ["PATH"], HOME=d, TMPDIR=d)
            try:
                r = subprocess.run([PWSH, "-NoProfile", "-Command", "irm %s/win-start.ps1 | iex; 'LAST=' + $LASTEXITCODE" % base], env=env, capture_output=True, text=True, timeout=120)
            finally: srv.shutdown(); srv.server_close()
            leftovers = [p for p in pathlib.Path(d).glob("wave-start-*")]
            return r.returncode, r.stdout + r.stderr, leftovers
    def test_exit_0_is_silent_success(self):
        rc, out, left = self.run_stub(0)
        self.assertEqual(rc, 0, out); self.assertIn("LAST=0", out); self.assertNotIn("failed", out.lower()); self.assertEqual(left, [])
    def test_exit_2_ends_without_error_or_failed_and_keeps_the_code(self):
        rc, out, left = self.run_stub(2)
        self.assertEqual(rc, 0, out)   # 호출 창은 안 닫히고 오류도 없다(exit 를 쓰지 않는다)
        self.assertIn("LAST=2", out); self.assertNotIn("failed", out.lower()); self.assertNotIn("exception", out.lower()); self.assertNotIn("error", out.lower()); self.assertEqual(left, [])
    def test_other_nonzero_codes_still_show_failure(self):
        for code in (1, 7):
            rc, out, left = self.run_stub(code)
            self.assertIn("Wave installer failed (exit %d)." % code, out); self.assertNotEqual(rc, 0, out); self.assertEqual(left, [])   # throw 는 호출 스크립트를 중단한다(종전 동작)

if __name__ == "__main__": unittest.main()
