#!/usr/bin/env bash
# macOS 러너 G5: 공개 v0.2.3 한 줄 설치 → 같은 러너에서 시험 릴리스 한 줄 → G2~G4 를 G5/ 에 남긴다.
#  mac-upgrade.sh <rc-release.json> <CA pem> <증거 루트>
set -u
RCJ="$1"; CA="$2"; EV="$3/mac/G5"; HERE="$(cd "$(dirname "$0")" && pwd)"; mkdir -p "$EV"
ONE="$(python3 -c 'import json,sys;print(json.load(open(sys.argv[1]))["one_line"])' "$RCJ")"
OLD='curl -fsSL https://github.com/greatson79/wave-install/releases/download/v0.2.3/bootstrap.sh -o "$HOME/install-wave.sh" && bash "$HOME/install-wave.sh"'
export WAVE_NO_PROGRESS=1
mkdir -p "$HOME/.local/bin"; cp "$HERE/fake-claude.sh" "$HOME/.local/bin/claude"; chmod +x "$HOME/.local/bin/claude"
grep -q 'local/bin' "$HOME/.zshenv" 2>/dev/null || echo 'export PATH="$HOME/.local/bin:$PATH"' >> "$HOME/.zshenv"
( cd "$HOME" && bash -c "$OLD" ) > "$EV/from_v023.log" 2>&1; echo $? > "$EV/from_v023.exit"
cp "$HOME/.wave/install-state.json" "$EV/from_v023_state.json"
FROM="$(python3 -c 'import json,sys;print(json.load(open(sys.argv[1])).get("installer_version"))' "$EV/from_v023_state.json")"
echo "[rc-mac-upgrade] 기존 설치기 버전: $FROM"
[ "$FROM" = "0.2.3" ] || { echo "v0.2.3 이 아님 — G5 측정 불가(증거 미생성)"; exit 0; }
SUM="$(shasum -a 256 "$EV/from_v023_state.json" | awk '{print $1}')"
printf '{"from_version":"%s","raw":[{"path":"from_v023_state.json","sha256":"%s"}]}\n' "$FROM" "$SUM" > "$EV/G5_meta.json"
bash "$HERE/reset-fleet.sh"
CURL_CA_BUNDLE="$CA" bash -c "cd \"\$HOME\" && $ONE" > "$EV/run.log" 2>&1; echo $? > "$EV/exit"
PATH="$HOME/.wave/bin:$PATH"
python3 "$HERE/collect.py" g2 --out "$EV" --preflight "$HOME/.cys/pack/bin/javis_preflight.py"
cys pack-manifest > "$EV/pack-manifest.src.json" 2>/dev/null
python3 "$HERE/collect.py" g3 --out "$EV" --manifest "$EV/pack-manifest.src.json"
python3 "$HERE/collect.py" g4 --out "$EV"
exit 0
