#!/usr/bin/env bash
# 러너 전용: 등록을 해제해 KeepAlive 자동복원을 멈춘 뒤 실제 종료를 확인한다.
# ★CI 러너(일회용 계정·HOME) 안에서만 돈다 — 아래 pkill 은 이 HOME 의 Wave 프로세스만 겨냥하고, 사용자 기기에서 돌리라고 만든 것이 아니다.
#  reset-fleet.sh [실패 시 상태 덤프 파일]
set -euo pipefail
dump="${1:-}"
# 설치기 관문(wave_bundle_in_use)과 같은 범위: 앱 Contents/ 아래 모든 프로세스 + 열린 파일
app_dir="$HOME/.wave/apps/Wave Terminal.app"
app_bin="$app_dir/Contents/"
processes="$(ps -axo comm=)" || exit 1
if [[ "$processes" == *"$app_bin"* ]]; then
  osascript -e 'tell application id "com.waveainetworks.wave-terminal" to quit'
fi
# 이전 fleet 의 합성 좌석(claude)과 그 진단 루프(.wave/rc/ 아래 명령줄)를 먼저 정리한다 — 루프의 `cys status` 한 번이
# 데몬 부재 시 자동기동으로 데몬을 되살려 정지 확인을 깬다(양상 2). 데몬 정지보다 앞서야 되살릴 틈이 없다.
esc="$(printf '%s' "$HOME" | sed 's/[][\\.*^$+?(){}|]/\\&/g')"
pkill -f "$HOME/.local/bin/claude" 2>/dev/null || true
pkill -f "$HOME/.wave/rc/" 2>/dev/null || true
# 오피스 브리지(cysd 의 자식)를 먼저 — 데몬이 launchd 소유가 아니면 cysd 정지로 안 죽고, 살아 있는 동안 이벤트 구독
# 클라이언트(cys events --reconnect)를 계속 새로 띄운다(양상 4). 이 HOME 의 브리지 스크립트만(설치기 안내와 같은 패턴).
pkill -f "^.*[pP]ython[0-9.]* $esc/\.cys/pack/bin/javis_hud_bridge\.py( |\$)" 2>/dev/null || true
"$HOME/.wave/bin/cys" daemon uninstall
# launchd 소유가 아닌 데몬(공개판 v0.2.3 이 CLI 자동기동으로 만든 것)은 daemon uninstall 로 안 멈춘다(양상 1).
# 설치기가 사용자에게 안내하는 정지 한 줄(bootstrap.sh S04 보류 안내)과 같은 패턴: 이 HOME 의 cysd 로 시작하는 명령줄만.
# 데몬과 그 이벤트 구독 클라이언트(데몬이 없어도 재연결 루프로 남아 앱 번들 cys 를 연 채 다음 설치를 막는다).
pkill -f "^$esc/\.wave/(apps/Wave Terminal\.app/Contents/MacOS|bin)/(cysd|cys events)( |\$)" 2>/dev/null || true
settled() {
  status="$(env -u CYS_SOCKET -u JAVIS_SOCKET -u AITERM_SOCKET "$HOME/.wave/bin/cys" daemon status)"
  processes="$(ps -axo comm=)" || exit 1
  [[ "$status" == *registered=false*loaded=false*socket_alive=false* && "$processes" != *"$app_bin"* \
     && -z "$(lsof -nP -t +D "$app_dir" 2>/dev/null || true)" ]]
}
for attempt in {1..50}; do
  if settled; then break; fi
  sleep 0.2
done
settled || {
  echo 'Wave 프로세스가 아직 살아 있어 다음 설치를 시작하지 않습니다.' >&2
  if [[ -n "$dump" ]]; then
    mkdir -p "$(dirname "$dump")"
    {
      echo "# daemon status"; echo "$status"
      echo "# ps (cysd|Wave Terminal|claude|rc|sleep|cys)"
      ps -axo pid,ppid,etime,command | grep -E 'cysd|Wave Terminal|claude|\.wave/rc|sleep|cys ' | grep -v grep || true
      echo "# lsof +D app"; lsof -nP +D "$app_dir" 2>&1 || true
      echo "# launchctl list | grep -i cys"; launchctl list 2>&1 | grep -i cys || true
    } > "$dump" 2>&1
  fi
  exit 1
}
rm -f "$HOME/.cys/.master-bootstrapped"
rm -rf "$HOME/.wave/rc" "$HOME/.cys/state/boot-last.json"
rm -f "$HOME/.wave/verify"/hook_*.out "$HOME/.wave/verify"/G3_inject.json
