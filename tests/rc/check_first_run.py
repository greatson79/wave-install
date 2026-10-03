#!/usr/bin/env python3
"""첫 설치 실행이 정말 성공했는지 단정한다 — 종료값 0 이어야 하고, 단계 기록 S07·S08·S09 가 failed 이면 안 되며, 「세 칸 생존 · 확인 미완」(fleet_state=alive_unconfirmed)도 통과가 아니다.
  check_first_run.py <종료값 파일> <install-state.json>      종료값 0 = 성공 확인 · 1 = 실패(또는 증거 없음) — 수치는 잡 로그에 한 줄로 남긴다
판정기(gate.py)는 G1 에서 S07~S09 를 안 보므로(CI_STEPS) 이 검사가 러너 쪽 안전망이다. 합성 Claude 는 표지를 쓰므로 정상 잡은 반드시 통과해야 한다(통과 못 하면 그것이 결함).
부트 점검을 건너뛰는 가짜 Claude 잡(noboot)은 이 검사 대상이 아니다 — 그쪽은 check_noboot.py(기대 종료값 2)."""
import json, sys
GATED = ("S07", "S08", "S09")

def judge(exit_file, state_file):
    try: code = int(open(exit_file, encoding="utf-8-sig").read().strip())
    except (OSError, ValueError): return 1, "증거 없음: " + exit_file
    try: steps = json.load(open(state_file, encoding="utf-8-sig"))["steps"]; s07 = next(v for k, v in steps.items() if k[:3] == "S07")
    except (OSError, ValueError, KeyError, TypeError, StopIteration): return 1, "증거 없음·형식 오류: %s steps.S07" % state_file
    obs = s07.get("observed") or {}
    st = {k[:3]: v.get("status") for k, v in steps.items() if k[:3] in GATED}
    line = "exit=%d %s fleet_state=%s" % (code, " ".join("%s=%s" % kv for kv in sorted(st.items())), obs.get("fleet_state"))
    if code != 0: return 1, "첫 설치 종료값이 0 이 아님: " + line
    if any(v == "failed" for v in st.values()): return 1, "S07·S08·S09 중 failed: " + line
    if obs.get("fleet_state") == "alive_unconfirmed": return 1, "확인 미완이 PASS 로 샘: " + line
    return 0, line

if __name__ == "__main__":
    rc, msg = judge(sys.argv[1], sys.argv[2]); print("[first-run] %s (rc=%d)" % (msg, rc)); sys.exit(rc)
