#!/usr/bin/env bash
# 합성 claude — LLM·로그인 없음(「합성」 표기 대상). 설치기가 부르는 모양만 흉내 낸다.
#  --version / auth * / update : 즉시 성공
#  그 외(좌석 기동): 이 좌석 역할(CYS_ROLE)로 settings.json 에 등록된 SessionStart 훅을 그대로 실행해 stdout 을 ~/.wave/rc/hook_<역할>.out 에 남기고,
#                    master 이면 결정론 부트(javis_bootstrap.py)를 실행한 뒤, 프로세스 이름 claude 로 대기한다(agent_alive 관측용).
RC="$HOME/.wave/rc"; mkdir -p "$RC"
case "${1:-}" in
  --version) echo "2.1.300 (Claude Code)"; exit 0 ;;
  auth|update) exit 0 ;;
esac
role="${CYS_ROLE:-none}"
cmd="$(python3 - <<'PY'
import glob, json, os
home = os.path.expanduser("~")
for p in [os.path.join(os.environ.get("CLAUDE_CONFIG_DIR", home + "/.claude"), "settings.json")] + glob.glob(home + "/.claude*/settings.json") + glob.glob(home + "/.cys/**/settings.json", recursive=True):
    try: d = json.load(open(p, encoding="utf-8"))
    except Exception: continue
    for e in d.get("hooks", {}).get("SessionStart", []):
        for h in e.get("hooks", []):
            if "session-start.sh" in h.get("command", ""):
                print(h["command"]); raise SystemExit
PY
)"
printf '%s\n' "$cmd" > "$RC/hook_command_${role}.txt"
if [ -n "$cmd" ] && [ "$role" != none ]; then
  printf '{"source":"startup","cwd":"%s"}\n' "$PWD" | sh -c "$cmd" > "$RC/hook_${role}.out" 2> "$RC/hook_${role}.err"
  echo $? > "$RC/hook_${role}.rc"
fi
if [ "$role" = master ]; then
  python3 "${CYS_PACK_DIR:-$HOME/.cys/pack}/bin/javis_bootstrap.py" > "$RC/bootstrap.out" 2> "$RC/bootstrap.err"
  echo $? > "$RC/bootstrap.rc"
fi
exec -a claude sleep 86400
