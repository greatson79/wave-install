#!/usr/bin/env bash
# 릴리스 자산 생성 (발행·push 는 하지 않는다). 사용: scripts/make-release.sh <버전 X.Y.Z> <https 릴리스 베이스 URL> <출력 폴더>
# 산출: tar.gz·zip 설치팩과 bootstrap.sh·bootstrap.ps1 주입본 및 SHA256SUMS.
# 순환 해소: 팩 안 bootstrap은 자리표시자 그대로 — 동반 steps.json·wave-pack 때문에 자기획득을 타지 않는다.
set -euo pipefail
VER="${1:?버전}"; BASE="${2:?릴리스 베이스 URL}"; OUT="${3:?출력 폴더}"
[[ "$VER" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]] || { echo "버전 형식 오류" >&2; exit 2; }
[[ "$BASE" == https://* || "$BASE" == file://* ]] || { echo "베이스 URL은 https:// (시험용 file://)" >&2; exit 2; }
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
NAME="wave-install-$VER"; TGZ="$OUT/$NAME.tar.gz"; ZIP="$OUT/$NAME.zip"
mkdir -p "$OUT"; STAGE="$(mktemp -d)"; trap 'rm -rf "$STAGE"' EXIT
mkdir -p "$STAGE/$NAME"
(cd "$ROOT" && cp -R bootstrap.sh bootstrap.ps1 steps.json install-state.json wave-pack LICENSES LICENSE reinstall.sh reinstall.ps1 README.md "$STAGE/$NAME/")
[[ "$(python3 -c 'import json,sys;print(json.load(open(sys.argv[1]))["version"])' "$STAGE/$NAME/steps.json")" == "$VER" ]] \
  || { echo "steps.json version 이 $VER 와 다름" >&2; exit 1; }
tar --exclude='.DS_Store' -czf "$TGZ" -C "$STAGE" "$NAME"
python3 - "$STAGE" "$NAME" "$ZIP" <<'PY'
from pathlib import Path
import sys, zipfile
stage, name, output = Path(sys.argv[1]), sys.argv[2], Path(sys.argv[3])
root = stage / name
with zipfile.ZipFile(output, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
    for path in sorted(root.rglob('*')):
        if path.name == '.DS_Store' or path.is_dir():
            continue
        if path.is_symlink():
            raise SystemExit(f'ZIP symlink 거부: {path}')
        archive.write(path, path.relative_to(stage).as_posix())
PY
SHA="$(shasum -a 256 "$TGZ" | awk '{print $1}')"
ZIP_SHA="$(shasum -a 256 "$ZIP" | awk '{print $1}')"
sed -e "s|__WAVE_TARBALL_URL__|${BASE%/}/$NAME.tar.gz|" -e "s|__WAVE_TARBALL_SHA256__|$SHA|" "$ROOT/bootstrap.sh" > "$OUT/bootstrap.sh"
chmod 755 "$OUT/bootstrap.sh"
grep -q '__WAVE_TARBALL' "$OUT/bootstrap.sh" && { echo "자리표시자 주입 실패" >&2; exit 1; }
bash -n "$OUT/bootstrap.sh"
python3 - "$ROOT/bootstrap.ps1" "$OUT/bootstrap.ps1" "${BASE%/}/$NAME.zip" "$ZIP_SHA" <<'PY'
from pathlib import Path
import sys
source, target, url, digest = Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3], sys.argv[4]
content = source.read_text(encoding='utf-8-sig')
for placeholder, value in (('__WAVE_INSTALL_ZIP_URL__', url), ('__WAVE_INSTALL_ZIP_SHA256__', digest)):
    if content.count(placeholder) != 1:
        raise SystemExit(f'자리표시자 개수 오류: {placeholder}')
    content = content.replace(placeholder, value)
if '__WAVE_INSTALL_ZIP_' in content:
    raise SystemExit('Windows 자리표시자 주입 실패')
target.write_bytes(b'\xef\xbb\xbf' + content.encode('utf-8'))
PY
python3 "$ROOT/tests/ps-balance.py" "$OUT/bootstrap.ps1"
(cd "$OUT" && shasum -a 256 bootstrap.sh bootstrap.ps1 "$NAME.tar.gz" "$NAME.zip" > SHA256SUMS)
echo "tarball=$TGZ sha256=$SHA"
echo "zip=$ZIP sha256=$ZIP_SHA"
echo "bootstrap=$OUT/bootstrap.sh sha256=$(shasum -a 256 "$OUT/bootstrap.sh" | awk '{print $1}')"
echo "bootstrap_ps1=$OUT/bootstrap.ps1 sha256=$(shasum -a 256 "$OUT/bootstrap.ps1" | awk '{print $1}')"
