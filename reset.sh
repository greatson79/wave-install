#!/usr/bin/env bash
set -euo pipefail

TARGET="wave"
APPLY=0

usage() {
  cat <<'EOF'
사용법: reset.sh --list [--target wave|pack|all]
       reset.sh --apply --target wave|pack|all

기본 동작은 --list이며 삭제하지 않는다. --apply를 명시해야만 지정된 사용자 폴더를 초기화한다.
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --list) ;;
    --apply) APPLY=1 ;;
    --target) shift; TARGET="${1:-}" ;;
    --help|-h) usage; exit 0 ;;
    *) usage >&2; exit 2 ;;
  esac
  shift
done

case "$TARGET" in
  wave) TARGETS=("$HOME/.wave") ;;
  pack) TARGETS=("$HOME/.cys/pack") ;;
  all) TARGETS=("$HOME/.wave" "$HOME/.cys/pack") ;;
  *) usage >&2; exit 2 ;;
esac

if [[ "$APPLY" != 1 ]]; then
  printf 'reset 대상(삭제하지 않음):\n'
  printf ' - %s\n' "${TARGETS[@]}"
  exit 0
fi

# Roll back before deleting .wave, which owns the journal. Pack-only is unrelated.
if [[ "$TARGET" == wave || "$TARGET" == all ]]; then
  SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
  python3 "$SCRIPT_DIR/lib/trust_seed.py" rollback "${CYS_ACCOUNT_DIR:-$HOME/.cys/claude}" "$HOME/.wave/trust-seed.tsv" "$HOME/.wave"
fi

printf 'reset 적용 대상:\n'
printf ' - %s\n' "${TARGETS[@]}"
for target in "${TARGETS[@]}"; do
  case "$target" in
    "$HOME/.wave"|"$HOME/.cys/pack") ;;
    *) printf '허용되지 않은 경로: %s\n' "$target" >&2; exit 1 ;;
  esac
  if [[ -e "$target" || -L "$target" ]]; then
    rm -rf -- "$target"
  fi
done
printf 'reset 완료: 지정된 사용자 폴더만 제거됨\n'
