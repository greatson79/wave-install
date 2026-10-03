#!/usr/bin/env python3
"""첫 설치 실행의 종료값·S07 관측값을 잡 로그에 남기고, 「세 칸 생존 · 확인 미완」(종료값 2 · fleet_state=alive_unconfirmed)이 PASS 로 새지 않게 막는다.
  check_first_run.py <종료값 파일> <install-state.json>      종료값 0 = 새지 않음 · 1 = 샘(또는 증거 없음)
판정기(gate.py)는 G1 에서 S07 을 안 보므로(CI_STEPS) 이 검사가 러너 쪽 안전망이다."""
import json, sys

def judge(exit_file, state_file):
    try: code = int(open(exit_file, encoding="utf-8-sig").read().strip())
    except (OSError, ValueError): return 1, "증거 없음: " + exit_file
    try: s07 = json.load(open(state_file, encoding="utf-8-sig"))["steps"]["S07_INITIAL_FLEET"]
    except (OSError, ValueError, KeyError, TypeError): return 1, "증거 없음·형식 오류: %s steps.S07_INITIAL_FLEET" % state_file
    obs = s07.get("observed") or {}
    line = "exit=%d S07=%s fleet_state=%s fleet_started=%s" % (code, s07.get("status"), obs.get("fleet_state"), obs.get("fleet_started"))
    if code == 2 or obs.get("fleet_state") == "alive_unconfirmed": return 1, "확인 미완이 PASS 로 샘: " + line
    return 0, line

if __name__ == "__main__":
    rc, msg = judge(sys.argv[1], sys.argv[2]); print("[first-run] %s (rc=%d)" % (msg, rc)); sys.exit(rc)
