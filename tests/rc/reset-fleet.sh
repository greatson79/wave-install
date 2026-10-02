#!/usr/bin/env bash
# 합성 좌석(sleep 86400 · 이름 claude)과 마스터 마커를 정리한다 — 업그레이드/재설치 전 상태 되돌림. 러너 전용.
pkill -f 'local/bin/claude' 2>/dev/null; pkill -x cysd 2>/dev/null; rm -f "$HOME/.cys/.master-bootstrapped"; rm -rf "$HOME/.wave/rc" "$HOME/.cys/state/boot-last.json"; rm -f "$HOME/.wave/verify"/hook_*.out "$HOME/.wave/verify"/G3_inject.json  # 이전 설치의 증거가 다음 측정에 섞이지 않게
sleep 2; true
