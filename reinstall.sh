#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
WAVE_HOME="${WAVE_HOME:-${HOME}/.wave}"
mode=execute
for arg in "$@"; do
  case "$arg" in
    --list|--dry-run) mode=list ;;
    --help|-h) printf '%s\n' '사용법: reinstall.sh [--list|--dry-run]'; exit 0 ;;
    *) printf '알 수 없는 인수: %s\n' "$arg" >&2; exit 2 ;;
  esac
done
# 소유 manifest 없는 앱/pack은 삭제하지 않는다. 상태 스키마만 재설치 대상으로 인정한다.
python3 - "$WAVE_HOME" "$HOME" "$mode" <<'PY_CLEANUP'
import datetime, json, os, pathlib, sys
root, home = pathlib.Path(sys.argv[1]).absolute(), pathlib.Path(sys.argv[2]).resolve()
if root.is_symlink() or root.resolve() == home or home not in root.resolve().parents:
    raise SystemExit('재설치 경로는 사용자 홈 내부의 일반 디렉터리여야 합니다.')
if root.resolve() != root:
    raise SystemExit('심링크/상대 구성요소가 포함된 재설치 경로는 보존하고 중단합니다.')
state = root / 'install-state.json'
print('백업 이동 대상: ' + str(state) + ' (wave-install.state.v1 스키마 확인 시)')
print('보존: 앱·bin·pack·로그·사용자 파일 전체. 소유 manifest 부재로 삭제하지 않습니다.')
print('정리: 현재 설치 프로세스의 WAVE_ENABLE_DAEMON만 해제; 셸 설정은 보존.')
if state.exists() or state.is_symlink():
    if state.is_symlink() or not state.is_file():
        raise SystemExit('상태 파일이 일반 파일이 아니므로 보존하고 중단합니다.')
    try:
        data = json.loads(state.read_text(encoding='utf-8-sig'))
    except (ValueError, OSError):
        raise SystemExit('상태 파일 해석 실패: 원본을 보존하고 중단합니다.')
    if not isinstance(data, dict) or data.get('schema') != 'wave-install.state.v1' or data.get('product') != 'Wave Terminal' or not isinstance(data.get('steps'), dict):
        raise SystemExit('설치기 상태 스키마 불일치: 원본을 보존하고 중단합니다.')
    if sys.argv[3] == 'execute':
        stamp = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
        backup = root / ('reinstall-backup-' + stamp)
        backup.mkdir(mode=0o700)
        state.rename(backup / state.name)
        print('백업 완료: ' + str(backup / state.name))
PY_CLEANUP
[[ "$mode" == list ]] && exit 0
unset WAVE_ENABLE_DAEMON
exec bash "$SCRIPT_DIR/bootstrap.sh" --reinstall
