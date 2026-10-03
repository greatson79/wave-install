#!/usr/bin/env python3
"""Wave 전용 Claude 설정 폴더에 좌석 첫 실행 관문(온보딩·폴더 신뢰)을 미리 기록한다(macOS S07 직전).

  trust_seed.py seed <설정폴더> <기록파일> verified|unproven <폴더>...
      <설정폴더>/.claude.json: projects.<폴더>.hasTrustDialogAccepted = true · hasCompletedOnboarding = true(verified 일 때만)
  trust_seed.py rollback <기록파일>                     우리가 true 로 세운 칸만 바꾸기 전 값으로 되돌린다(그 뒤 사람이 바꾼 칸은 그대로)

좌석은 CLAUDE_CONFIG_DIR="${CYS_ACCOUNT_DIR:-$HOME/.cys/claude}" claude --dangerously-skip-permissions 로 뜨고,
Claude Code 는 그 폴더의 .claude.json 을 읽는다. 폴더 신뢰 창은 기본값이 「No, exit」 라
Return 한 번에 좌석이 죽는다. 사용자 ~/.claude·~/.claude.json 은 인자로 받지 않으므로 건드릴 수 없다.
Adapted from oogisoogi/jarvis-install bootstrap.sh:2711-3002 seed_claude_prefs/TRUST_SEED_FILE
(df5efc8a, MIT, LICENSES/jarvis-install-MIT.txt). 차이: Wave 전용 설정이라 false 도 true 로 세운다(Claude 가 새 폴더 칸을
false 로 만든다) — 바꾸기 전 값은 기록에 남겨 되돌릴 때 그대로 돌려놓는다.
hasCompletedOnboarding 은 로그인 관문까지 지운다(원작 idoforgod/cys-terminal src/pack.rs U-19 V-h 실측 ③ · Claude Code 2.1.241:
미로그인 좌석이 「Not logged in」 인 채 살아 있다) ⇒ 그 좌석 설정 폴더로 로그인이 확인된(verified) 때만 넣는다.
"""
import json
import os
import shutil
import sys
import tempfile

ABSENT = {"absent": True}


def load(path):
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError("%s 최상위가 객체가 아님" % os.path.basename(path))
    return data


def atomic_write(path, data):
    if os.path.islink(path):
        raise ValueError("%s 가 바로가기(심볼릭 링크)라 손대지 않음" % os.path.basename(path))
    d = os.path.dirname(path) or "."
    os.makedirs(d, exist_ok=True)
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


def set_true(data, path):
    """path 끝 칸을 true 로. 이미 true 면 None, 아니면 (바꾸기 전 값, 새로 만든 중간 칸 수)."""
    node, made = data, 0
    for k in path[:-1]:
        if k not in node:
            node[k] = {}
            made += 1
        node = node[k]
        if not isinstance(node, dict):
            raise ValueError("%s 칸이 객체가 아님" % k)
    if node.get(path[-1]) is True:
        return None
    prior = node.get(path[-1], ABSENT)
    node[path[-1]] = True
    return prior, made


def seed(config_dir, journal, auth, dirs):
    files = {"cfg": os.path.join(config_dir, ".claude.json")}
    wants = [("cfg", ["hasCompletedOnboarding"])] if auth == "verified" else []
    wants += [("cfg", ["projects", d, "hasTrustDialogAccepted"]) for d in dict.fromkeys(dirs)]
    datas = {n: load(p) for n, p in files.items()}
    created = [files[n] for n, d in datas.items() if d is None]
    datas = {n: ({} if d is None else d) for n, d in datas.items()}
    changes = []
    for n, path in wants:
        r = set_true(datas[n], path)
        if r is not None:
            changes.append({"file": files[n], "path": path, "prior": r[0], "made": r[1]})
    if not changes:
        return "unchanged"
    touched = list(dict.fromkeys(c["file"] for c in changes))
    log = load(journal) or {"backups": {}, "created_files": [], "changes": []}
    for p in touched:
        if p in created:
            log["created_files"] = list(dict.fromkeys(log["created_files"] + [p]))
        elif not os.path.exists(p + ".wave-bak"):
            shutil.copy2(p, p + ".wave-bak")
            log["backups"][p] = p + ".wave-bak"
    log["changes"] += changes
    atomic_write(journal, log)  # 기록이 먼저 선다 — 기록 없는 변경을 남기지 않는다
    for n, p in files.items():
        if p in touched:
            atomic_write(p, datas[n])
    for n, path in wants:  # 되읽기 확인
        node = load(files[n])
        for k in path:
            node = node.get(k) if isinstance(node, dict) else None
        if node is not True:
            raise ValueError("되읽기 확인 실패: %s" % ".".join(path))
    return "changed %d" % len(changes)


def rollback(journal):
    log = load(journal)
    if log is None:
        return "nothing"
    datas, dirty = {}, set()
    for c in reversed(log["changes"]):
        p = c["file"]
        if p not in datas:
            datas[p] = load(p) or {}
        chain = [datas[p]]
        for k in c["path"][:-1]:
            nxt = chain[-1].get(k)
            if not isinstance(nxt, dict):
                break
            chain.append(nxt)
        if len(chain) != len(c["path"]) or chain[-1].get(c["path"][-1]) is not True:
            continue  # 그 칸이 없거나 그 뒤 다른 값으로 바뀌었으면 그대로 둔다
        dirty.add(p)
        if c["prior"] == ABSENT:
            del chain[-1][c["path"][-1]]
        else:
            chain[-1][c["path"][-1]] = c["prior"]
        for i in range(len(chain) - 1, len(chain) - 1 - c["made"], -1):  # 우리가 만든 중간 칸이 비면 지운다
            if chain[i]:
                break
            del chain[i - 1][c["path"][i - 1]]
    for p in dirty:
        data = datas[p]
        if p in log["created_files"] and not data:
            os.unlink(p)
        else:
            atomic_write(p, data)
    os.unlink(journal)
    return "rolled back %d" % len(log["changes"])


def main(argv):
    try:
        if len(argv) >= 5 and argv[0] == "seed" and argv[3] in ("verified", "unproven"):
            print(seed(argv[1], argv[2], argv[3], argv[4:]))
        elif len(argv) == 2 and argv[0] == "rollback":
            print(rollback(argv[1]))
        else:
            print(__doc__, file=sys.stderr)
            return 2
    except (OSError, ValueError, KeyError) as e:
        print("trust_seed: %s" % e, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
