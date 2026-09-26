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
REINSTALL=0
RESUME=0
DRY_RUN=0
STEP_OBSERVED='{}'
STEP_STATUS="passed"

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
  RELEASE_SUMS_URL="$(json_value "$STEPS_FILE" 'release.sha256sums_url')"
  RELEASE_MINISIG_URL="$(json_value "$STEPS_FILE" "release.minisig_url.$RELEASE_PLATFORM")"
  RELEASE_PUBLIC_KEY="$(json_value "$STEPS_FILE" 'release.minisign_public_key')"
  for value in "$RELEASE_VERSION" "$RELEASE_ASSET_NAME" "$RELEASE_ASSET_URL" "$RELEASE_EXPECTED_SHA256" "$RELEASE_SUMS_URL" "$RELEASE_MINISIG_URL" "$RELEASE_PUBLIC_KEY"; do
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

step_s01() {
  require_command claude || return 1
  local pin minimum version comparison
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
  version="$(claude --version 2>/dev/null)" || return 1
  mkdir -p "$WAVE_HOME/tooling"
  printf '%s\n' "$version" > "$WAVE_HOME/tooling/claude.version"
  # 최소값은 정식 X.Y.Z 릴리스. 빌드 메타데이터는 비교하지 않는다.
  comparison="$(python3 - "$version" "$minimum" <<'PY'
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
)" || { fail_message "Claude Code semver 형식 확인 불가"; return 1; }
  if [[ "$comparison" == upgrade ]]; then
    log "중단: Claude Code $minimum 이상 필요. claude update로 업그레이드한 뒤 다시 실행하세요."
    return 1
  fi
  STEP_OBSERVED="$(python3 - "$version" <<'PY'
import json, sys
print(json.dumps({"claude_version": sys.argv[1]}))
PY
)"
}

step_s02() {
  claude auth status >/dev/null 2>&1 || return 1
  mkdir -p "$WAVE_HOME/auth"
  : > "$WAVE_HOME/auth/claude-authenticated"
  STEP_OBSERVED='{"authenticated":true,"account_recorded":false}'
}

step_s03() {
  require_command curl || return 1
  require_command shasum || return 1
  require_command minisign || return 1
  set_release_context || return 1
  mkdir -p "$WAVE_HOME/downloads"
  local sums_path sig_path expected actual
  sums_path="$WAVE_HOME/downloads/SHA256SUMS"
  sig_path="${ARTIFACT_PATH}.minisig"
  curl --fail --silent --show-error --location --proto '=https' --tlsv1.2 "$RELEASE_ASSET_URL" --output "$ARTIFACT_PATH" || return 1
  curl --fail --silent --show-error --location --proto '=https' --tlsv1.2 "$RELEASE_SUMS_URL" --output "$sums_path" || return 1
  curl --fail --silent --show-error --location --proto '=https' --tlsv1.2 "$RELEASE_MINISIG_URL" --output "$sig_path" || return 1
  expected="$(awk -v file="$RELEASE_ASSET_NAME" '$2 == file || $2 == "*" file {print $1; exit}' "$sums_path")"
  actual="$(shasum -a 256 "$ARTIFACT_PATH" | awk '{print $1}')"
  [[ -n "$expected" && "$expected" == "$actual" && "$RELEASE_EXPECTED_SHA256" == "$actual" ]] || fail_message "SHA256 불일치" || return 1
  minisign -Vm "$ARTIFACT_PATH" -P "$RELEASE_PUBLIC_KEY" -x "$sig_path" >/dev/null || return 1
  STEP_OBSERVED="$(python3 - "$RELEASE_PLATFORM" "$RELEASE_ASSET_NAME" "$actual" <<'PY'
import json, sys
print(json.dumps({"platform": sys.argv[1], "asset": sys.argv[2], "sha256": sys.argv[3], "minisig_verified": True}))
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

step_s05() {
  mkdir -p "$WAVE_HOME/daemon"
  local result
  result="$WAVE_HOME/daemon/register-result"
  if [[ "${WAVE_ENABLE_DAEMON:-1}" == "0" ]]; then
    printf '%s\n' 'skipped_by_user' > "$result"
    STEP_STATUS="skipped"
    STEP_OBSERVED='{"mode":"skipped","registered":false}'
    return 0
  fi
  require_command launchctl || return 1
  local plist uid label
  plist="$WAVE_HOME/daemon/com.waveainetworks.cysd.plist"
  uid="$(id -u)"
  label="com.waveainetworks.cysd"
  cat > "$plist" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
<key>Label</key><string>${label}</string>
<key>ProgramArguments</key><array><string>${WAVE_HOME}/bin/cysd</string></array>
<key>RunAtLoad</key><true/>
</dict></plist>
EOF
  launchctl bootstrap "gui/$uid" "$plist" || return 1
  launchctl print "gui/$uid/$label" >/dev/null || return 1
  printf '%s\n' 'registered' > "$result"
  STEP_OBSERVED='{"mode":"default_on","registered":true,"admin_required":false}'
}

step_s06() {
  require_command shasum || return 1
  local source="${WAVE_PACK_SOURCE:-${SCRIPT_DIR}/wave-pack}"
  [[ -d "$source" ]] || fail_message "S1 wave-pack 소스 없음: $source" || return 1
  [[ -f "$source/manifest.json" && -f "$source/SHA256SUMS" ]] || return 1
  mkdir -p "$PACK_HOME"
  cp -R "$source"/. "$PACK_HOME"/
  (cd "$PACK_HOME" && shasum -a 256 -c SHA256SUMS) || return 1
  mkdir -p "$WAVE_HOME/bin"
  [[ -x "$PACK_HOME/bin/wave" ]] || fail_message "wave CLI 래퍼 없음" || return 1
  cp "$PACK_HOME/bin/wave" "$WAVE_HOME/bin/wave"
  chmod 755 "$WAVE_HOME/bin/wave"
  STEP_OBSERVED='{"pack_installed":true,"manifest_verified":true}'
}

step_s07() {
  local roles="$PACK_HOME/roles.json"
  local wave="$WAVE_HOME/bin/wave"
  [[ -f "$roles" && -x "$wave" ]] || fail_message "roles.json 또는 wave CLI 없음" || return 1
  mkdir -p "$WAVE_HOME/fleet"
  "$wave" fleet bootstrap --roles-file "$roles" > "$WAVE_HOME/fleet/bootstrap.log" 2>&1 || return 1
  "$wave" fleet status --json > "$WAVE_HOME/fleet/status.json" || return 1
  python3 - "$WAVE_HOME/fleet/status.json" <<'PY'
import json, sys
with open(sys.argv[1], encoding="utf-8") as handle:
    data = json.load(handle)
if len(data.get("seats", [])) != 2:
    raise SystemExit("초기 편성 좌석 수가 2가 아님")
PY
  : > "$WAVE_HOME/fleet/initial-fleet.ok"
  STEP_OBSERVED='{"seats":2,"roles":"master+dept","fleet_started":null}'
}

step_s08() {
  local wave="$WAVE_HOME/bin/wave"
  [[ -x "$WAVE_HOME/bin/cys" && -x "$wave" ]] || return 1
  mkdir -p "$WAVE_HOME/verify"
  "$WAVE_HOME/bin/cys" identify >/dev/null || return 1
  "$wave" doctor --json > "$WAVE_HOME/verify/doctor.json" || return 1
  STEP_OBSERVED="$(python3 - "$WAVE_HOME/verify/doctor.json" "$(json_value "$STEPS_FILE" 'tooling.max_injected_bytes_per_seat')" <<'PY'
import json, sys
with open(sys.argv[1], encoding="utf-8") as handle:
    data = json.load(handle)
limit = int(sys.argv[2])
if data.get("identify_exit") != 0 or len(data.get("seats", [])) != 2:
    raise SystemExit("identify·좌석 수 계약 불일치")
injected = [seat.get("injected_bytes") for seat in data["seats"]]
known = [value for value in injected if type(value) is int and value >= 0]
if any(value > limit for value in known):
    raise SystemExit("좌석당 지침 주입량 20KB 초과")
measured = len(known) == len(injected)
print(json.dumps({"identify_exit": 0, "seats": 2,
                  "injection_measured": measured,
                  "max_injected_bytes": max(known) if measured else None}))
PY
)" || return 1
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
            value = observed.get("max_injected_bytes")
            if observed.get("injection_measured") is not True or type(value) is not int or value < 0:
                reasons.append("injection_unmeasured")
            elif value > config["tooling"]["max_injected_bytes_per_seat"]:
                reasons.append("injection_limit_exceeded")
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
    "주입량 미측정은 0바이트 통과를 뜻하지 않습니다.\n", encoding="utf-8")
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
  state_patch "$step_id" "running" 0 "" '{}'
  set +e
  "$function_name"
  local rc=$?
  set -e
  if [[ "$rc" -ne 0 ]]; then
    state_patch "$step_id" "failed" "$rc" "$(step_error_id "$step_id")" "$STEP_OBSERVED"
    return "$rc"
  fi
  state_patch "$step_id" "$STEP_STATUS" 0 "" "$STEP_OBSERVED"
}

main() {
  local arg
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
  load_config || return 1
  if [[ "$DRY_RUN" == 1 ]]; then
    log "dry-run: $STEPS_FILE / $STATE_FILE / $LOG_FILE"
    return 0
  fi
  init_state
  local id status
  while IFS= read -r id; do
    status="$(json_value "$STATE_FILE" "steps.$id.status")"
    if [[ "$RESUME" == 1 && "$id" != "S09_COMPLETE" && ( "$status" == "passed" || "$status" == "skipped" ) ]]; then
      log "[$id] resume: 이미 $status — 건너뜀"
      continue
    fi
    if [[ "$id" == "S09_COMPLETE" ]]; then
      mark_required_complete || return 1
    fi
    log "[$id] 시작"
    run_step "$id" || return 1
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
