#!/usr/bin/env bash
# 로컬 시뮬레이션: 격리 HOME 에서 bootstrap.sh "단독 복사본"만으로 file:// 설치팩을 받아 S06 까지 진행.
# 실 네트워크·실 ~/.claude·sudo 없음. 가짜 claude/curl(자산)/hdiutil/codesign 스텁.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
SIM="$(mktemp -d /tmp/wave-v02-sim.XXXXXX)"; H="$SIM/home"; ST="$SIM/stubs"; FK="$SIM/fake"
mkdir -p "$H" "$ST" "$FK" "$SIM/rel/wave-install-0.2.1"
# 가짜 릴리스 산출물
cp -R "$ROOT/bootstrap.sh" "$ROOT/steps.json" "$ROOT/install-state.json" "$ROOT/wave-pack" "$SIM/rel/wave-install-0.2.1/"
printf 'fake-dmg' > "$FK/asset.dmg"; DSHA="$(shasum -a 256 "$FK/asset.dmg" | awk '{print $1}')"
python3 - "$SIM/rel/wave-install-0.2.1/steps.json" "$DSHA" <<'PY'
import json, sys
p, d = sys.argv[1:]; s = json.load(open(p))
for k in ("macos_arm64", "macos_x64"): s["release"]["sha256"][k] = d
json.dump(s, open(p, "w"), ensure_ascii=False, indent=2)
PY
tar -czf "$SIM/wave-install-0.2.1.tar.gz" -C "$SIM/rel" wave-install-0.2.1
TSHA="$(shasum -a 256 "$SIM/wave-install-0.2.1.tar.gz" | awk '{print $1}')"
# 스텁
cat > "$ST/claude" <<'S'
#!/bin/bash
case "$1" in --version) echo 2.1.300 ;; auth) [ -f "$FAKE/in" ] || { [ "$2" = login ] && touch "$FAKE/in"; [ "$2" = status ] && exit 1; }; exit 0 ;; esac
S
cat > "$ST/curl" <<'S'
#!/bin/bash
out=""; url=""; while [ $# -gt 0 ]; do case "$1" in --output) out="$2"; shift ;; http*|file*) url="$1" ;; esac; shift; done
case "$url" in file://*) cp "${url#file://}" "$out" ;; *) cp "$FAKE/asset.dmg" "$out" ;; esac
S
cat > "$ST/hdiutil" <<'S'
#!/bin/bash
if [ "$1" = attach ]; then while [ $# -gt 0 ]; do [ "$1" = -mountpoint ] && mp="$2"; shift; done
  a="$mp/Wave Terminal.app/Contents/MacOS"; mkdir -p "$a"; printf '#!/bin/sh\necho 0.0.0\n' > "$a/cys"; printf '#!/bin/sh\nexit 0\n' > "$a/cysd"; chmod +x "$a/cys" "$a/cysd"; fi
S
printf '#!/bin/bash\nexit 0\n' > "$ST/codesign"
chmod +x "$ST"/*
# 실행: 한 줄 명령이 받는 파일 하나만 홈에 둔다
cp "$ROOT/bootstrap.sh" "$H/install-wave.sh"
set +e
HOME="$H" WAVE_HOME="$H/.wave" FAKE="$FK" PATH="$ST:/usr/bin:/bin:/usr/sbin:/sbin" WAVE_ENABLE_DAEMON=0 \
  WAVE_INSTALL_TARBALL_URL="file://$SIM/wave-install-0.2.1.tar.gz" WAVE_INSTALL_TARBALL_SHA256="$TSHA" \
  bash "$H/install-wave.sh" 2>&1 | tee "$SIM/run.log"
echo "SIM_DIR=$SIM"
