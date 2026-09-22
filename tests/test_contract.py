#!/usr/bin/env python3
"""S3 설치기 계약 테스트.

이 테스트는 네트워크·실제 설치·GitHub/Vercel 접근을 하지 않는다.
초기 S3 스테이징에서는 S2 릴리스 자리표시자를 허용하고,
S2 완료 후 --require-resolved-release 로 재실행한다.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
STEPS_PATH = ROOT / "steps.json"
STATE_PATH = ROOT / "install-state.json"
EXPECTED_IDS = [
    "S00_PREFLIGHT",
    "S01_CLAUDE_INSTALL",
    "S02_CLAUDE_LOGIN",
    "S03_DOWNLOAD_VERIFY",
    "S04_INSTALL_LINK",
    "S05_DAEMON_REGISTER",
    "S06_PACK_INSTALL",
    "S07_INITIAL_FLEET",
    "S08_VERIFY",
    "S09_COMPLETE",
]
REQUIRED_STEP_KEYS = {
    "id",
    "index",
    "total",
    "title",
    "command",
    "pass",
    "on_fail",
    "optional",
}
SUPPORTED_PASS_KINDS = {
    "exit_code",
    "file_exists",
    "sha256",
    "json_path",
    "count",
    "bytes_lte",
    "non_placeholder",
}
PLACEHOLDER_RE = re.compile(r"__.*?__")


def load_json(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise AssertionError(f"필수 파일 없음: {path}") from exc
    except json.JSONDecodeError as exc:
        raise AssertionError(f"JSON 파싱 실패: {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise AssertionError(f"최상위 JSON은 객체여야 함: {path}")
    return value


def assert_contract(require_resolved_release: bool) -> None:
    steps = load_json(STEPS_PATH)
    assert steps.get("schema") == "wave-install.steps.v1"
    assert steps.get("product") == "Wave Terminal"
    assert steps.get("version") == "0.1.2"
    assert isinstance(steps.get("steps"), list)
    actual_ids = [step.get("id") for step in steps["steps"]]
    assert actual_ids == EXPECTED_IDS, actual_ids
    assert len(steps["steps"]) == 10

    for index, step in enumerate(steps["steps"]):
        missing = REQUIRED_STEP_KEYS - set(step)
        assert not missing, f"{step.get('id')} 누락 키: {sorted(missing)}"
        assert step["index"] == index
        assert step["total"] == 10
        assert isinstance(step["command"], dict)
        assert set(step["command"]) == {"macos", "windows"}
        assert isinstance(step["pass"], list) and step["pass"]
        assert isinstance(step["on_fail"], dict)
        assert step["on_fail"].get("error_id", "").startswith("WT-")
        assert step["on_fail"].get("next") in {"retry", "stop"}
        for condition in step["pass"]:
            assert condition.get("kind") in SUPPORTED_PASS_KINDS, condition

    release = steps.get("release")
    assert isinstance(release, dict)
    for key in (
        "repository",
        "version",
        "asset_name",
        "asset_url",
        "sha256",
        "sha256sums_url",
        "minisig_url",
        "minisign_public_key",
    ):
        assert key in release, f"release.{key} 누락"

    serialized = json.dumps(release, ensure_ascii=False)
    placeholders = PLACEHOLDER_RE.findall(serialized)
    if require_resolved_release:
        assert not placeholders, f"S2 자리표시자 잔존: {placeholders}"
        assert release["repository"] == "greatson79/wave-terminal"
        assert release["version"] == "0.1.0"
        assert release["asset_name"]["windows_x64"] is None
        assert release["asset_url"]["windows_x64"] is None
        assert release["sha256"]["windows_x64"] is None
        assert release["minisig_url"]["windows_x64"] is None
        for platform in ("macos_arm64", "macos_x64"):
            assert re.fullmatch(r"[0-9a-f]{64}", release["sha256"][platform])
            assert release["asset_url"][platform].endswith(release["asset_name"][platform])
            assert release["minisig_url"][platform].endswith(release["asset_name"][platform] + ".minisig")
        assert release["minisign_public_key"].startswith("RW")
    else:
        assert "__S2_" in serialized, "초기 S3에는 S2 자리표시자가 있어야 함"

    state = load_json(STATE_PATH)
    assert state.get("schema") == "wave-install.state.v1"
    assert state.get("product") == "Wave Terminal"
    assert state.get("status") == "not_started"
    assert set(state.get("steps", {})) == set(EXPECTED_IDS)
    for step_id in EXPECTED_IDS:
        entry = state["steps"][step_id]
        for key in (
            "status",
            "exit_code",
            "started_at",
            "completed_at",
            "version",
            "checks",
            "error_id",
        ):
            assert key in entry, f"state.steps.{step_id}.{key} 누락"
        assert entry["status"] == "pending"
    assert state["paths"]["state"].endswith("/.wave/install-state.json")
    assert state["options"]["daemon"] is True
    assert state["options"]["codex"] is False
    assert state["options"]["antigravity"] is False

    for name in (
        "bootstrap.sh",
        "bootstrap.ps1",
        "reinstall.sh",
        "reinstall.ps1",
        "reset.sh",
        "reset.ps1",
        "S2_RELEASE_SUBSTITUTION.md",
    ):
        assert (ROOT / name).is_file(), f"필수 산출물 없음: {name}"

    shell = (ROOT / "bootstrap.sh").read_text(encoding="utf-8")
    assert "set -euo pipefail" in shell
    assert "__S2_" in shell or "release" in shell
    assert "sudo" not in shell
    assert "vercel" not in shell.lower()
    assert "git push" not in shell
    assert "cys-terminal" not in shell

    for name in ("reinstall.sh", "reset.sh"):
        text = (ROOT / name).read_text(encoding="utf-8")
        assert "--list" in text, f"{name}에 --list 없음"
        assert "sudo" not in text
        assert "git push" not in text


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--require-resolved-release", action="store_true")
    args = parser.parse_args()
    try:
        assert_contract(args.require_resolved_release)
    except AssertionError as exc:
        print(f"FAIL: {exc}")
        return 1
    print(
        "PASS: S3 설치기 계약 "
        + ("(S2 URL 치환 후)" if args.require_resolved_release else "(S2 자리표시자 허용)")
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
