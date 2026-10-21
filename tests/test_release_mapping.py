#!/usr/bin/env python3
"""S2 Release와 S3 설치기 매핑 회귀 테스트."""

from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
STEPS = ROOT / "steps.json"
BASE = "https://github.com/greatson79/wave-terminal/releases/download/v0.2.5"
WIN_BASE = BASE
MAC = "wave-terminal-0.2.5-macos-arm64.dmg"  # ad-hoc 재서명 DMG (tests/rc/mac-resign.sh 와 같은 절차)
WIN = "wave-terminal-0.2.5-windows-x64-setup.exe"
MAC_SHA = "7b0c8d71d3bf9d2fb81e8508a9e62c39cac0d9e90db91ad51c40d0155e10ab0d"
CDHASH = "6b7faab63885895145ea9443d593c9efbc4541e1"


def test_resolved_release_maps_each_macos_asset_to_its_hash_and_signature() -> None:
    release = json.loads(STEPS.read_text(encoding="utf-8"))["release"]

    # macos_x64 는 별도 빌드가 없어 arm64 자산을 그대로 가리킨다(RC 러너 rc_release.py 와 같은 매핑).
    assert release["repository"] == "greatson79/wave-terminal"
    assert release["version"] == "0.2.5"
    assert release["macos_version"] == "0.2.5"
    assert release["asset_name"] == {"macos_arm64": MAC, "macos_x64": MAC, "windows_x64": WIN}
    assert release["asset_url"] == {
        "macos_arm64": f"{BASE}/{MAC}",
        "macos_x64": f"{BASE}/{MAC}",
        "windows_x64": f"{WIN_BASE}/{WIN}",
    }
    assert release["sha256"] == {
        "macos_arm64": MAC_SHA,
        "macos_x64": MAC_SHA,
        "windows_x64": "299dcc697ae0cf7408074be541d6ad4ebe686fb5605a016f5487b1968d10a7bb",
    }
    assert release["bytes"] == {"windows_x64": 128935203}
    # minisign 은 설치기가 더 이상 쓰지 않는다(SHA256 + codesign/CDHash · Authenticode).
    assert release["minisig_url"] == {"macos_arm64": None, "macos_x64": None, "windows_x64": None}
    assert release["cdhash"] == {"macos_arm64": CDHASH, "macos_x64": CDHASH}
    assert release["sha256sums_url"] == f"{BASE}/SHA256SUMS"
    assert release["windows_sha256sums_url"] == f"{WIN_BASE}/SHA256SUMS"
    assert release["minisign_public_key"] == "RWShBLhu6xe+AnzdLhOKUuXyZb6FPjuBSWG0s7SPacy3v9o4Qt8Y9mqI"
    # 「다시 설치」: 맥 = 공개 입구 그대로 · 윈도우 = 앱 릴리스 bootstrap.ps1.
    steps = json.loads(STEPS.read_text(encoding="utf-8"))
    assert steps["reinstall"]["command"]["macos"] == "curl -fsSL https://waveainetworks.com/mac | bash -s -- --reinstall"
    assert "wave-terminal/releases/download/v0.2.5/bootstrap.ps1" in steps["reinstall"]["command"]["windows"]


if __name__ == "__main__":
    test_resolved_release_maps_each_macos_asset_to_its_hash_and_signature()
    print("PASS: S2 release mapping")
