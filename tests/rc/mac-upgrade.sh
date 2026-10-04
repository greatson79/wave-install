#!/usr/bin/env bash
# macOS 러너 G5: 공개 v0.2.3 한 줄 설치 → 같은 러너에서 시험 릴리스 한 줄 → G2~G4 를 G5/ 에 남긴다.
#  mac-upgrade.sh <rc-release.json> <CA pem> <증거 루트>
set -u
RCJ="$1"; CA="$2"; EV="$3/mac/G5"; HERE="$(cd "$(dirname "$0")" && pwd)"; mkdir -p "$EV"
ONE="$(python3 -c 'import json,sys;print(json.load(open(sys.argv[1]))["one_line"])' "$RCJ")"
OLD='curl -fsSL https://github.com/greatson79/wave-install/releases/download/v0.2.3/bootstrap.sh -o "$HOME/install-wave.sh" && bash "$HOME/install-wave.sh"'
export WAVE_NO_PROGRESS=1
mkdir -p "$HOME/.local/bin"; mkdir -p "$HOME/.local/share/rc-fake"; cp "$HERE/fake_claude.py" "$HOME/.local/share/rc-fake/logic.py"
cc -O0 -DLOGIC="\"$HOME/.local/share/rc-fake/logic.py\"" -o "$HOME/.local/bin/claude" "$HERE/claude_launcher.c"  # 네이티브 런처 — 프로세스 이름이 처음부터 claude
for rcf in "$HOME/.zshenv" "$HOME/.bash_profile" "$HOME/.bashrc" "$HOME/.profile"; do grep -q 'local/bin' "$rcf" 2>/dev/null || echo 'export PATH="$HOME/.local/bin:$PATH"' >> "$rcf"; done  # 러너 계정 로그인 셸이 bash 라 좌석 셸이 .zshenv 를 읽지 않는다(회귀 관측 run: cys boot 가 claude 를 못 찾아 60초 미확인)
python3 "$HERE/run_to.py" 1500 "$EV/from_v023.log" -- bash -c "cd \"\$HOME\" && $OLD"; echo $? > "$EV/from_v023.exit"
cp "$HOME/.wave/install-state.json" "$EV/from_v023_state.json"
cp "$HOME/.cys/pack/schedule.json" "$EV/installed_schedule_v023.json" 2>/dev/null   # 증거만(G7b 기준 아님): v0.2.3 설치본 — 데몬이 부트마다 기본 잡을 써 넣어 변한다
# 공개 v0.2.3 의 상태 파일 installer_version 은 0.1.3 으로 안 올려진 채 배포됐다(10/3 실측) → 받은 설치팩 주소·팩 steps.json 의 version 으로 판정
FROM="$(python3 - "$EV/from_v023.log" "$HOME/.wave/src/pack/steps.json" <<'PY'
import json, re, sys
m = re.search(r"wave-install-(\d+\.\d+\.\d+)\.(?:tar\.gz|zip)", open(sys.argv[1], encoding="utf-8", errors="replace").read())
v = json.load(open(sys.argv[2], encoding="utf-8")).get("version")
print(m.group(1) if m and m.group(1) == v else "mismatch(%s,%s)" % (m and m.group(1), v))
PY
)"
echo "[rc-mac-upgrade] 기존 설치기 버전: $FROM"
[ "$FROM" = "0.2.3" ] || { echo "v0.2.3 이 아님($FROM) — G5 측정 불가"; exit 1; }
SUM="$(shasum -a 256 "$EV/from_v023_state.json" | awk '{print $1}')"
printf '{"from_version":"%s","raw":[{"path":"from_v023_state.json","sha256":"%s"}]}\n' "$FROM" "$SUM" > "$EV/G5_meta.json"
bash "$HERE/reset-fleet.sh" "$EV/reset-fail.txt" || exit 1
CURL_CA_BUNDLE="$CA" python3 "$HERE/run_to.py" 1500 "$EV/run.log" -- bash -c "cd \"\$HOME\" && $ONE"; echo $? > "$EV/exit"
bash "$HERE/collect-fleet.sh" "$EV"   # 설치기가 쓴 시도·좌석 기록(실패한 업그레이드의 마지막 상태 포함)
cp "$HOME/.wave/install-state.json" "$EV/state.json" 2>/dev/null   # rc4: check_first_run.py 입력
PATH="$HOME/.wave/bin:$PATH"
python3 "$HERE/collect.py" g2 --out "$EV" --preflight "$HOME/.cys/pack/bin/javis_preflight.py"
cys pack-manifest > "$EV/pack-manifest.src.json" 2>/dev/null
python3 "$HERE/collect.py" g3 --out "$EV" --manifest "$EV/pack-manifest.src.json"
python3 "$HERE/collect.py" g4 --out "$EV"
cp "$HOME/.cys/pack/schedule.json" "$EV/installed_schedule_rc.json" 2>/dev/null   # 증거만: 업그레이드 후 설치본
miss=0; for f in G5_meta.json G2_preflight.json G3_inject.json G4_boot.json; do [ -s "$EV/$f" ] || { echo "증거 없음: $f"; miss=1; }; done
exit $miss
