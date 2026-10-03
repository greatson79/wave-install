#!/usr/bin/env bash
# macOS 러너: 시험 릴리스의 한 줄을 그대로 실행하고 G1·G2·G3·G4(+G6) 증거를 만든다.
#  mac-run.sh <rc-release.json> <CA pem> <증거 루트>      (증거 루트/mac/ 에 쓴다)
set -u
RCJ="$1"; CA="$2"; EV="$3/mac"; HERE="$(cd "$(dirname "$0")" && pwd)"; mkdir -p "$EV/G6" "$EV/phaseA"
ONE="$(python3 -c 'import json,sys;print(json.load(open(sys.argv[1]))["one_line"])' "$RCJ")"
export CURL_CA_BUNDLE="$CA" WAVE_NO_PROGRESS=1
log() { echo "[rc-mac] $*"; }
# 고정 한 줄 그대로 실행 — 서브셸에서 bash -c (주소만 시험 서버로 치환된 README 줄)
oneline() { python3 "$HERE/run_to.py" "${2:-1500}" "$1" -- bash -c "cd \"\$HOME\" && $ONE"; }
# 단계 A 전용: 브라우저를 못 열게(open 무력화 shim · BROWSER=false) 하고 300초 상한 — S02 가 로그인 대기에 들어가면 그 프로세스 그룹만 종료
phase_a() {
  local shim="$RUNNER_TEMP/nobrowser"; mkdir -p "$shim"; printf '#!/bin/sh\nexit 0\n' > "$shim/open"; chmod +x "$shim/open"
  PATH="$shim:$PATH" BROWSER=false oneline "$EV/phaseA/run.log" 300
  local rc=$?
  pkill -f 'claude auth login' 2>/dev/null; pkill -x claude 2>/dev/null; true  # 진짜 claude 잔여 프로세스가 합성 좌석 관측(agent_alive)을 오염시키지 않게
  return $rc
}

log "A: 로그인 없는 깨끗한 상태 — 실제 S00·S01 후 S02 에서 멈추는 것이 정상"
phase_a; echo $? > "$EV/phaseA/exit"
cp "$HOME/.wave/install-state.json" "$EV/phaseA/state.json" 2>/dev/null

log "합성 claude 투입(S02 이하 결정론 단계용)"
mkdir -p "$HOME/.local/bin"; [ -e "$HOME/.local/bin/claude" ] && mv "$HOME/.local/bin/claude" "$HOME/.local/bin/claude.real"
mkdir -p "$HOME/.local/share/rc-fake"; cp "$HERE/fake_claude.py" "$HOME/.local/share/rc-fake/logic.py"
cc -O0 -DLOGIC="\"$HOME/.local/share/rc-fake/logic.py\"" -o "$HOME/.local/bin/claude" "$HERE/claude_launcher.c"  # 네이티브 런처 — 프로세스 이름이 처음부터 claude
for rcf in "$HOME/.zshenv" "$HOME/.bash_profile" "$HOME/.bashrc" "$HOME/.profile"; do grep -q 'local/bin' "$rcf" 2>/dev/null || echo 'export PATH="$HOME/.local/bin:$PATH"' >> "$rcf"; done  # 러너 계정 로그인 셸이 bash 라 좌석 셸이 .zshenv 를 읽지 않는다(4차 run: cys boot 가 claude 를 못 찾아 60초 미확인)

log "B: 같은 한 줄 재실행"
oneline "$EV/run.log"; echo $? > "$EV/exit"

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
python3 - "$HOME/.wave/install-state.json" "$EV/G6/before-state.json" <<'PY'
import pathlib, shutil, sys
source = pathlib.Path(sys.argv[1])
if source.is_file(): shutil.copy2(source, sys.argv[2])
PY
bash "$HERE/reset-fleet.sh" || { log "G6 재설치 전 정지 실패"; exit 1; }
python3 "$HERE/run_to.py" 1500 "$EV/G6/run.log" -- bash -c "cd \"\$HOME\" && bash \"\$HOME/install-wave.sh\" --reinstall"; echo $? > "$EV/G6/exit"
cp "$HOME/.wave/install-state.json" "$EV/G6/install-state.json" 2>/dev/null || log "G6 설치 상태 수집 실패"
python3 - "$EV/G6/before-state.json" "$EV/G6/install-state.json" "$EV/G6/attempt.json" <<'PY'
import json, pathlib, sys
def stamp(path):
    try:
        doc = json.loads(pathlib.Path(path).read_text())
        return {k: doc.get(k) for k in ("created_at", "updated_at", "status")}
    except (OSError, ValueError): return None
pathlib.Path(sys.argv[3]).write_text(json.dumps({"before": stamp(sys.argv[1]), "after": stamp(sys.argv[2])}))
PY
collect "$EV/G6"
cp -R "$HOME/.wave/rc" "$EV/G6/rc-synthetic-logs" 2>/dev/null   # 19차: 재설치 ① 이 C43(uvx 없음)로 한 번 실패 — 그때의 좌석 PATH·프로세스 증거를 G6 에도 남긴다
python3 "$HERE/collect.py" claude-hash --out "$EV/G6" --phase after
# 증거 없이 성공 처리 금지: 필수 증거가 하나라도 없으면 잡을 실패시킨다(판정은 gate.py 몫 — 여기선 존재만)
miss=0; for f in G1_state.json G2_preflight.json G3_inject.json G4_boot.json G6/exit G6/install-state.json G6/attempt.json G6/G6_claude_untouched.json G6/G2_preflight.json G6/G3_inject.json G6/G4_boot.json; do [ -s "$EV/$f" ] || { log "증거 없음: $f"; miss=1; }; done
exit $miss
