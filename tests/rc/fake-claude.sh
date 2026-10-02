#!/usr/bin/env bash
# 합성 claude — LLM·로그인 없음(「합성」 표기 대상). 설치기가 부르는 모양만 흉내 낸다.
#  --version / auth * / update : 즉시 성공
#  그 외(좌석 기동): 이 좌석 역할(CYS_ROLE)로 settings.json 에 등록된 SessionStart 훅을 그대로 실행해 stdout 을 ~/.wave/rc/hook_<역할>.out 에 남기고,
#                    master 이면 결정론 부트(javis_bootstrap.py)를 실행한 뒤, 프로세스 이름 claude 로 대기한다(agent_alive 관측용).
RC="$HOME/.wave/rc"; VF="$HOME/.wave/verify"; mkdir -p "$RC" "$VF"  # 훅 stdout 은 설치기 소비 경로(verify/hook_<역할>.out)에도 둔다
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
  cp "$RC/hook_${role}.out" "$VF/hook_${role}.out"
fi
if [ "$role" = master ]; then
  { echo "PATH=$PATH"; echo "uvx=$(command -v uvx)"; echo "python3=$(command -v python3)"; echo "cysd_link=$(readlink "$HOME/.wave/bin/cysd")"; ps -axo pid,command | grep "[c]ysd" | head -5; echo "ls_wave_bin:"; ls -l "$HOME/.wave/bin"; } 2>&1 > "$RC/preflight_path.txt"  # 부트 ①(preflight --fix)이 상속하는 좌석 PATH 원문
  python3 "${CYS_PACK_DIR:-$HOME/.cys/pack}/bin/javis_bootstrap.py" > "$RC/bootstrap.out" 2> "$RC/bootstrap.err"
  echo $? > "$RC/bootstrap.rc"
fi
# launch-agent 는 agents.json 의 ready_marker(❯)가 화면에 보일 때까지 최대 60초 기다린 뒤 지침을 주입한다 — 합성 claude 도 같은 표지를 출력해야 한다(5차: 미확인 60s)
printf '\n❯ \n'
# 프로세스 자신이 살아 있어야 명령줄(bash <경로>/claude …)이 cysd 의 agent_alive 매칭(토큰 basename==claude)에 잡힌다 — exec -a 로 바꾸면 7차처럼 미기동으로 관측됨
while true; do sleep 3600; done
