#!/usr/bin/env python3
"""CI 용 로컬 시험 서버: 수강생 설치 한 줄(scripts/ci/install-lines.json 의 win)이 받는 /win 을 게시 서버와 같은 모양으로 흉내 낸다.
/win -> 307 -> /win-start.ps1(저장소 bootstrap.ps1 의 BOM 바이트에 SHA 를 묶은 stub) · 그 밖의 경로는 저장소 루트 정적 파일.
사용: oneline-local.py PORT   (127.0.0.1 전용 · 프로세스를 종료할 때까지 서빙)"""
import functools, http.server, json, pathlib, sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
import render_win_start

port = int(sys.argv[1])
base = "http://127.0.0.1:%d" % port
stub = render_win_start.render((ROOT / "bootstrap.ps1").read_bytes(), base + "/bootstrap.ps1", fixture=True)


class H(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/win":
            self.send_response(307); self.send_header("Location", "/win-start.ps1"); self.send_header("Content-Length", "0"); self.end_headers()
        elif self.path == "/win-start.ps1":
            self.send_response(200); self.send_header("Content-Length", str(len(stub))); self.end_headers(); self.wfile.write(stub)
        else:
            super().do_GET()


http.server.ThreadingHTTPServer(("127.0.0.1", port), functools.partial(H, directory=str(ROOT))).serve_forever()
