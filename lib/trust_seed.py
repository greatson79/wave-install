#!/usr/bin/env python3
"""Wave 좌석 Claude 설정 폴더에 첫 실행 질문 사전 설정을 건다(macOS S07 직전) — 지인 jarvis-install 과 같은 규칙.

  trust_seed.py seed <설정폴더> <기록파일.tsv> <작업폴더> <홈>
  trust_seed.py rollback <설정폴더> <기록파일.tsv> <작업폴더>

seed (oogisoogi/jarvis-install bootstrap.sh:2713-3002 profile_configs·seed_claude_prefs, df5efc8a, MIT,
LICENSES/jarvis-install-MIT.txt — 같은 규칙):
  - 설정폴더가 없으면 아무것도 쓰지 않는다(:2716 「있는 것만 쓴다」).
  - <설정폴더>/.claude.json: hasCompletedOnboarding = true(덮어씀 · :2879-2883) · projects 없으면 {} (:2885-2887)
    · projects.<작업폴더>.hasTrustDialogAccepted = true(칸을 만들거나 덮어씀 · :2897-2904)
    · projects.<홈>.hasTrustDialogAccepted = true — 그 키가 **없을 때만**(값이 false 여도 그대로 · :2905-2995)
    · fullscreenUpsellSeenCount = 99(덮어씀 · :2997-2998).
  - 우리가 넣은 홈 키만 기록파일에 「설정파일<탭>홈」 한 줄로 덧붙인다(:2921·:2950). 기록을 먼저 쓰고
    실패하면 홈 키는 넣지 않고 종료값 3(:2918-2926 마침표 홈 갈래와 같은 순서 → 단계 실패 J-PERM-01 :3011-3019).
  - 맥 원작에는 .claude.json 백업 사본이 없다(백업 사본은 윈도우 원작 ps1:3105-3108 만).
  Wave 고유(원작과 다른 유일한 의도적 차이 · 주인님 지시): <설정폴더>/settings.json 의 remoteControlAtStartup = true
    (원작 :2734-2735 는 false). 바꿨으면 「settings.json<탭>remoteControlAtStartup<탭>바꾸기 전 값(JSON 또는 absent)」을 같은 기록에 남긴다.
rollback (원작 reset-clean.sh:1684-1757 strip_trust_seed · :2095 작업폴더 칸 삭제와 같은 범위):
  - 기록된 홈 키는 값이 아직 true 일 때만 지우고, 칸이 비면 칸째 지운다. 작업폴더 칸은 통째로 지운다.
  - settings.json 줄은 값이 아직 true 일 때만 바꾸기 전 값으로 돌린다(absent 면 지운다).
  - 온보딩·fullscreenUpsellSeenCount 는 원작처럼 되돌리지 않는다. 끝나면 기록파일을 지운다.
"""
import json
import os
import sys
import tempfile

KEY = "hasTrustDialogAccepted"


def load(path):
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError("%s 최상위가 객체가 아님" % os.path.basename(path))
    return data


def write(path, data):
    if os.path.islink(path):
        raise ValueError("%s 가 바로가기(심볼릭 링크)라 손대지 않음" % os.path.basename(path))
    d = os.path.dirname(path) or "."
    mode = os.stat(path).st_mode & 0o777 if os.path.exists(path) else 0o600
    fd, tmp = tempfile.mkstemp(prefix=os.path.basename(path) + ".", dir=d)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
            f.write("\n")
        os.chmod(tmp, mode)
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


def entry(projects, d):
    e = projects.get(d)
    if e is not None and not isinstance(e, dict):
        raise ValueError("projects 의 폴더 칸이 객체가 아님")
    return e


def seed(config_dir, journal, work, home):
    if not os.path.isdir(config_dir):
        return 0, ["(Wave 좌석 Claude 설정 폴더가 아직 없어 사전 설정을 건너뜁니다.)"]
    cfg, sf = os.path.join(config_dir, ".claude.json"), os.path.join(config_dir, "settings.json")
    o, s = load(cfg), load(sf)
    o0, s0 = json.dumps(o), json.dumps(s)
    o = {} if o is None else o
    s = {} if s is None else s
    o["hasCompletedOnboarding"] = True
    p = o.setdefault("projects", {})
    if not isinstance(p, dict):
        raise ValueError("projects 가 객체가 아님")
    e = entry(p, work)
    if e is None:
        p[work] = {KEY: True}
    else:
        e[KEY] = True
    msgs = []
    e = entry(p, home)
    add_home = e is None or KEY not in e
    if not add_home:
        msgs.append("(이 컴퓨터에는 홈 폴더 신뢰 설정이 이미 있어 그대로 두었습니다 — 우리가 바꾸지 않습니다.)")
    o["fullscreenUpsellSeenCount"] = 99
    prior = s.get("remoteControlAtStartup", "absent")
    rows = ["%s\t%s\n" % (cfg, home)] if add_home else []
    if prior is not True:
        rows.append("%s\tremoteControlAtStartup\t%s\n" % (sf, prior if prior == "absent" else json.dumps(prior)))
    rc = 0
    if rows:
        try:  # 기록이 먼저 선다 — 기록 없이 넣지 않는다(원작 :2918-2926)
            os.makedirs(os.path.dirname(journal) or ".", exist_ok=True)
            with open(journal, "a", encoding="utf-8") as f:
                f.write("".join(rows))
        except OSError:
            rc = 3
            msgs.append("(홈 폴더 신뢰 기록을 남기지 못해 그 설정을 넣지 않았습니다 — 좌석이 폴더 신뢰를 한 번 물을 수 있습니다.)")
    if rc == 0:
        if add_home:
            p.setdefault(home, {})[KEY] = True
        if prior is not True:
            s["remoteControlAtStartup"] = True
        msgs.append("첫 실행 질문(테마·폴더 신뢰·큰 화면 권유)을 미리 넘겨 두었습니다.")
    if json.dumps(o) != o0:
        write(cfg, o)
    if s and json.dumps(s) != s0:
        write(sf, s)
    return rc, msgs


def rollback(config_dir, journal, work):
    rows = []
    if os.path.exists(journal):
        with open(journal, encoding="utf-8") as f:
            rows = [ln.rstrip("\n").split("\t") for ln in f if ln.strip()]
    files = {}
    cfg = os.path.join(config_dir, ".claude.json")
    for r in [[cfg, None]] + rows:
        if len(r) < 2 or not os.path.exists(r[0]):
            continue
        data = files.setdefault(r[0], load(r[0]))
        if r[1] is None:  # 작업폴더 칸 — 원작 reset-clean.sh:2095 처럼 통째로
            if isinstance(data.get("projects"), dict):
                data["projects"].pop(work, None)
        elif len(r) >= 3:  # settings.json remoteControlAtStartup
            if data.get(r[1]) is True:
                if r[2] == "absent":
                    del data[r[1]]
                else:
                    data[r[1]] = json.loads(r[2])
        else:
            e = data.get("projects", {}).get(r[1]) if isinstance(data.get("projects"), dict) else None
            if isinstance(e, dict) and e.get(KEY) is True:  # 우리가 넣은 값과 같을 때만
                del e[KEY]
                if not e:
                    del data["projects"][r[1]]
    for path, data in files.items():
        write(path, data)
    if os.path.exists(journal):
        os.unlink(journal)
    return "rolled back %d" % len(rows)


def main(argv):
    try:
        if len(argv) == 5 and argv[0] == "seed":
            rc, msgs = seed(*argv[1:])
            print("\n".join(msgs))
            return rc
        if len(argv) == 4 and argv[0] == "rollback":
            print(rollback(*argv[1:]))
            return 0
        print(__doc__, file=sys.stderr)
        return 2
    except (OSError, ValueError) as e:
        print("trust_seed: %s" % e, file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
