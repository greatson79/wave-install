#!/usr/bin/env bash
# macOS 러너 rc4: 부트 점검을 건너뛰는 합성 Claude 로 시험 릴리스 한 줄을 실행한다 — 기대 = 설치기의 「세 칸 생존 · 확인 미완」 별도 종료값(판정 = check_noboot.py · 기대값 rc4-expect.json)
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
bash "$HERE/collect-fleet.sh" "$EV"   # install.log · fleet/ · 표지(있으면)
cp -R "$HOME/.wave/rc" "$EV/rc-synthetic-logs" 2>/dev/null
python3 "$HERE/surface_list.py" "$EV/surface_list.json" || true   # surface.list 원본 응답(증거만)
[ -s "$EV/exit" ] && [ -s "$EV/install-state.json" ]
