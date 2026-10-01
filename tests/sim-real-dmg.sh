#!/usr/bin/env bash
# 실 DMG 시뮬레이션: 로컬 빌드(재서명) DMG 를 https 자산 URL 대신 로컬 파일로 받아, 실제 hdiutil·codesign·ditto 로 S03·S04 를 돈다.
# 사용: tests/sim-real-dmg.sh <wave-terminal-0.1.1-macos-arm64.dmg>   (steps.json 의 고정 SHA256·CDHash 와 대조됨)
# 실 네트워크·실 ~/.claude·~/.cys·launchctl 없음(격리 HOME · claude 만 가짜 · 데몬 등록 생략).
set -euo pipefail
DMG="${1:?DMG 경로}"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
SIM="$(mktemp -d /tmp/wave-v02-sim.XXXXXX)"; H="$SIM/home"; ST="$SIM/stubs"; FK="$SIM/fake"
mkdir -p "$H" "$ST" "$FK"; cp "$DMG" "$FK/asset.dmg"
bash "$ROOT/scripts/make-release.sh" 0.2.0 "file://$SIM/rel" "$SIM/rel" >"$SIM/make-release.log"
cat > "$ST/claude" <<'S'
#!/bin/bash
case "$1" in --version) echo 2.1.300 ;; auth) [ "$2" = login ] && touch "$FAKE/in"; [ "$2" = status ] && { [ -f "$FAKE/in" ] || exit 1; }; exit 0 ;; esac
S
cat > "$ST/curl" <<'S'
#!/bin/bash
out=""; url=""; while [ $# -gt 0 ]; do case "$1" in --output) out="$2"; shift ;; http*|file*) url="$1" ;; esac; shift; done
case "$url" in file://*) cp "${url#file://}" "$out" ;; https://github.com/greatson79/wave-terminal/*) cp "$FAKE/asset.dmg" "$out" ;; *) echo "예상 밖 URL: $url" >&2; exit 9 ;; esac
S
chmod +x "$ST"/*
cp "$SIM/rel/bootstrap.sh" "$H/install-wave.sh"   # 한 줄 명령이 받는 단독 파일(주입본)
set +e
HOME="$H" WAVE_HOME="$H/.wave" FAKE="$FK" PATH="$ST:/usr/bin:/bin:/usr/sbin:/sbin" WAVE_ENABLE_DAEMON=0 \
  bash "$H/install-wave.sh" 2>&1 | tee "$SIM/run.log"
echo "SIM_DIR=$SIM"
