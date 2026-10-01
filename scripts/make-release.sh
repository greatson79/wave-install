#!/usr/bin/env bash
# 릴리스 자산 생성 (발행·push 는 하지 않는다). 사용: scripts/make-release.sh <버전 X.Y.Z> <https 릴리스 베이스 URL> <출력 폴더>
# 산출: <출력>/wave-install-<버전>.tar.gz  ·  <출력>/bootstrap.sh (tarball URL·SHA256 주입본)
# SHA256 순환 해소(2안): tarball 안 bootstrap.sh 는 자리표시자 그대로 — steps.json 이 옆에 있어 자기획득을 타지 않는다.
#   릴리스 자산 bootstrap.sh 에만 값을 주입한다.
set -euo pipefail
VER="${1:?버전}"; BASE="${2:?릴리스 베이스 URL}"; OUT="${3:?출력 폴더}"
[[ "$VER" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]] || { echo "버전 형식 오류" >&2; exit 2; }
[[ "$BASE" == https://* || "$BASE" == file://* ]] || { echo "베이스 URL은 https:// (시험용 file://)" >&2; exit 2; }
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
NAME="wave-install-$VER"; TGZ="$OUT/$NAME.tar.gz"
mkdir -p "$OUT"; STAGE="$(mktemp -d)"; trap 'rm -rf "$STAGE"' EXIT
mkdir -p "$STAGE/$NAME"
(cd "$ROOT" && cp -R bootstrap.sh steps.json install-state.json wave-pack LICENSES README.md "$STAGE/$NAME/")
[[ "$(python3 -c 'import json,sys;print(json.load(open(sys.argv[1]))["version"])' "$STAGE/$NAME/steps.json")" == "$VER" ]] \
  || { echo "steps.json version 이 $VER 와 다름" >&2; exit 1; }
tar --exclude='.DS_Store' -czf "$TGZ" -C "$STAGE" "$NAME"
SHA="$(shasum -a 256 "$TGZ" | awk '{print $1}')"
sed -e "s|__WAVE_TARBALL_URL__|${BASE%/}/$NAME.tar.gz|" -e "s|__WAVE_TARBALL_SHA256__|$SHA|" "$ROOT/bootstrap.sh" > "$OUT/bootstrap.sh"
chmod 755 "$OUT/bootstrap.sh"
grep -q '__WAVE_TARBALL' "$OUT/bootstrap.sh" && { echo "자리표시자 주입 실패" >&2; exit 1; }
bash -n "$OUT/bootstrap.sh"
echo "tarball=$TGZ sha256=$SHA"
echo "bootstrap=$OUT/bootstrap.sh sha256=$(shasum -a 256 "$OUT/bootstrap.sh" | awk '{print $1}')"
