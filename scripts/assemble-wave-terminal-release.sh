#!/usr/bin/env bash
# 배포 장소 하나(wave-terminal 릴리스)용 설치 자산 조립 — 발행·push 는 하지 않는다.
# 사용: scripts/assemble-wave-terminal-release.sh <owner/repo> <앱 판 X.Y.Z> <art 폴더>
#   art 폴더 = 앱 쪽 자산(DMG · .app.tar.gz · .sig · latest.json)이 이미 든 곳. 여기에 설치기 쪽
#   (bootstrap.sh/.ps1 · 설치팩 tar.gz/zip · win-start.ps1 · steps.json)을 더하고 전 자산 SHA256SUMS 를 쓴다.
#   <owner/repo> 가 greatson79/wave-terminal 이 아니면(시험 저장소) steps.json·bootstrap.sh 안
#   저장소 이름만 바꾼 사본으로 만든다(공개 기본값 = 저장소 파일은 그대로).
set -euo pipefail
REPO="${1:?owner/repo}"; V="${2:?app version}"; ART="${3:?art dir}"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
IV="$(python3 -c 'import json,sys;print(json.load(open(sys.argv[1]))["version"])' "$ROOT/steps.json")"
[[ -d "$ART" ]] || { echo "art 폴더 없음: $ART" >&2; exit 2; }
[[ ! -e "$ART/SHA256SUMS" ]] || { echo "✗ $ART 에 이미 SHA256SUMS — 새 폴더로 다시 조립(지우지 않음)" >&2; exit 1; }
STAGE="$(mktemp -d)"   # 임시 폴더는 지우지 않는다(변수 rm 금지 · OS 임시 정리에 맡김)
mkdir -p "$STAGE/src" && git -C "$ROOT" archive HEAD | tar -x -C "$STAGE/src"   # 커밋된 것만(작업 트리 찌꺼기 0)
if [[ "$REPO" != "greatson79/wave-terminal" ]]; then
  # 시험 사본: 저장소 이름 한 곳만(github.com/greatson79/wave-terminal/releases → <repo>/releases)
  sed -i '' "s#github.com/greatson79/wave-terminal/releases#github.com/$REPO/releases#g" "$STAGE/src/steps.json" "$STAGE/src/bootstrap.sh"
  python3 - "$STAGE/src/steps.json" "$REPO" <<'PY'
import json, sys
p, repo = sys.argv[1:]; s = json.load(open(p, encoding="utf-8"))
assert s["release"]["repository"] == "greatson79/wave-terminal"
txt = open(p, encoding="utf-8").read().replace('"repository": "greatson79/wave-terminal"', f'"repository": "{repo}"', 1)
open(p, "w", encoding="utf-8").write(txt)
PY
fi
[[ "$(python3 -c 'import json,sys;print(json.load(open(sys.argv[1]))["release"]["version"])' "$STAGE/src/steps.json")" == "$V" ]] \
  || { echo "steps.json release.version != $V" >&2; exit 1; }
bash "$STAGE/src/scripts/make-release.sh" "$IV" "https://github.com/$REPO/releases/download/v$V" "$STAGE/out" >/dev/null
cp "$STAGE/out/bootstrap.sh" "$STAGE/out/bootstrap.ps1" "$STAGE/out/wave-install-$IV.tar.gz" "$STAGE/out/wave-install-$IV.zip" "$ART/"
cp "$STAGE/src/steps.json" "$ART/steps.json"
python3 - "$STAGE/src/win-start.ps1" "$ART/win-start.ps1" "https://github.com/$REPO/releases/download/v$V/bootstrap.ps1" "$ART/bootstrap.ps1" <<'PY'
from pathlib import Path
import hashlib, sys
source, target, bootstrap = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[4])
url = sys.argv[3]
text = source.read_text(encoding='utf-8-sig')
for marker, value in [('__WAVE_BOOTSTRAP_URL__', url), ('__WAVE_BOOTSTRAP_SHA256__', hashlib.sha256(bootstrap.read_bytes()).hexdigest())]:
    assert text.count(marker) == 1, marker
    text = text.replace(marker, value)
target.write_text(text, encoding='utf-8-sig')
PY
( cd "$ART" && shasum -a 256 $(ls | sort) > "$STAGE/sums" && mv "$STAGE/sums" SHA256SUMS )
echo "조립 끝: $ART ($REPO v$V · 설치기 $IV)"; cat "$ART/SHA256SUMS"
