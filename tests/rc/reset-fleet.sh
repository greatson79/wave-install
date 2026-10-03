#!/usr/bin/env bash
# 러너 전용: 등록을 해제해 KeepAlive 자동복원을 멈춘 뒤 실제 종료를 확인한다.
set -euo pipefail
# 설치기 관문(wave_bundle_in_use)과 같은 범위: 앱 Contents/ 아래 모든 프로세스 + 열린 파일
app_dir="$HOME/.wave/apps/Wave Terminal.app"
app_bin="$app_dir/Contents/"
processes="$(ps -axo comm=)" || exit 1
if [[ "$processes" == *"$app_bin"* ]]; then
  osascript -e 'tell application id "com.waveainetworks.wave-terminal" to quit'
fi
"$HOME/.wave/bin/cys" daemon uninstall
pkill -f "$HOME/.local/bin/claude" 2>/dev/null || true
pkill -f "$HOME/.wave/rc/bin_" 2>/dev/null || true
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
  exit 1
}
rm -f "$HOME/.cys/.master-bootstrapped"
rm -rf "$HOME/.wave/rc" "$HOME/.cys/state/boot-last.json"
rm -f "$HOME/.wave/verify"/hook_*.out "$HOME/.wave/verify"/G3_inject.json
