#!/usr/bin/env python3
"""제한 시간 실행 — run_to.py SECONDS LOGFILE -- CMD... : stdin 은 닫고(로그인 대기 방지), 시간 초과 시 프로세스 그룹째 종료하고 exit 124.
출력은 LOGFILE 로 가고 마지막 40줄만 콘솔에 보여 준다."""
import os, signal, subprocess, sys
sec, log, cmd = int(sys.argv[1]), sys.argv[2], sys.argv[4:]
with open(log, "wb") as f:
    p = subprocess.Popen(cmd, stdin=subprocess.DEVNULL, stdout=f, stderr=subprocess.STDOUT, start_new_session=(os.name != "nt"))
    try: rc = p.wait(timeout=sec)
    except subprocess.TimeoutExpired:
        (os.killpg(p.pid, signal.SIGKILL) if os.name != "nt" else p.kill()); p.wait(); rc = 124
tail = open(log, "rb").read().decode("utf-8", "replace").splitlines()[-40:]
print("\n".join(tail)); print("[run_to] exit=%d" % rc); sys.exit(rc)
