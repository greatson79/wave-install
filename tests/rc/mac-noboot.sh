#!/usr/bin/env bash
# rc.5 계약: 표지 없는 합성 Claude도 S07~S09 통과; 원문 status·S08 미확인 안내를 evidence로 보존한다
#  mac-noboot.sh <rc-release.json> <CA pem> <증거 루트>      (증거 루트/mac/noboot/ 에 쓴다)
set -u
RCJ="$1"; CA="$2"; EV="$3/mac/noboot"; HERE="$(cd "$(dirname "$0")" && pwd)"; mkdir -p "$EV"
ONE="$(python3 -c 'import json,sys;print(json.load(open(sys.argv[1]))["one_line"])' "$RCJ")"
export WAVE_NO_PROGRESS=1 CURL_CA_BUNDLE="$CA"
mkdir -p "$HOME/.local/bin" "$HOME/.local/share/rc-fake" "$HOME/.wave"; cp "$HERE/fake_claude.py" "$HOME/.local/share/rc-fake/logic.py"
cc -O0 -DLOGIC="\"$HOME/.local/share/rc-fake/logic.py\"" -o "$HOME/.local/bin/claude" "$HERE/claude_launcher.c"  # 네이티브 런처 — 프로세스 이름이 처음부터 claude
for rcf in "$HOME/.zshenv" "$HOME/.bash_profile" "$HOME/.bashrc" "$HOME/.profile"; do grep -q 'local/bin' "$rcf" 2>/dev/null || echo 'export PATH="$HOME/.local/bin:$PATH"' >> "$rcf"; done
: > "$HOME/.wave/rc-skip-bootstrap"   # fake_claude.py 가 이 파일을 보고 javis_bootstrap.py 를 건너뛴다
python3 "$HERE/run_to.py" 1500 "$EV/run.log" -- bash -c "cd \"\$HOME\" && $ONE"; echo $? > "$EV/exit"
[ -e "$HOME/.cys/.master-bootstrapped" ] || : > "$EV/marker_absent"
cp "$HOME/.wave/install-state.json" "$EV/install-state.json" 2>/dev/null
cp "$HOME/.wave/fleet/status.json" "$EV/cys-status.json" 2>/dev/null
bash "$HERE/collect-fleet.sh" "$EV"   # install.log · fleet/ · 표지(있으면)
cp -R "$HOME/.wave/rc" "$EV/rc-synthetic-logs" 2>/dev/null
python3 "$HERE/surface_list.py" "$EV/surface_list.json" || true   # surface.list 원본 응답(증거만)
[ -s "$EV/exit" ] && [ -s "$EV/install-state.json" ] && [ -s "$EV/cys-status.json" ]
