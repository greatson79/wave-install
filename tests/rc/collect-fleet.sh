#!/usr/bin/env bash
# 러너 증거: 설치기가 남긴 시도·좌석 기록 전체 — $WAVE_HOME/fleet/(started-at·status.json·master-ref·declared·before.json …)·install.log·attempt-started.
# 판정(verify_live_fleet)이 거짓이었던 이유를 재계산이 아니라 설치기가 실제 쓴 값으로 확정하기 위한 직접 증거. 없는 파일은 건너뛴다(항상 0 으로 끝남).
#  collect-fleet.sh <증거 폴더>   → <증거 폴더>/fleet/ · install.log · attempt-started
out="$1/fleet"; mkdir -p "$out"
cp -R "$HOME/.wave/fleet/." "$out/" 2>/dev/null
cp "$HOME/.wave/install.log" "$1/install.log" 2>/dev/null
cp "$HOME/.wave/attempt-started" "$1/attempt-started" 2>/dev/null
exit 0
