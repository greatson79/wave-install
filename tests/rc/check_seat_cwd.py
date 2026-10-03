#!/usr/bin/env python3
"""홈 아닌 폴더에서 설치기를 시작해도 세 좌석(master·cso·worker)의 cwd 가 사용자 홈인지 단정한다(rc4 회귀 감시 · 테오 2238 / 펄스 0105).
  check_seat_cwd.py <홈 경로 | identity.json(profile)> <cys status --json 증거> [더 많은 증거 …]
종료값 0 = 모든 증거에서 살아 있는 세 역할 좌석 cwd == 홈 · 1 = 하나라도 다르거나 좌석이 없거나 증거 없음."""
import json, os, sys

def norm(p): return str(p).rstrip("\\/").replace("\\", "/").casefold()

def judge(home, files):
    if home.endswith(".json"):
        try: home = json.load(open(home, encoding="utf-8-sig"))["profile"]
        except (OSError, ValueError, KeyError): return 1, "홈 경로를 못 읽음: " + home
    bad, lines = [], []
    for f in files:
        try: seats = [s for s in json.load(open(f, encoding="utf-8-sig"))["surfaces"] if s.get("exited") is False and str(s.get("role") or "").split("-")[0] in ("master", "cso", "worker")]
        except (OSError, ValueError, KeyError, TypeError): bad.append("증거 없음·형식 오류: " + f); continue
        roles = sorted({str(s["role"]).split("-")[0] for s in seats})
        if roles != ["cso", "master", "worker"]: bad.append("%s: 좌석 역할 %s (세 칸 기대)" % (os.path.basename(f), roles)); continue
        off = ["%s=%s" % (s["role"], s.get("cwd")) for s in seats if norm(s.get("cwd")) != norm(home)]
        if off: bad.append("%s: 홈(%s)이 아닌 cwd — %s" % (os.path.basename(f), home, ", ".join(off)))
        else: lines.append("%s: 세 좌석 cwd = 홈" % os.path.basename(f))
    return (1, "; ".join(bad)) if bad else (0, "; ".join(lines))

if __name__ == "__main__":
    rc, msg = judge(sys.argv[1], sys.argv[2:]); print("[seat-cwd] %s (rc=%d)" % (msg, rc)); sys.exit(rc)
