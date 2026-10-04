#!/usr/bin/env python3
"""G9 실기 증거(real/*.json) — 설치기 종료값·fleet_state 를 반드시 담는다(실기 증거 계약). 판정기(gate.py)는 이 두 칸을 읽지 않으므로 이 도구가 만들 때·검사할 때 막는다.
  real_evidence.py make --os mac|win --exit N --seats master,cso,worker --login-approve N [--other N] --wave-home ~/.wave --out <real 폴더>
      → <real>/<os>.json + <real>/raw/<os>_install-state.json(원본 사본 · sha256 raw 로 묶음). 기록은 있는 그대로(종료값 2 면 2 로 남는다).
  real_evidence.py check <real 폴더>      → 실기 문서(os 필드)가 1개 이상 있고 모두 installer_exit(정수)==0 ∧ fleet_state 가 있고 alive_unconfirmed·unknown 이 아닐 때만 0 (아니면 1)"""
import argparse, glob, hashlib, json, os, shutil, sys

def fleet_state(state):
    try: obs = state["steps"]["S07_INITIAL_FLEET"]["observed"] or {}
    except (KeyError, TypeError): return "unknown"
    return obs.get("fleet_state") or ("started" if obs.get("fleet_started") is True else "unknown")

def make(a):
    os.makedirs(os.path.join(a.out, "raw"), exist_ok=True)   # gate.py 는 real/*.json 전부를 문서로 읽으므로 원본 사본은 하위 폴더에 둔다
    src = os.path.join(os.path.expanduser(a.wave_home), "install-state.json")
    raw = "raw/%s_install-state.json" % a.os; shutil.copy2(src, os.path.join(a.out, raw))
    state = json.load(open(src, encoding="utf-8-sig"))
    doc = {"os": a.os, "seats": a.seats.split(","), "human_hands": {"login_approve": a.login_approve, "other": a.other},
           "installer_exit": a.exit, "fleet_state": fleet_state(state),
           "raw": [{"path": raw, "sha256": hashlib.sha256(open(os.path.join(a.out, raw), "rb").read()).hexdigest()}]}
    json.dump(doc, open(os.path.join(a.out, "%s.json" % a.os), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("[real] %s installer_exit=%d fleet_state=%s" % (a.os, a.exit, doc["fleet_state"]))

def check(folder):
    bad, real = [], 0
    for p in sorted(glob.glob(os.path.join(folder, "*.json"))):
        d = json.load(open(p, encoding="utf-8-sig"))
        if d.get("os") is None: continue   # 실기 문서가 아닌 파일은 건너뜀
        real += 1; n = os.path.basename(p)
        if not isinstance(d.get("installer_exit"), int) or isinstance(d.get("installer_exit"), bool) or not d.get("fleet_state"):
            bad.append("%s: installer_exit·fleet_state 없음" % n)
        elif d["installer_exit"] != 0 or d["fleet_state"] in ("alive_unconfirmed", "unknown"):   # unknown = 상태 파일에서 못 읽음 — 통과로 치지 않는다
            bad.append("%s: installer_exit=%s fleet_state=%s" % (n, d["installer_exit"], d["fleet_state"]))
    if not real: bad.append("실기 문서(os 필드가 있는 *.json) 0개")   # 폴더에 다른 JSON 만 있어도 통과시키지 않는다
    for m in bad: print("[real] FAIL " + m)
    return 1 if bad else 0

if __name__ == "__main__":
    ap = argparse.ArgumentParser(); sub = ap.add_subparsers(dest="cmd", required=True)
    m = sub.add_parser("make"); m.add_argument("--os", required=True, choices=["mac", "win"]); m.add_argument("--exit", type=int, required=True)
    m.add_argument("--seats", required=True); m.add_argument("--login-approve", type=int, required=True); m.add_argument("--other", type=int, default=0)
    m.add_argument("--wave-home", default="~/.wave"); m.add_argument("--out", required=True)
    c = sub.add_parser("check"); c.add_argument("folder")
    a = ap.parse_args()
    if a.cmd == "make": make(a)
    else: sys.exit(check(a.folder))
