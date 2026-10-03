#!/usr/bin/env bash
# 시험용 ad-hoc 재서명 — CI 빌드 DMG 는 Tauri 서명 뒤 런타임이 들어가 봉인이 깨져(「code has no resources but signature indicates they must be present」) 설치기 S03 의 codesign --verify --deep --strict 를 못 넘는다.
# 안쪽 Mach-O → 중첩 번들 → 앱 순으로 ad-hoc 재서명하고 새 DMG 를 만든다. ★실제 Developer ID 서명·공증이 아니다(G9/릴리스에서 별도). 바이트가 아닌 서명이 달라지므로 CDHash 도 새로 계산해 시험 steps 에 넣는다.
#  mac-resign.sh <원본.dmg> <출력.dmg> <로그>
set -euo pipefail
SRC="$1"; OUT="$2"; LOG="$3"; W="$(mktemp -d)"; MP="$W/mnt"; mkdir -p "$MP" "$W/stage"
{
  echo "# 시험용 ad-hoc 재서명 (실제 Developer ID 서명·공증 아님)"; echo "source_dmg_sha256=$(shasum -a 256 "$SRC" | awk '{print $1}')"
  hdiutil attach -nobrowse -readonly -mountpoint "$MP" "$SRC" >/dev/null
  APP="$(find "$MP" -maxdepth 2 -type d -name '*.app' -print -quit)"; NAME="$(basename "$APP")"
  echo "--- 재서명 전 검증 (원문)"; codesign --verify --deep --strict --verbose=4 "$APP" 2>&1 || echo "before_verify_exit=$?"
  ditto "$APP" "$W/stage/$NAME"; hdiutil detach "$MP" >/dev/null
  A="$W/stage/$NAME"; xattr -cr "$A"
  n=0
  while IFS= read -r f; do codesign --force --sign - --timestamp=none "$f" >/dev/null 2>&1 && n=$((n+1)) || echo "WARN sign failed: $f"; done < <(
    find "$A" -type f -print0 | while IFS= read -r -d '' f; do file -b "$f" | grep -q 'Mach-O' && echo "$f"; done | awk '{print length "\t" $0}' | sort -rn | cut -f2-)
  echo "macho_signed=$n"
  while IFS= read -r b; do codesign --force --sign - --timestamp=none "$b" >/dev/null 2>&1 || echo "WARN bundle sign failed: $b"; done < <(
    find "$A" -mindepth 2 -type d \( -name '*.framework' -o -name '*.app' -o -name '*.xpc' -o -name '*.bundle' \) -print | awk '{print length "\t" $0}' | sort -rn | cut -f2-)
  codesign --force --sign - --timestamp=none "$A"
  echo "--- 재서명 후 검증 (설치기 S03 과 같은 검사)"; codesign --verify --deep --strict --verbose=4 "$A" 2>&1; echo "after_verify_exit=$?"
  hdiutil create -quiet -volname "Wave Terminal" -srcfolder "$W/stage" -ov -format UDZO "$OUT"
  echo "output_dmg_sha256=$(shasum -a 256 "$OUT" | awk '{print $1}')"
  hdiutil attach -nobrowse -readonly -mountpoint "$MP" "$OUT" >/dev/null
  APP2="$(find "$MP" -maxdepth 2 -type d -name '*.app' -print -quit)"
  codesign --verify --deep --strict "$APP2" && echo "dmg_verify=ok"
  echo "cdhash=$(codesign -dvvv "$APP2" 2>&1 | sed -n 's/^CDHash=//p' | head -1)"
  hdiutil detach "$MP" >/dev/null
} > "$LOG" 2>&1
rm -rf "$W"; grep -q '^dmg_verify=ok' "$LOG"
