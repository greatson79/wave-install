#!/usr/bin/env python3
"""「부트 점검을 건너뛰는 가짜 Claude」 잡 판정 — check_noboot.py <증거 폴더> [기대값.json]
증거 폴더에 exit(설치기 종료값)·run.log·marker_absent(표지 없음 확인)·install-state.json 이 있어야 한다. 기대값은 rc4-expect.json 한 곳(잡 기대값 정본).
종료값: 0 통과 · 1 실패(기대와 다름·exit 1·증거 없음) · 3 기대값 미정(통과로 치지 않는다)."""
import json, os, sys
STEP = "S07_INITIAL_FLEET"

def judge(ev, expect_path):
    exp = json.load(open(expect_path, encoding="utf-8"))
    want, code = exp.get("unconfirmed_exit"), exp.get("diag_code")
    if want is None: return 3, "기대 종료값 미정(rc4-expect.json unconfirmed_exit) — 판정 보류"
    try: got = int(open(os.path.join(ev, "exit"), encoding="utf-8").read().strip())
    except (OSError, ValueError): return 1, "증거 없음: exit"
    if not os.path.exists(os.path.join(ev, "marker_absent")): return 1, "표지가 있었다 — 가짜 Claude 가 부트를 건너뛰지 못함(시험 무효)"
    if got == 1: return 1, "설치기 exit 1 = 실패"
    shown = "".join(open(os.path.join(ev, f), encoding="utf-8", errors="replace").read() for f in ("run.log", "run.log.err") if os.path.exists(os.path.join(ev, f)))
    if "Wave installer failed" in shown: return 1, "짧은 한 줄 stub 이 종료값 %d 를 「failed」로 표시함(실패 아님 안내여야 함)" % got   # 윈 stub(win-start.ps1) 경유 화면 단정
    if got != want: return 1, "종료값 %d != 기대 %d" % (got, want)
    if code:
        text = "".join(open(os.path.join(ev, f), encoding="utf-8", errors="replace").read() for f in ("run.log", "install.log") if os.path.exists(os.path.join(ev, f)))
        if code not in text: return 1, "진단 코드 %s 가 로그에 없음" % code
    obs = exp.get("observed")
    if obs:  # 종료값만이 아니라 install-state 의 S07 관측값(세 칸 생존 · 확인 미완)까지 대조
        try: seen = json.load(open(os.path.join(ev, "install-state.json"), encoding="utf-8-sig"))["steps"][STEP]["observed"]
        except (OSError, ValueError, KeyError, TypeError): return 1, "증거 없음·형식 오류: install-state.json steps.%s.observed" % STEP
        bad = ["%s=%r(기대 %r)" % (k, seen.get(k), v) for k, v in obs.items() if seen.get(k) != v]
        if bad: return 1, "관측값 불일치: " + ", ".join(bad)
    return 0, "종료값 %d%s 확인" % (got, " · 진단 코드 " + code if code else "")

if __name__ == "__main__":
    rc, msg = judge(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else os.path.join(os.path.dirname(os.path.abspath(__file__)), "rc4-expect.json"))
    print("[noboot] %s (rc=%d)" % (msg, rc)); sys.exit(rc)
