#!/usr/bin/env python3
"""시험 서버 — 폴더를 https 로 서빙(자체서명 인증서는 러너 안에서 만든 것). serve_https.py DIR PORT CERT KEY"""
import functools, http.server, ssl, sys
d, port, cert, key = sys.argv[1], int(sys.argv[2]), sys.argv[3], sys.argv[4]
h = functools.partial(http.server.SimpleHTTPRequestHandler, directory=d)
s = http.server.ThreadingHTTPServer(("127.0.0.1", port), h)
ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER); ctx.load_cert_chain(cert, key)
s.socket = ctx.wrap_socket(s.socket, server_side=True); s.serve_forever()
