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
python3 "$HERE/run_to.py" 1500 "$EV/from_v023.log" -- bash -c "cd \"\$HOME\" && $OLD"; echo $? > "$EV/from_v023.exit"
cp "$HOME/.wave/install-state.json" "$EV/from_v023_state.json"
# 공개 v0.2.3 의 상태 파일 installer_version 은 0.1.3 으로 안 올려진 채 배포됐다(10/3 실측) → 받은 설치팩 주소·팩 steps.json 의 version 으로 판정
FROM="$(python3 - "$EV/from_v023.log" "$HOME/.wave/src/pack/steps.json" <<'PY'
import json, re, sys
m = re.search(r"wave-install-(\d+\.\d+\.\d+)\.(?:tar\.gz|zip)", open(sys.argv[1], encoding="utf-8", errors="replace").read())
v = json.load(open(sys.argv[2], encoding="utf-8")).get("version")
print(m.group(1) if m and m.group(1) == v else "mismatch(%s,%s)" % (m and m.group(1), v))
PY
)"
echo "[rc-mac-upgrade] 기존 설치기 버전: $FROM"
[ "$FROM" = "0.2.3" ] || { echo "v0.2.3 이 아님 — G5 측정 불가(증거 미생성)"; exit 0; }
SUM="$(shasum -a 256 "$EV/from_v023_state.json" | awk '{print $1}')"
printf '{"from_version":"%s","raw":[{"path":"from_v023_state.json","sha256":"%s"}]}\n' "$FROM" "$SUM" > "$EV/G5_meta.json"
bash "$HERE/reset-fleet.sh"
CURL_CA_BUNDLE="$CA" python3 "$HERE/run_to.py" 1500 "$EV/run.log" -- bash -c "cd \"\$HOME\" && $ONE"; echo $? > "$EV/exit"
PATH="$HOME/.wave/bin:$PATH"
python3 "$HERE/collect.py" g2 --out "$EV" --preflight "$HOME/.cys/pack/bin/javis_preflight.py"
cys pack-manifest > "$EV/pack-manifest.src.json" 2>/dev/null
python3 "$HERE/collect.py" g3 --out "$EV" --manifest "$EV/pack-manifest.src.json"
python3 "$HERE/collect.py" g4 --out "$EV"
exit 0
