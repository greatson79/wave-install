#!/usr/bin/env bash
# macOS 러너: 시험 릴리스의 한 줄을 그대로 실행하고 G1·G2·G3·G4(+G6) 증거를 만든다.
#  mac-run.sh <rc-release.json> <CA pem> <증거 루트>      (증거 루트/mac/ 에 쓴다)
set -u
RCJ="$1"; CA="$2"; EV="$3/mac"; HERE="$(cd "$(dirname "$0")" && pwd)"; mkdir -p "$EV/G6" "$EV/phaseA"
ONE="$(python3 -c 'import json,sys;print(json.load(open(sys.argv[1]))["one_line"])' "$RCJ")"
export CURL_CA_BUNDLE="$CA" WAVE_NO_PROGRESS=1
log() { echo "[rc-mac] $*"; }
# 고정 한 줄 그대로 실행 — 서브셸에서 bash -c (주소만 시험 서버로 치환된 README 줄)
oneline() { ( cd "$HOME" && bash -c "$ONE" ); }

log "A: 로그인 없는 깨끗한 상태 — 실제 S00·S01 후 S02 에서 멈추는 것이 정상"
oneline > "$EV/phaseA/run.log" 2>&1; echo $? > "$EV/phaseA/exit"
cp "$HOME/.wave/install-state.json" "$EV/phaseA/state.json" 2>/dev/null

log "합성 claude 투입(S02 이하 결정론 단계용)"
mkdir -p "$HOME/.local/bin"; [ -e "$HOME/.local/bin/claude" ] && mv "$HOME/.local/bin/claude" "$HOME/.local/bin/claude.real"
cp "$HERE/fake-claude.sh" "$HOME/.local/bin/claude"; chmod +x "$HOME/.local/bin/claude"
grep -q 'local/bin' "$HOME/.zshenv" 2>/dev/null || echo 'export PATH="$HOME/.local/bin:$PATH"' >> "$HOME/.zshenv"

log "B: 같은 한 줄 재실행"
oneline > "$EV/run.log" 2>&1; echo $? > "$EV/exit"

collect() {  # collect <대상 폴더>
  local d="$1"; mkdir -p "$d"
  PATH="$HOME/.wave/bin:$PATH"
  python3 "$HERE/collect.py" g2 --out "$d" --preflight "$HOME/.cys/pack/bin/javis_preflight.py" || log "g2 수집 실패"
  cys pack-manifest > "$d/pack-manifest.src.json" 2>/dev/null
  python3 "$HERE/collect.py" g3 --out "$d" --manifest "$d/pack-manifest.src.json" || log "g3 수집 실패"
  python3 "$HERE/collect.py" g4 --out "$d" || log "g4 수집 실패"
  cp "$HOME/.wave/verify/G3_inject.json" "$d/installer_G3_inject.json" 2>/dev/null  # 설치기 S08 이 쓴 값(대조용 · 판정기 입력 아님)
}
python3 "$HERE/collect.py" g1 --out "$EV"
collect "$EV"
cp -R "$HOME/.wave/rc" "$EV/rc-synthetic-logs" 2>/dev/null

log "G6: ~/.claude 기준선 → 재설치(--reinstall) → 재측정"
python3 "$HERE/collect.py" claude-hash --out "$EV/G6" --phase before
bash "$HERE/reset-fleet.sh"
( cd "$HOME" && bash "$HOME/install-wave.sh" --reinstall ) > "$EV/G6/run.log" 2>&1; echo $? > "$EV/G6/exit"
collect "$EV/G6"
python3 "$HERE/collect.py" claude-hash --out "$EV/G6" --phase after
exit 0
