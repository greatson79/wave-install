#!/usr/bin/env python3
"""시험 서버 — 폴더를 https 로 서빙(자체서명 인증서는 러너 안에서 만든 것). serve_https.py DIR PORT CERT KEY
RC_HELP_LOG 가 있으면 도움 요청 API 를 흉내 낸다(윈 Ctrl+C 측정용): POST /api/help → 201, GET /api/help/<id> → 200(빈 메시지), POST /api/help/<id>/close → 200, /api/progress → 200.
요청 한 줄씩 RC_HELP_LOG 에 남긴다 — 폴링(GET) 줄이 있으면 설치기가 대화형 대기 루프에 들어갔다는 뜻이고, close 줄은 finally 가 실행됐다는 뜻이다."""
import functools, http.server, json, os, ssl, sys, time
d, port, cert, key = sys.argv[1], int(sys.argv[2]), sys.argv[3], sys.argv[4]
LOG = os.environ.get("RC_HELP_LOG")
RID, TOKEN = "a" * 32, "b" * 64

class H(http.server.SimpleHTTPRequestHandler):
    def _help(self):
        n = int(self.headers.get("Content-Length") or 0)
        if n: self.rfile.read(n)
        with open(LOG, "a", encoding="utf-8") as f: f.write("%.2f %s %s\n" % (time.time(), self.command, self.path))
        code, body = 200, {}
        if self.command == "POST" and self.path == "/api/help": code, body = 201, {"id": RID, "client_token": TOKEN}
        elif self.command == "GET" and self.path.startswith("/api/help/"): body = {"messages": []}
        data = json.dumps(body).encode()
        self.send_response(code); self.send_header("Content-Type", "application/json"); self.send_header("Content-Length", str(len(data))); self.end_headers(); self.wfile.write(data)
    def do_POST(self):
        if LOG and self.path.startswith("/api/"): return self._help()
        self.send_error(404)
    def do_GET(self):
        if LOG and self.path.startswith("/api/"): return self._help()
        super().do_GET()

h = functools.partial(H, directory=d)
s = http.server.ThreadingHTTPServer(("127.0.0.1", port), h)
ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER); ctx.load_cert_chain(cert, key)
s.socket = ctx.wrap_socket(s.socket, server_side=True); s.serve_forever()
