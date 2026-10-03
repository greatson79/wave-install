#!/usr/bin/env bash
set -euo pipefail

# Wave Install S3. 실제 릴리스·설치 실행은 S5 검증 창에서만 수행한다.

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
WAVE_HOME="${WAVE_HOME:-${HOME}/.wave}"
PACK_HOME="${HOME}/.cys/pack"
STEPS_FILE="${SCRIPT_DIR}/steps.json"
STATE_TEMPLATE="${SCRIPT_DIR}/install-state.json"
STATE_FILE="${WAVE_HOME}/install-state.json"
LOG_FILE="${WAVE_HOME}/install.log"
# 릴리스 때 채우는 값 — bootstrap.sh 한 파일만 받아도 설치팩(tarball)을 스스로 받아 푼다.
# 테스트·시뮬레이션만 WAVE_INSTALL_TARBALL_URL/SHA256 으로 덮어쓴다(file:// 허용).
WAVE_TARBALL_URL="${WAVE_INSTALL_TARBALL_URL:-__WAVE_TARBALL_URL__}"
WAVE_TARBALL_SHA256="${WAVE_INSTALL_TARBALL_SHA256:-__WAVE_TARBALL_SHA256__}"
CLAUDE_INSTALL_URL="${WAVE_CLAUDE_INSTALL_URL:-https://claude.ai/install.sh}"
CLAUDE_DIRECT_BASE_URL="${WAVE_CLAUDE_DIRECT_BASE_URL:-https://downloads.claude.ai/claude-code-releases}"
REINSTALL=0
RESUME=0
DRY_RUN=0
STEP_OBSERVED='{}'
STEP_STATUS="passed"
# 설치 도움(R5): 첫 화면 고지 뒤에만 전송. 기본 주소는 WAVE_HELP_BASE_URL 로 교체, WAVE_NO_PROGRESS=1 이면 진행·도움 모두 끈다.
HELP_NOTICE_SHOWN=0
HELP_INTERACTIVE=0
HELP_PROGRESS_WARNED=0
# 진행 신호 시간 상한: 호출 1회 벽시계(DNS 포함, 초과 시 자식 종료) · 설치 1회 누적 예산(다 쓰면 이번 설치에서는 끈다).
HELP_PROGRESS_CALL_CAP=3
HELP_PROGRESS_BUDGET=15
HELP_PROGRESS_SPENT=0
HELP_STEP="1/10"
HELP_VERSION="unknown"

usage() {
  cat <<'EOF'
사용법: bootstrap.sh [--reinstall] [--resume] [--dry-run]

--reinstall  기존 상태를 백업하고 사용자 폴더 설치 흐름을 처음부터 다시 시작
--resume     이미 통과한 단계는 건너뛰고 pending/failed 단계부터 재개
--dry-run    설치·네트워크·로그인·데몬을 실행하지 않고 계약 위치만 표시
EOF
}

log() {
  printf '[%s] %s\n' "$(date -u '+%Y-%m-%dT%H:%M:%SZ')" "$*" >&2
}

fail_message() {
  log "실패: $*"
  return 1
}

require_command() {
  command -v "$1" >/dev/null 2>&1 || fail_message "필수 명령 없음: $1"
}

assert_user_path() {
  case "$1" in
    "$HOME"|"$HOME"/*) ;;
    *) fail_message "사용자 폴더 밖 경로는 허용하지 않음: $1"; return 1 ;;
  esac
}

help_enabled() {
  [[ "${WAVE_NO_PROGRESS:-}" != 1 && "$HELP_NOTICE_SHOWN" == 1 && -f "$SCRIPT_DIR/lib/install_help_client.py" ]]
}

# 수집 항목·목적·30일 보관 고지. 이 함수가 끝나야 전송이 열린다(대화형 여부도 여기서 — tee 연결 전에 판정).
show_help_notice() {
  [[ "${WAVE_NO_PROGRESS:-}" == 1 ]] && return 0
  [[ -f "$SCRIPT_DIR/lib/help-notice.txt" && -f "$SCRIPT_DIR/lib/install_help_client.py" ]] || return 0
  if [[ -t 0 && -t 1 ]]; then HELP_INTERACTIVE=1; fi
  cat -- "$SCRIPT_DIR/lib/help-notice.txt"
  HELP_NOTICE_SHOWN=1
}

# 진행 신호(8KB). 호출 1회는 client 안에서 3초 벽시계, 바깥에서 자식 프로세스 전체를 CALL_CAP+2초로 끊는다.
# 실패는 CALL_CAP초로 쳐서 누적하고, 누적이 BUDGET초에 닿으면 이번 설치에서는 더 보내지 않는다.
# 실패해도 한 번만 알리고 설치를 계속한다. 본문·오류 원문은 출력하지 않는다.
help_progress() {
  help_enabled || return 0
  (( HELP_PROGRESS_SPENT < HELP_PROGRESS_BUDGET )) || return 0
  local rc=0 began=$SECONDS used
  WAVE_COMMAND_TIMEOUT=$((HELP_PROGRESS_CALL_CAP + 2)) bounded_command python3 "$SCRIPT_DIR/lib/install_help_client.py" \
    progress --notice-shown --version "$HELP_VERSION" \
    --step "$HELP_STEP" --event "$1" --detail "${2:-}" </dev/null >/dev/null 2>&1 || rc=$?
  used=$((SECONDS - began))
  if [[ "$rc" -ne 0 && "$used" -lt "$HELP_PROGRESS_CALL_CAP" ]]; then used=$HELP_PROGRESS_CALL_CAP; fi
  HELP_PROGRESS_SPENT=$((HELP_PROGRESS_SPENT + used))
  if [[ "$rc" -ne 0 && "$HELP_PROGRESS_WARNED" == 0 ]]; then
    HELP_PROGRESS_WARNED=1
    log 'progress send failed (fail-open); 설치를 계속합니다.'
  fi
  if (( HELP_PROGRESS_SPENT >= HELP_PROGRESS_BUDGET )); then
    log "진행 신호 시간 예산(${HELP_PROGRESS_BUDGET}초)을 다 써서 이번 설치에서는 진행 신호를 보내지 않습니다. 설치는 계속합니다."
  fi
  return 0
}

# 최종 막힘 도움 요청. 대화형이면 처방 글을 기다려 표시만 한다. 어떤 결과든 호출자 종료값은 바꾸지 않는다.
help_request() {
  help_enabled || return 0
  local -a mode=()
  [[ "$HELP_INTERACTIVE" == 1 ]] && mode=(--interactive)
  python3 "$SCRIPT_DIR/lib/install_help_client.py" help --notice-shown --version "$HELP_VERSION" \
    --step "$HELP_STEP" --code J-UNK-00 --log-file "$LOG_FILE" ${mode[@]+"${mode[@]}"} 2>/dev/null || true
  return 0
}

# steps.json·wave-pack 이 옆에 없으면(= curl 한 파일만 받은 경우) 고정 SHA256 tarball 을 받아 풀고 그 안에서 재실행한다.
ensure_pack() {
  [[ -f "$SCRIPT_DIR/steps.json" && -d "$SCRIPT_DIR/wave-pack" ]] && return 0
  local url="$WAVE_TARBALL_URL" want="$WAVE_TARBALL_SHA256" src="$WAVE_HOME/src" tgz proto got
  [[ "$url" == __*__ || "$want" == __*__ ]] && fail_message "설치팩 URL·SHA256 이 릴리스 때 채워지지 않음" && return 1
  [[ "$want" =~ ^[0-9a-f]{64}$ ]] || fail_message "설치팩 SHA256 형식 오류" || return 1
  case "$url" in https://*) proto='=https' ;; file://*) proto='=file' ;; *) fail_message "설치팩 URL은 https:// 여야 함"; return 1 ;; esac
  require_command curl || return 1; require_command shasum || return 1; require_command tar || return 1
  log "설치팩을 내려받습니다: $url"
  rm -rf -- "$src"; mkdir -p "$src"; tgz="$src/wave-install.tar.gz"
  curl --fail --silent --show-error --location --proto "$proto" --tlsv1.2 "$url" --output "$tgz" || return 1
  got="$(shasum -a 256 "$tgz" | awk '{print $1}')"
  [[ "$got" == "$want" ]] || fail_message "설치팩 SHA256 불일치" || return 1
  if tar -tzf "$tgz" | grep -Eq '(^/|(^|/)\.\.(/|$))'; then fail_message "설치팩에 위험한 경로가 있음"; return 1; fi
  mkdir -p "$src/pack"
  tar -xzf "$tgz" -C "$src/pack" --strip-components=1 || return 1
  [[ -f "$src/pack/bootstrap.sh" && -f "$src/pack/steps.json" && -d "$src/pack/wave-pack" ]] || fail_message "설치팩 구성이 올바르지 않음" || return 1
  log "설치팩 확인 완료 — $src/pack 에서 다시 시작합니다."
  exec bash "$src/pack/bootstrap.sh" "$@"
}

load_config() {
  if [[ -f "$STEPS_FILE" ]]; then
    return 0
  fi
  local config_url="${WAVE_INSTALL_STEPS_URL:-https://raw.githubusercontent.com/greatson79/wave-install/main/steps.json}"
  [[ "$config_url" == __*__ ]] && fail_message "steps.json URL이 S5 전 배포 자리표시자 상태임" && return 1
  require_command curl || return 1
  [[ "$config_url" == https://* ]] || fail_message "steps.json은 HTTPS URL이어야 함" || return 1
  mkdir -p "$WAVE_HOME/config"
  curl --fail --silent --show-error --location --proto '=https' --tlsv1.2 "$config_url" --output "$WAVE_HOME/config/steps.json" || return 1
  STEPS_FILE="$WAVE_HOME/config/steps.json"
}

json_value() {
  local file="$1"
  local path="$2"
  python3 - "$file" "$path" <<'PY'
import json
import sys

with open(sys.argv[1], encoding="utf-8") as handle:
    value = json.load(handle)
for part in sys.argv[2].split("."):
    value = value[part]
if value is None:
    print("null")
elif isinstance(value, (dict, list)):
    print(json.dumps(value, ensure_ascii=False, separators=(",", ":")))
else:
    print(value)
PY
}

step_error_id() {
  python3 - "$STEPS_FILE" "$1" <<'PY'
import json, sys
try:
    with open(sys.argv[1], encoding="utf-8") as handle:
        config = json.load(handle)
    steps = config.get("steps") if isinstance(config, dict) else None
    matches = [step for step in steps if isinstance(step, dict) and step.get("id") == sys.argv[2]] if isinstance(steps, list) else []
    on_fail = matches[0].get("on_fail") if len(matches) == 1 else None
    error_id = on_fail.get("error_id") if isinstance(on_fail, dict) else None
    if not isinstance(error_id, str) or not error_id.strip():
        raise ValueError("missing error id")
except (OSError, ValueError):
    print(f"단계 오류 ID 설정을 확인할 수 없음: {sys.argv[2]}", file=sys.stderr)
    sys.exit(1)
print(error_id)
PY
}

state_patch() {
  local step_id="$1"
  local status="$2"
  local exit_code="$3"
  local error_id="$4"
  local observed="${5-}"
  [[ -n "$observed" ]] || observed='{}'
  local now
  now="$(date -u '+%Y-%m-%dT%H:%M:%SZ')"
  python3 - "$STATE_FILE" "$STEPS_FILE" "$step_id" "$status" "$exit_code" "$error_id" "$observed" "$now" <<'PY'
import json
import sys

state_path, steps_path, step_id, status, exit_code, error_id, observed_raw, now = sys.argv[1:]
if status == "passed" and error_id:
    raise SystemExit("passed와 error_id를 함께 기록할 수 없음")
with open(state_path, encoding="utf-8") as handle:
    state = json.load(handle)
with open(steps_path, encoding="utf-8") as handle:
    steps = json.load(handle)
try:
    observed = json.loads(observed_raw)
except json.JSONDecodeError:
    observed = {"raw": observed_raw}
entry = state["steps"][step_id]
entry["status"] = status
entry["exit_code"] = int(exit_code)
entry["error_id"] = error_id or None
entry["observed"] = observed
entry["checks"] = [f"exit_code={exit_code}"]
entry["started_at"] = entry["started_at"] or now
entry["completed_at"] = None if status == "running" else now
entry["version"] = steps.get("release", {}).get("version")
state["current_step"] = step_id if status == "running" else state.get("current_step")
state["updated_at"] = now
state["status"] = "running" if status == "running" else state.get("status", "running")
with open(state_path, "w", encoding="utf-8") as handle:
    json.dump(state, handle, ensure_ascii=False, indent=2)
    handle.write("\n")
PY
}

init_state() {
  assert_user_path "$WAVE_HOME" || return 1
  mkdir -p "$WAVE_HOME"
  if [[ "$REINSTALL" == 1 && -f "$STATE_FILE" ]]; then
    cp -- "$STATE_FILE" "${STATE_FILE}.bak.$(date -u '+%Y%m%dT%H%M%SZ')"
    cp -- "$STATE_TEMPLATE" "$STATE_FILE"
  elif [[ ! -f "$STATE_FILE" ]]; then
    cp -- "$STATE_TEMPLATE" "$STATE_FILE"
  fi
  python3 - "$STATE_FILE" "$WAVE_HOME" "$LOG_FILE" <<'PY'
import json
import sys
from pathlib import Path

state_path, wave_home, log_path = sys.argv[1:]
with open(state_path, encoding="utf-8") as handle:
    state = json.load(handle)
state["paths"]["state"] = str(Path(wave_home) / "install-state.json")
state["paths"]["log"] = str(Path(log_path))
state["paths"]["wave_home"] = str(Path(wave_home))
state["paths"]["pack"] = str(Path.home() / ".cys" / "pack")
state["created_at"] = state.get("created_at") or None
with open(state_path, "w", encoding="utf-8") as handle:
    json.dump(state, handle, ensure_ascii=False, indent=2)
    handle.write("\n")
PY
  touch "$LOG_FILE"
  exec > >(tee -a "$LOG_FILE") 2>&1
}

set_release_context() {
  local arch
  arch="$(uname -m)"
  case "$arch" in
    arm64|aarch64) RELEASE_PLATFORM="macos_arm64" ;;
    x86_64|amd64) RELEASE_PLATFORM="macos_x64" ;;
    *) fail_message "지원하지 않는 macOS 아키텍처: $arch"; return 1 ;;
  esac
  RELEASE_VERSION="$(json_value "$STEPS_FILE" 'release.version')"
  RELEASE_ASSET_NAME="$(json_value "$STEPS_FILE" "release.asset_name.$RELEASE_PLATFORM")"
  RELEASE_ASSET_URL="$(json_value "$STEPS_FILE" "release.asset_url.$RELEASE_PLATFORM")"
  RELEASE_EXPECTED_SHA256="$(json_value "$STEPS_FILE" "release.sha256.$RELEASE_PLATFORM")"
  for value in "$RELEASE_VERSION" "$RELEASE_ASSET_NAME" "$RELEASE_ASSET_URL" "$RELEASE_EXPECTED_SHA256"; do
    [[ "$value" == __*__ ]] && fail_message "S2 릴리스 자리표시자 잔존" && return 1
  done
  [[ "$RELEASE_ASSET_URL" == https://* ]] || fail_message "릴리스 asset URL은 HTTPS여야 함" || return 1
  [[ "$RELEASE_EXPECTED_SHA256" =~ ^[0-9a-f]{64}$ ]] || fail_message "S2 SHA256 값이 유효하지 않음" || return 1
  [[ "$RELEASE_ASSET_NAME" != */* ]] || fail_message "asset 파일명에 경로가 들어갈 수 없음" || return 1
  ARTIFACT_PATH="$WAVE_HOME/downloads/$RELEASE_ASSET_NAME"
}

step_s00() {
  require_command python3 || return 1
  require_command zsh || return 1
  require_command df || return 1
  [[ "$(uname -s)" == "Darwin" ]] || fail_message "macOS가 아님" || return 1
  local free_kb min_kb probe
  free_kb="$(df -Pk "$HOME" | awk 'NR==2 {print $4}')"
  min_kb=$(( $(json_value "$STEPS_FILE" 'tooling.min_free_bytes') / 1024 ))
  [[ "$free_kb" =~ ^[0-9]+$ && "$free_kb" -ge "$min_kb" ]] || fail_message "디스크 여유 공간 부족" || return 1
  mkdir -p "$WAVE_HOME"
  probe="$WAVE_HOME/.write-probe.$$"
  : > "$probe" || return 1
  rm -f -- "$probe"
  STEP_OBSERVED="$(python3 - "$free_kb" <<'PY'
import json, sys
print(json.dumps({"os": "macos", "shell": "zsh", "free_kb": int(sys.argv[1]), "user_path": True}))
PY
)"
}

# Claude Code 설치: 공식 install.sh → 안 되면 공식 배포 자리에서 직접 받기(manifest 해시 대조).
install_claude_direct() {
  local arch platform ver sum dl
  case "$(uname -m)" in arm64|aarch64) arch=arm64 ;; x86_64) arch=x64 ;; *) return 1 ;; esac
  [[ "$arch" == x64 && "$(sysctl -n sysctl.proc_translated 2>/dev/null)" == 1 ]] && arch=arm64
  platform="darwin-$arch"
  ver="$(curl -fsSL --max-time 60 "$CLAUDE_DIRECT_BASE_URL/stable" | tr -d '[:space:]')" || return 1
  [[ "$ver" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]] || return 1
  sum="$(curl -fsSL --max-time 60 "$CLAUDE_DIRECT_BASE_URL/$ver/manifest.json" | python3 -c 'import json,sys; print(json.load(sys.stdin)["platforms"][sys.argv[1]]["checksum"])' "$platform")" || return 1
  [[ "$sum" =~ ^[0-9a-f]{64}$ ]] || return 1
  mkdir -p "$WAVE_HOME/downloads"
  dl="$WAVE_HOME/downloads/claude-$ver-$platform"
  curl -fsSL --max-time 900 -o "$dl" "$CLAUDE_DIRECT_BASE_URL/$ver/$platform/claude" || return 1
  [[ "$(shasum -a 256 "$dl" | awk '{print $1}')" == "$sum" ]] || { rm -f "$dl"; fail_message "Claude Code 직접 받기 해시 불일치"; return 1; }
  chmod +x "$dl"
  "$dl" install stable </dev/null || return 1
}

install_claude() {
  local script="$WAVE_HOME/downloads/claude-install.sh"
  mkdir -p "$WAVE_HOME/downloads"
  log "Claude Code가 없어 공식 설치기로 설치합니다."
  if curl -fsSL --max-time 120 "$CLAUDE_INSTALL_URL" -o "$script" && bash "$script" </dev/null; then
    return 0
  fi
  log "공식 설치기가 막혀 공식 배포 자리에서 직접 받습니다."
  install_claude_direct
}

# 출력: ok | upgrade (정식 X.Y.Z 최소값 대비 SemVer 비교, 빌드 메타데이터 무시)
claude_version_gate() {
  python3 - "$1" "$2" <<'PY'
import re, sys
core = r'(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)'
actual = re.fullmatch(core + r'(?:-([0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?(?: \(Claude Code\))?', sys.argv[1])
minimum = re.fullmatch(core, sys.argv[2])
if not actual or not minimum:
    sys.exit(2)
pre = actual.group(4)
if pre and any(p.isdigit() and len(p) > 1 and p[0] == '0' for p in pre.split('.')):
    sys.exit(2)
a = tuple(map(int, actual.group(1, 2, 3)))
b = tuple(map(int, minimum.group(1, 2, 3)))
print('ok' if a > b or (a == b and not pre) else 'upgrade')
PY
}

step_s01() {
  local pin minimum version comparison installed=0 updated=0
  pin="$(json_value "$STEPS_FILE" 'tooling.claude_code_version')"
  if [[ "$pin" == __*__ ]]; then
    fail_message "Claude Code 버전 핀이 아직 정해지지 않음"
    return 1
  fi
  minimum="$(json_value "$STEPS_FILE" 'tooling.claude_code_min_version')" || return 1
  if [[ -z "$minimum" || "$minimum" == __*__ ]]; then
    fail_message "Claude Code 최소 버전 미정"
    return 1
  fi
  require_command curl || return 1
  PATH="$PATH:$HOME/.local/bin"
  if ! command -v claude >/dev/null 2>&1; then
    install_claude || { fail_message "Claude Code 설치 실패 — https://claude.ai/install.sh 를 직접 실행한 뒤 다시 시도하세요."; return 1; }
    hash -r
    command -v claude >/dev/null 2>&1 || { fail_message "Claude Code 설치 후에도 claude 명령을 찾지 못함"; return 1; }
    installed=1
  fi
  version="$(claude --version 2>/dev/null)" || return 1
  comparison="$(claude_version_gate "$version" "$minimum")" || { fail_message "Claude Code semver 형식 확인 불가"; return 1; }
  if [[ "$comparison" == upgrade ]]; then
    log "Claude Code $minimum 이상이 필요해 claude update를 실행합니다."
    claude update </dev/null || true
    hash -r
    version="$(claude --version 2>/dev/null)" || return 1
    comparison="$(claude_version_gate "$version" "$minimum")" || { fail_message "Claude Code semver 형식 확인 불가"; return 1; }
    [[ "$comparison" == ok ]] || { log "중단: claude update 후에도 $minimum 미만입니다($version). 터미널에서 claude update를 직접 실행한 뒤 다시 시도하세요."; return 1; }
    updated=1
  fi
  mkdir -p "$WAVE_HOME/tooling"
  printf '%s\n' "$version" > "$WAVE_HOME/tooling/claude.version"
  STEP_OBSERVED="$(python3 - "$version" "$installed" "$updated" <<'PY'
import json, sys
print(json.dumps({"claude_version": sys.argv[1], "installed": sys.argv[2] == "1", "updated": sys.argv[3] == "1"}))
PY
)"
}

step_s02() {
  PATH="$PATH:$HOME/.local/bin"
  if ! claude auth status >/dev/null 2>&1; then
    log "Claude 로그인이 필요합니다. 아래 안내대로 브라우저에서 승인하고, 코드가 나오면 이 창에 붙여넣으세요."
    if { : </dev/tty; } 2>/dev/null; then
      claude auth login </dev/tty >/dev/tty 2>&1 || true
    else
      claude auth login || true
    fi
    claude auth status >/dev/null 2>&1 || { log "로그인을 확인하지 못했습니다. 같은 명령을 다시 실행하면 이어서 진행합니다."; return 1; }
  fi
  mkdir -p "$WAVE_HOME/auth"
  : > "$WAVE_HOME/auth/claude-authenticated"
  STEP_OBSERVED='{"authenticated":true,"account_recorded":false}'
}

# CDHash 핀은 steps.json 단일 정본에서 온다. 비었거나 null·자리표시자·형식 오류면 건너뛰지 않고 중단한다.
release_cdhash_pin() {
  local pin
  pin="$(json_value "$STEPS_FILE" "release.cdhash.$RELEASE_PLATFORM" 2>/dev/null)" || pin=""
  [[ "$pin" =~ ^[0-9a-f]{40}$ ]] || { fail_message "앱 CDHash 핀 미확정: steps.json release.cdhash.$RELEASE_PLATFORM"; return 1; }
  printf '%s\n' "$pin"
}

step_s03() {
  require_command curl || return 1
  require_command shasum || return 1
  require_command hdiutil || return 1
  require_command codesign || return 1
  set_release_context || return 1
  local actual want_cdhash mp app got_cdhash
  want_cdhash="$(release_cdhash_pin)" || return 1
  mkdir -p "$WAVE_HOME/downloads"
  curl --fail --silent --show-error --location --proto '=https' --tlsv1.2 "$RELEASE_ASSET_URL" --output "$ARTIFACT_PATH" || return 1
  actual="$(shasum -a 256 "$ARTIFACT_PATH" | awk '{print $1}')"
  [[ "$RELEASE_EXPECTED_SHA256" == "$actual" ]] || fail_message "SHA256 불일치(고정값과 다름)" || return 1
  # 서명 검증: DMG 안 앱을 읽기 전용으로 잠시 열어 codesign 으로 확인한다(S04가 같은 앱을 설치).
  mp="$WAVE_HOME/verify-mount"
  mkdir -p "$mp"
  hdiutil attach -nobrowse -readonly -mountpoint "$mp" "$ARTIFACT_PATH" >/dev/null || return 1
  app="$(find "$mp" -maxdepth 2 -type d -name '*.app' -print -quit)"
  if [[ -z "$app" ]] || ! codesign --verify --deep --strict "$app" >/dev/null 2>&1; then
    hdiutil detach "$mp" >/dev/null 2>&1 || true
    fail_message "앱 서명(codesign) 검증 실패"
    return 1
  fi
  got_cdhash="$(codesign -dvvv "$app" 2>&1 | sed -n 's/^CDHash=//p' | head -1)"
  if [[ "$got_cdhash" != "$want_cdhash" ]]; then
    hdiutil detach "$mp" >/dev/null 2>&1 || true
    fail_message "앱 CDHash 불일치"
    return 1
  fi
  hdiutil detach "$mp" >/dev/null 2>&1 || true
  STEP_OBSERVED="$(python3 - "$RELEASE_PLATFORM" "$RELEASE_ASSET_NAME" "$actual" "$got_cdhash" <<'PY'
import json, sys
print(json.dumps({"platform": sys.argv[1], "asset": sys.argv[2], "sha256": sys.argv[3], "codesign_verified": True,
                  "cdhash": sys.argv[4]}))
PY
)"
}

step_s04() {
  require_command hdiutil || return 1
  require_command ditto || return 1
  require_command cmp || return 1
  set_release_context || return 1
  [[ -f "$ARTIFACT_PATH" ]] || fail_message "검증된 artifact 없음" || return 1
  local mountpoint app_dest app cys_target cysd_target hook
  mountpoint="$WAVE_HOME/mount"
  mkdir -p "$mountpoint" "$WAVE_HOME/apps" "$WAVE_HOME/bin" "$WAVE_HOME/shell"
  hdiutil attach -nobrowse -readonly -mountpoint "$mountpoint" "$ARTIFACT_PATH" >/dev/null || return 1
  app="$(find "$mountpoint" -maxdepth 2 -type d -name '*.app' -print -quit)"
  [[ -n "$app" ]] || { hdiutil detach "$mountpoint" >/dev/null 2>&1 || true; fail_message "DMG 안에 앱이 없음"; return 1; }
  app_dest="$WAVE_HOME/apps/Wave Terminal.app"
  rm -rf -- "$app_dest"
  ditto "$app" "$app_dest" || { hdiutil detach "$mountpoint" >/dev/null 2>&1 || true; return 1; }
  # 검증된 DMG의 원본과 복사본을 대조한다. cysd는 S04에서 실행하지 않는다.
  cmp -s "$app/Contents/MacOS/cysd" "$app_dest/Contents/MacOS/cysd" || {
    hdiutil detach "$mountpoint" >/dev/null 2>&1 || true
    fail_message "cysd 복사본 무결성 불일치"
    return 1
  }
  hdiutil detach "$mountpoint" >/dev/null 2>&1 || true
  cys_target="$app_dest/Contents/MacOS/cys"
  cysd_target="$app_dest/Contents/MacOS/cysd"
  [[ -f "$cys_target" && -x "$cys_target" && -f "$cysd_target" && -x "$cysd_target" ]] || fail_message "cys/cysd 실행 파일 없음" || return 1
  ln -sfn "$cys_target" "$WAVE_HOME/bin/cys" || return 1
  ln -sfn "$cysd_target" "$WAVE_HOME/bin/cysd" || return 1
  [[ -L "$WAVE_HOME/bin/cysd" && "$(readlink "$WAVE_HOME/bin/cysd")" == "$cysd_target" && -f "$WAVE_HOME/bin/cysd" && -x "$WAVE_HOME/bin/cysd" ]] || fail_message "cysd 심링크 검증 실패" || return 1
  hook="$WAVE_HOME/shell/wave-terminal.zsh"
  printf 'export PATH="%s:$PATH"\n' "$WAVE_HOME/bin" > "$hook"
  touch "$HOME/.zprofile"
  if ! grep -Fq "$hook" "$HOME/.zprofile"; then
    printf '\n# Wave Terminal S3\n[ -f %q ] && source %q\n' "$hook" "$hook" >> "$HOME/.zprofile"
  fi
  "$WAVE_HOME/bin/cys" --version >/dev/null || return 1
  zsh -f -c "source '$hook'; command -v cys" | grep -Fq "$WAVE_HOME/bin/cys" || return 1
  STEP_OBSERVED='{"cys":true,"cysd":true,"cysd_check":"file+executable+symlink+copy-match","shell_link":true,"admin_required":false}'
}

# Bounded child commands: timeout is a failed measurement, never success.
bounded_command() {
  python3 - "$@" <<'PY_BOUND'
import os, subprocess, sys
try:
    result = subprocess.run(sys.argv[1:], timeout=float(os.environ.get("WAVE_COMMAND_TIMEOUT", "30")))
    sys.exit(result.returncode)
except subprocess.TimeoutExpired:
    print("cys command timed out", file=sys.stderr)
    sys.exit(124)
PY_BOUND
}

bounded_cys() { bounded_command "$WAVE_HOME/bin/cys" "$@"; }

awakening_command() {
  local deadline="$1" remaining
  shift
  remaining=$((deadline - SECONDS))
  (( remaining > 0 )) || return 124
  (( remaining > 30 )) && remaining=30
  WAVE_COMMAND_TIMEOUT="$remaining" bounded_command "$@"
}

step_s05() {
  mkdir -p "$WAVE_HOME/install"
  local registered=false ready=false attempt
  if bounded_cys daemon install > "$WAVE_HOME/install/daemon-install.log" 2>&1; then registered=true; fi
  for attempt in 1 2 3; do
    if [[ "$(bounded_cys ping 2>/dev/null)" == pong ]]; then ready=true; break; fi
    sleep 1
  done
  if [[ "$ready" != true ]]; then
    # GUI owns the daemon lifecycle; do not leave an installer-owned background server.
    open "$WAVE_HOME/apps/Wave Terminal.app" || true
    for attempt in 1 2 3; do
      if [[ "$(bounded_cys ping 2>/dev/null)" == pong ]]; then ready=true; break; fi
      sleep 1
    done
  fi
  STEP_OBSERVED="{\"registered\":$registered,\"daemon_ready\":$ready,\"registration\":\"cys daemon install\"}"
  printf '%s\n' "$STEP_OBSERVED" > "$WAVE_HOME/install/daemon-register-result"
  [[ "$registered" == true ]] || STEP_STATUS="skipped_with_reason"
  [[ "$ready" == true ]] || { fail_message "데몬 응답 없음 — 각성 단계에서 재확인 필요"; return 1; }
}

step_s06() {
  local backup
  backup="$WAVE_HOME/backups/legacy-pack-$(date -u '+%Y%m%dT%H%M%SZ')-$$"
  python3 - "$SCRIPT_DIR/wave-pack" "$PACK_HOME" "$backup" <<'PY_BACKUP' || return 1
from pathlib import Path
import shutil, sys
source, target, backup = map(Path, sys.argv[1:])
if target.is_symlink() or (target / 'directives').is_symlink():
    raise SystemExit('pack/directives symlink refused')
for old in (source / 'directives').glob('*.md'):
    dest = target / 'directives' / old.name
    if dest.is_symlink():
        raise SystemExit('directive symlink refused')
    if dest.is_file() and dest.read_bytes() == old.read_bytes():
        saved = backup / 'directives' / old.name
        saved.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(dest), str(saved))
        sidecar = Path(str(dest) + '.new')
        if sidecar.is_file() and not sidecar.is_symlink():
            shutil.move(str(sidecar), str(saved) + '.new')
PY_BACKUP
  mkdir -p "$WAVE_HOME/verify"
  CYS_PACK_DIR="$PACK_HOME" bounded_cys init-pack || return 1
  bounded_cys pack-manifest > "$WAVE_HOME/verify/embedded-pack.json" || return 1
  python3 - "$PACK_HOME" "$WAVE_HOME/verify/embedded-pack.json" <<'PY_VERIFY' || return 1
import hashlib, json, sys
from pathlib import Path
pack, manifest = map(Path, sys.argv[1:])
files = json.loads(manifest.read_text())['files']
directives = {k:v for k,v in files.items() if k.startswith('directives/') and k.endswith('.md')}
if not directives:
    raise SystemExit('embedded directive manifest empty')
for rel, expected in directives.items():
    path = pack / rel
    if '..' in Path(rel).parts or path.is_symlink() or not path.is_file():
        raise SystemExit('invalid/missing directive: '+rel)
    if hashlib.sha256(path.read_bytes()).hexdigest() != expected:
        raise SystemExit('custom/mismatched directive preserved; merge required: '+rel)
# preflight-product-profile.json is seed-once and user-owned in the app (written only when missing, never
# overwritten). A user edit/revert is a legitimate state, so its sidecar never blocks the install; the
# installer leaves both files untouched. Every other .new still means a pending merge.
SEED_ONCE = {'preflight-product-profile.json.new'}
if [p for p in pack.rglob('*.new') if p.relative_to(pack).as_posix() not in SEED_ONCE]:
    raise SystemExit('pending .new files: merge required')
PY_VERIFY
  # cys-dept는 앱 번들 바이너리가 아니라 init-pack이 까는 팩 스크립트다. preflight C11b가 보는 그 자리
  # (cys 옆 $WAVE_HOME/bin)에 심링크한다. 사용자 실파일은 덮지 않는다(preflight와 같은 규약).
  local dept_src="$PACK_HOME/bin/cys-dept" dept_link="$WAVE_HOME/bin/cys-dept" dept_state="absent"
  if [[ -f "$dept_src" && ! -L "$dept_src" ]]; then
    if [[ -e "$dept_link" && ! -L "$dept_link" ]]; then
      dept_state="user_file_preserved"
    elif chmod +x "$dept_src" && ln -sfn "$dept_src" "$dept_link"; then
      dept_state="linked"
    else
      dept_state="link_failed"
    fi
  fi
  STEP_OBSERVED='{"pack_installed":true,"pack_provider":"cys init-pack","embedded_directives_verified":true,"pending_new":0,"cys_dept":"'"$dept_state"'"}'
}

# master 는 앱 계약대로 `cys launch-agent --role master` 로 띄운다(앱이 agent 정보를 기록하고 MASTER 지침을 주입한다).
step_s07() {
  mkdir -p "$WAVE_HOME/fleet"
  local ref started deadline remaining existing reused=false
  started="$(date +%s)"
  deadline=$((SECONDS + 420))
  awakening_command "$deadline" open "$WAVE_HOME/apps/Wave Terminal.app" || return 1
  wait_gui_onboarded "$deadline" || return 1
  awakening_command "$deadline" "$WAVE_HOME/bin/cys" status --json > "$WAVE_HOME/fleet/before.json" || return 1
  # 재실행·resume(Windows Run-S07 과 같은 동작): 이 설치가 앞서 만든 master(master-ref·started-at 기록과 일치,
  # 그 시각 이후 생성) 하나만 살아 있으면 새로 만들지 않고 재사용해 각성을 확인한다. 기록과 다른 master·둘 이상·
  # 기록 이전 생성 master 는 여전히 중복 생성 없이 중단한다.
  existing="$(python3 - "$WAVE_HOME/fleet/before.json" "$WAVE_HOME/fleet/master-ref" "$WAVE_HOME/fleet/started-at" <<'PY_EXISTING'
import json, re, sys
live = [s for s in json.load(open(sys.argv[1]))['surfaces'] if s.get('role') == 'master' and s.get('exited') is False]
if not live:
    sys.exit(0)
try:
    saved_ref = open(sys.argv[2]).read().strip()
    saved_started = int(open(sys.argv[3]).read().strip())
except (OSError, ValueError):
    saved_ref, saved_started = '', None
seat = live[0]
created = seat.get('created_at')
if (len(live) == 1 and re.fullmatch(r'surface:[0-9]+', saved_ref) and saved_started is not None
        and seat.get('surface_ref') == saved_ref and isinstance(created, (int, float)) and created >= saved_started):
    print(saved_ref, saved_started)
    sys.exit(0)
raise SystemExit('기존 master가 살아 있습니다(이 설치가 만든 좌석이 아니거나 둘 이상). 중복 생성 없이 설치를 중단합니다.')
PY_EXISTING
)" || return 1
  if [[ -n "$existing" ]]; then
    ref="${existing% *}"
    started="${existing#* }"
    reused=true
    log "이 설치가 앞서 만든 master($ref)를 재사용해 각성을 확인합니다."
  else
    # launch-agent 는 준비 표지(❯)·지침 주입까지 기다리므로 30초 상한(awakening_command)보다 길게 준다.
    remaining=$((deadline - SECONDS)); (( remaining > 120 )) && remaining=120
    ref="$(WAVE_COMMAND_TIMEOUT="$remaining" bounded_cys launch-agent --role master --agent claude --cwd "$HOME")" || return 1
    [[ "$ref" =~ ^surface:[0-9]+$ ]] || return 1
    printf '%s\n' "$ref" > "$WAVE_HOME/fleet/master-ref"
    printf '%s\n' "$started" > "$WAVE_HOME/fleet/started-at"
    # Claude Code 는 첫 입력 없이 움직이지 않는다 — 예전 wake 파일의 선언 문구를 한 줄로 큐 전달(대상이 조용해지면 자동 Return).
    # 선언 문구·「선언을 받는다」 축: oogisoogi/jarvis-install bootstrap.sh write_wake_file/step_wake (MIT, LICENSES/jarvis-install-MIT.txt).
    awakening_command "$deadline" "$WAVE_HOME/bin/cys" send --queued --to master \
      '너는 마스터다 — 설치된 팩의 마스터 부트 절차를 수행해 주세요. CSO와 작업 워커를 한 좌석씩 소환하고 각성을 확인해 주세요. 리뷰어 좌석은 설치 완료 조건에 포함하지 않습니다.' >/dev/null ||
      fail_message "J-PATH-02 — W-DECLARE: master 좌석에 선언 문구를 전달하지 못했습니다. 같은 설치 명령을 다시 실행하세요." || return 1
  fi
  while (( SECONDS < deadline )); do
    remaining=$((deadline - SECONDS))
    (( remaining > 5 )) && remaining=5
    if WAVE_COMMAND_TIMEOUT="$remaining" bounded_cys status --json > "$WAVE_HOME/fleet/status.json" &&
       verify_live_fleet "$ref" "$started" && (( SECONDS < deadline )); then
      STEP_OBSERVED="{\"seats\":3,\"roles\":[\"master\",\"cso\",\"worker\"],\"fleet_started\":true,\"master_marker_verified\":true,\"master_reused\":$reused}"
      return 0
    fi
    remaining=$((deadline - SECONDS))
    (( remaining <= 0 )) && break
    (( remaining > 2 )) && remaining=2
    sleep "$remaining"
  done
  fail_message "420초 안에 마스터 부트 표지·CSO·worker 생존을 확인하지 못했습니다"

}

# S07: 앱 첫 실행 온보딩(팩·훅 설치)이 끝난 뒤에 master 를 만든다 — 온보딩의 팩 교체와 좌석이 겹치지 않게.
# 표지 ~/.cys/.gui-onboarded 의 내용은 앱 버전이다(앱 needs_gui_onboard). 읽히면 `cys --version` 과 대조한다.
wait_gui_onboarded() {
  local marker="$HOME/.cys/.gui-onboarded" version limit=$((SECONDS + 180))
  (( limit < $1 )) || limit="$1"
  version="$(awakening_command "$1" "$WAVE_HOME/bin/cys" --version 2>/dev/null | awk '{print $NF}')" || version=""
  while (( SECONDS < limit )); do
    if [[ -f "$marker" ]]; then
      [[ -z "$version" || ! -r "$marker" || "$(tr -d '[:space:]' < "$marker")" == "$version" ]] && return 0
    fi
    sleep 1
  done
  fail_message "J-VER-02 — W-ONBOARD: Wave Terminal 첫 실행 준비(온보딩) 완료 표지를 확인하지 못했습니다. 앱 창을 열어 둔 채 같은 설치 명령을 --resume 으로 다시 실행하세요."
}

verify_live_fleet() {
  python3 - "$WAVE_HOME/fleet/status.json" "$HOME/.cys/.master-bootstrapped" "$1" "$2" <<'PY_LIVE'
import json, sys
from pathlib import Path
status, marker = map(Path, sys.argv[1:3]); ref, since = sys.argv[3:]
try:
    m = json.loads(marker.read_text())
    live = [s for s in json.loads(status.read_text())['surfaces'] if s.get('exited') is False and s.get('agent_alive') is True]
    masters = [s for s in live if s.get('surface_ref') == ref and s.get('role') == 'master']
    csos = [s for s in live if s.get('role') == 'cso' and s.get('created_at', 0) >= float(since)]
    children = [s for s in live if str(s.get('role', '')).startswith('worker') and s.get('created_at', 0) >= float(since)]
    ok = (marker.stat().st_mtime >= float(since) and m.get('orchestra_check') == 'exit 0'
          and str(m.get('surface_ref')) in {ref, ref.split(':')[1]} and masters and csos and children)
except (OSError, ValueError, KeyError, TypeError):
    ok = False
sys.exit(0 if ok else 1)
PY_LIVE
}

verify_original_injection() {
  bounded_cys pack-manifest > "$WAVE_HOME/verify/embedded-pack.json" || return 1
  python3 - "$PACK_HOME" "$WAVE_HOME/verify/embedded-pack.json" <<'PY_G3'
import hashlib, json, sys
from pathlib import Path
pack, manifest = map(Path, sys.argv[1:])
if pack.is_symlink() or (pack/'directives').is_symlink():
    raise SystemExit('G3 linked pack refused')
files=json.loads(manifest.read_text())['files']
required={'directives/'+r+'_DIRECTIVE.md' for r in ('MASTER','CSO','WORKER')}
directives={k:v for k,v in files.items() if k.startswith('directives/') and k.endswith('.md')}
if not required.issubset(directives):
    raise SystemExit('G3 manifest missing required directives')
result={}
for rel, expected in directives.items():
    source=pack/rel
    if '..' in Path(rel).parts or source.is_symlink() or not source.is_file():
        raise SystemExit('G3 missing/linked original: '+rel)
    data=source.read_bytes(); actual=hashlib.sha256(data).hexdigest()
    if not data or actual != expected:
        raise SystemExit('G3 installed original mismatch: '+rel)
    result[rel]=dict(pack_sha256=actual,pack_bytes=len(data))
# Same seed-once exception as S06 (user-owned product profile); any other .new fails.
if [p for p in pack.rglob('*.new') if p.relative_to(pack).as_posix() != 'preflight-product-profile.json.new']:
    raise SystemExit('G3 pending .new files')
print(json.dumps(dict(original_match=True,new_file_count=0,roles=result,
    injected_bytes=None,injection_reason='RC 러너 G3_inject.json 판정',
    source='app-manifest+installed-pack',fleet_verified=True)))
PY_G3
}

# 각성 증거(3갈래: 확인 / 미확인 카드 / 실패=위 생존·주입 검증). master 좌석 Claude 세션 기록(jsonl)에 답 레코드 ≥1.
# Adapted from oogisoogi/jarvis-install bootstrap.sh seat_session_file/seat_session_counts/master_assistant_count (MIT),
# axis (1) of Confirm-MasterAwake — commit df5efc8a, bootstrap.sh L4092-4127·L4242, bootstrap.ps1 L4808-4857·L5025.
# Source: https://github.com/oogisoogi/jarvis-install · License: LICENSES/jarvis-install-MIT.txt.
master_awake_state() {
  python3 - "$WAVE_HOME/fleet/status.json" "$1" "$2" "${CYS_ACCOUNT_DIR:-$HOME/.cys/claude}/projects" <<'PY_AWAKE'
import json, re, sys
from pathlib import Path
status, ref, since, root = sys.argv[1], sys.argv[2], float(sys.argv[3]), Path(sys.argv[4])
try:
    cwd = next(s['cwd'] for s in json.loads(Path(status).read_text())['surfaces'] if s.get('surface_ref') == ref)
    files = (root / re.sub(r'[^A-Za-z0-9]', '-', cwd)).glob('*.jsonl')
    ok = any(f.stat().st_mtime >= since and b'"type":"assistant"' in f.read_bytes() for f in files)
except (OSError, ValueError, KeyError, TypeError, StopIteration):
    ok = False
print('confirmed' if ok else 'unconfirmed')
PY_AWAKE
}

step_s08() {
  local ref started observed awake
  ref="$(cat "$WAVE_HOME/fleet/master-ref")" || return 1
  started="$(cat "$WAVE_HOME/fleet/started-at")" || return 1
  bounded_cys status --json > "$WAVE_HOME/fleet/status.json" || return 1
  verify_live_fleet "$ref" "$started" || return 1
  observed="$(verify_original_injection)" || return 1
  awake="$(master_awake_state "$ref" "$started")"
  if [[ "$awake" != confirmed ]]; then
    log "각성 미확인: master 좌석은 살아 있지만 Claude 세션 기록에서 답변을 찾지 못했습니다. 설치는 계속합니다. Wave Terminal 의 master 창에서 자비스가 응답하는지 확인해 주세요."
  fi
  STEP_OBSERVED="${observed%\}},\"master_awake\":\"$awake\"}"
}

summarize_state() {
  python3 - "$STATE_FILE" "$STEPS_FILE" "$1" <<'PY'
import json, sys
from datetime import datetime, timezone
path, steps_path, phase = sys.argv[1:]
with open(path, encoding="utf-8") as handle:
    state = json.load(handle)
with open(steps_path, encoding="utf-8") as handle:
    config = json.load(handle)

def bypass(value):
    if isinstance(value, dict):
        return bool(value.get("TEST_SYNTHETIC_BYPASS")) or any(bypass(v) for v in value.values())
    if isinstance(value, list):
        return any(bypass(v) for v in value)
    return value == "TEST_SYNTHETIC_BYPASS"

exceptions = []
if bypass({k: v for k, v in state.items() if k not in {"steps", "exceptions"}}):
    exceptions.append({"step_id": None, "reason": "TEST_SYNTHETIC_BYPASS"})
for step in config["steps"]:
    if phase != "final" and step["index"] >= 9:
        continue
    step_id = step["id"]
    entry = state["steps"].get(step_id)
    reasons = []
    if not isinstance(entry, dict):
        reasons.append("missing_step")
    else:
        if entry.get("error_id"):
            reasons.append("error_id")
            # 이전 판본/수동 상태의 모순을 보존 근거와 함께 정정한다.
            if entry.get("status") == "passed":
                entry["status"] = "failed"
        if entry.get("status") != "passed":
            reasons.append("status:" + str(entry.get("status")))
        if type(entry.get("exit_code")) is not int or entry["exit_code"] != 0:
            reasons.append("exit_code")
        if bypass(entry):
            reasons.append("TEST_SYNTHETIC_BYPASS")
        observed = entry.get("observed")
        observed = observed if isinstance(observed, dict) else {}
        if step_id == "S07_INITIAL_FLEET" and observed.get("fleet_started") is not True:
            reasons.append("fleet_unmeasured")
        if step_id == "S08_VERIFY":
            if observed.get("original_match") is not True:
                reasons.append("injection_original_unverified")
            count = observed.get("new_file_count")
            if type(count) is not int or count != 0:
                reasons.append("pending_new_unverified")
    for reason in reasons:
        exceptions.append({"step_id": step_id, "reason": reason})
state["required_steps_passed"] = not exceptions
state["exceptions"] = exceptions
state["updated_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
if phase == "final":
    state["status"] = "complete_with_exceptions" if exceptions else "complete"
    state["current_step"] = None
with open(path, "w", encoding="utf-8") as handle:
    json.dump(state, handle, ensure_ascii=False, indent=2)
    handle.write("\n")
PY
}

mark_required_complete() {
  summarize_state required
}

step_s09() {
  STEP_OBSERVED="$(python3 - "$STATE_FILE" "$WAVE_HOME/START-HERE.md" <<'PY'
import json, sys
from pathlib import Path
state = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
message = ("필수 단계 검증을 통과했습니다." if state["required_steps_passed"] else
           "설치 절차를 마무리했습니다. 예외·미검증 항목이 있으므로 전체 검증 완료가 아닙니다.")
Path(sys.argv[2]).write_text("# Wave Terminal 시작하기\n\n" + message +
    "\n\ninstall-state.json의 required_steps_passed·exceptions와 install.log를 확인하세요. "
    "원본 주입 증거가 없거나 .new가 남으면 완료로 처리하지 않습니다.\n", encoding="utf-8")
print(json.dumps({"required_steps_passed": state["required_steps_passed"],
                  "start_here": True, "silent_completion": False}))
PY
)" || return 1
}

mark_install_complete() {
  summarize_state final
}

run_step() {
  local step_id="$1"
  local function_name
  case "$step_id" in
    S00_PREFLIGHT) function_name="step_s00" ;;
    S01_CLAUDE_INSTALL) function_name="step_s01" ;;
    S02_CLAUDE_LOGIN) function_name="step_s02" ;;
    S03_DOWNLOAD_VERIFY) function_name="step_s03" ;;
    S04_INSTALL_LINK) function_name="step_s04" ;;
    S05_DAEMON_REGISTER) function_name="step_s05" ;;
    S06_PACK_INSTALL) function_name="step_s06" ;;
    S07_INITIAL_FLEET) function_name="step_s07" ;;
    S08_VERIFY) function_name="step_s08" ;;
    S09_COMPLETE) function_name="step_s09" ;;
    *) fail_message "알 수 없는 단계 ID: $step_id"; return 1 ;;
  esac
  STEP_OBSERVED='{}'
  STEP_STATUS="passed"
  help_progress start
  state_patch "$step_id" "running" 0 "" '{}'
  set +e
  local stderr_file
  stderr_file="$(mktemp "$WAVE_HOME/.step-stderr.XXXXXX")" || return 1
  "$function_name" 2>"$stderr_file"
  local rc=$?
  cat "$stderr_file" >&2
  cat "$stderr_file" >> "$LOG_FILE"
  set -e
  if [[ "$rc" -ne 0 ]]; then
    help_progress fail J-UNK-00
    # 상태 파일에는 가린 뒤 자른 stderr 끝부분(최대 4KB)만 남긴다. 원문 전체는 install.log 에만 있다.
    STEP_OBSERVED="$(python3 - "$STEP_OBSERVED" "$stderr_file" "$rc" "$SCRIPT_DIR/lib" <<'PY_REASON'
import json, os, re, sys
observed, path, rc, lib = json.loads(sys.argv[1]), sys.argv[2], sys.argv[3], sys.argv[4]
with open(path, "rb") as handle:
    handle.seek(0, os.SEEK_END)
    start = max(0, handle.tell() - 1024 * 1024)
    handle.seek(start)
    data = handle.read()
if start:
    data = data[data.find(b"\n") + 1:] if b"\n" in data else b""
text, user = data.decode("utf-8", "replace").strip(), os.environ.get("USER", "")
try:
    sys.path.insert(0, lib)
    from install_help import safe_text
    text = safe_text(text, user)
except Exception:
    home = os.path.expanduser("~")
    if len(home) > 1:
        text = text.replace(home, "~")
    if user:
        text = re.sub(r"(?<!\w)" + re.escape(user) + r"(?!\w)", "<USER>", text, flags=re.I)
raw = text.encode("utf-8")
if len(raw) > 4096:
    text = "..." + raw[-4096:].decode("utf-8", "ignore")
observed["reason"] = text or "step exited with code " + rc
print(json.dumps(observed, ensure_ascii=False))
PY_REASON
)"
    local optional
    optional="$(python3 - "$STEPS_FILE" "$step_id" <<'PY_OPTIONAL'
import json, sys
config = json.load(open(sys.argv[1], encoding="utf-8"))
print("true" if any(s["id"] == sys.argv[2] and s.get("optional") is True for s in config["steps"]) else "false")
PY_OPTIONAL
)"
    if [[ "$optional" == "true" ]]; then
      state_patch "$step_id" "skipped_with_reason" "$rc" "$(step_error_id "$step_id")" "$STEP_OBSERVED"
      log "[$step_id] 선택 단계 실패 — 이유를 기록하고 계속 진행합니다."
      return 0
    fi
    state_patch "$step_id" "failed" "$rc" "$(step_error_id "$step_id")" "$STEP_OBSERVED"
    return "$rc"
  fi
  state_patch "$step_id" "$STEP_STATUS" 0 "" "$STEP_OBSERVED"
  help_progress end
}

main() {
  local arg
  local -a orig_args=("$@")
  while [[ $# -gt 0 ]]; do
    arg="$1"
    case "$arg" in
      --reinstall) REINSTALL=1 ;;
      --resume) RESUME=1 ;;
      --dry-run) DRY_RUN=1 ;;
      --help|-h) usage; return 0 ;;
      *) usage >&2; return 2 ;;
    esac
    shift
  done
  assert_user_path "$WAVE_HOME" || return 1
  ensure_pack ${orig_args[@]+"${orig_args[@]}"} || return 1
  load_config || return 1
  if [[ "$DRY_RUN" == 1 ]]; then
    log "dry-run: $STEPS_FILE / $STATE_FILE / $LOG_FILE"
    return 0
  fi
  HELP_VERSION="$(json_value "$STEPS_FILE" version 2>/dev/null || echo unknown)"
  show_help_notice
  init_state
  local id status step_no=0
  while IFS= read -r id; do
    step_no=$((step_no + 1))
    HELP_STEP="${step_no}/10"
    status="$(json_value "$STATE_FILE" "steps.$id.status")"
    if [[ "$RESUME" == 1 && "$id" != "S09_COMPLETE" && "$id" != "S05_DAEMON_REGISTER" && "$id" != "S06_PACK_INSTALL" && "$id" != "S07_INITIAL_FLEET" && "$id" != "S08_VERIFY" && ( "$status" == "passed" || "$status" == "skipped" ) ]]; then
      log "[$id] resume: 이미 $status — 건너뜀"
      help_progress end
      continue
    fi
    if [[ "$id" == "S09_COMPLETE" ]]; then
      mark_required_complete || return 1
    fi
    log "[$id] 시작"
    run_step "$id" || { help_request; return 1; }
  done < <(python3 - "$STEPS_FILE" <<'PY'
import json, sys
with open(sys.argv[1], encoding="utf-8") as handle:
    for step in json.load(handle)["steps"]:
        print(step["id"])
PY
)
  mark_install_complete
  log "[10/10] Wave Terminal 설치 상태 $(json_value "$STATE_FILE" 'status') — START-HERE와 exceptions를 확인하세요."
}

main "$@"
