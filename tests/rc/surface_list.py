#!/usr/bin/env python3
"""데몬에 surface.list 원본 요청 1줄을 보내 응답 원문을 증거로 남긴다(판정 입력 아님 · 수집 실패가 잡을 죽이지 않는다 — 항상 exit 0).
  surface_list.py <출력 파일>      성공: <출력 파일>=응답 한 줄 원문 · 실패: <출력 파일>.error=사유
소켓: CYS_SOCKET → (윈도우) \\\\.\\pipe\\cys · (맥·리눅스) ~/.local/state/cys/cys.sock — 앱 cys::socket_path() 와 같은 기본값.
요청: {"id":1,"method":"surface.list","params":{}} + 개행. 윈도우 파이프 경로는 이 환경에서 실행해 보지 못했다(맥 소켓만 실측)."""
import json, os, socket, sys, time

REQ = (json.dumps({"id": 1, "method": "surface.list", "params": {}}) + "\n").encode()

def path():
    p = os.environ.get("CYS_SOCKET")
    if p: return os.path.expanduser(p)
    return r"\\.\pipe\cys" if os.name == "nt" else os.path.expanduser("~/.local/state/cys/cys.sock")

def fetch(p, timeout=10):
    if os.name == "nt":
        for _ in range(10):   # ERROR_PIPE_BUSY(231) 은 데몬 다운이 아니라 순간 혼잡 — 잠깐 기다려 다시
            try: f = open(p, "r+b", buffering=0); break
            except OSError as e:
                if getattr(e, "winerror", 0) != 231: raise
                time.sleep(0.5)
        else: raise OSError("pipe busy")
        with f:
            f.write(REQ); return f.readline()
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM); s.settimeout(timeout); s.connect(p); s.sendall(REQ); buf = b""
    while not buf.endswith(b"\n"):
        c = s.recv(65536)
        if not c: break
        buf += c
    s.close(); return buf

if __name__ == "__main__":
    out = sys.argv[1]
    try:
        raw = fetch(path())
        if not raw.strip(): raise ValueError("빈 응답")
        open(out, "wb").write(raw)
    except Exception as e:
        try: open(out + ".error", "w", encoding="utf-8").write("%s: %s\n" % (type(e).__name__, e))
        except Exception: pass
    sys.exit(0)
