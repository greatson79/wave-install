#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"

if [[ "${1:-}" == "--list" ]]; then
  cat <<'EOF'
reinstall.sh 계획(기본은 실행하지 않음):
1. ~/.wave/install-state.json을 타임스탬프 백업
2. 기존 pack·로그는 보존
3. bootstrap.sh --reinstall로 S00부터 재검증
4. S09에서 필수 단계 실측 후에만 complete 기록
EOF
  exit 0
fi

exec bash "$SCRIPT_DIR/bootstrap.sh" --reinstall "$@"
