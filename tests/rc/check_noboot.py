#!/usr/bin/env python3
"""가짜 Claude 잡 판정: 스키마에 따라 종료값·상태 및 rc.5 raw status/S08 증거를 검사한다.
rc.4 고정본은 명시 선택하고 CI는 rc-inputs.json 선언을 따른다."""
import json, os, sys
from pathlib import Path
STEP = "S07_INITIAL_FLEET"

def judge(ev, expect_path, schema):
    exp = json.load(open(expect_path, encoding="utf-8"))
    if schema == "rc5":
        if exp.get("s07_schema") != "rc5": return 1, "rc.5 스키마 기대값 선언 없음"
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import install_outcomes
        folder = Path(ev)
        verdict, reason = install_outcomes.check(folder.parents[1], folder.parent.name, "noboot", schema="rc5")
        return (0 if verdict == "PASS" else 1), reason
    if schema != "rc4": return 1, "지원하지 않는 스키마: " + str(schema)
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
    declared = json.loads(Path(__file__).with_name("rc-inputs.json").read_text(encoding="utf-8"))["s07_schema"]
    schema = sys.argv[3] if len(sys.argv) > 3 else declared
    if schema != declared:
        print("[noboot] 러너 입력 스키마와 불일치: %s (rc-inputs.json=%s)" % (schema, declared)); sys.exit(1)
    default_expect = "install-outcome-expect-rc5.json" if schema == "rc5" else "rc4-expect.json"
    expect_path = sys.argv[2] if len(sys.argv) > 2 else str(Path(__file__).with_name(default_expect))
    rc, msg = judge(sys.argv[1], expect_path, schema=schema)
    print("[noboot] %s (rc=%d)" % (msg, rc)); sys.exit(rc)
