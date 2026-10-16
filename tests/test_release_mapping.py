#!/usr/bin/env python3
"""S2 Release와 S3 설치기 매핑 회귀 테스트."""

from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
STEPS = ROOT / "steps.json"
BASE = "https://github.com/greatson79/wave-terminal/releases/download/v0.2.4"
WIN_BASE = BASE
MAC = "wave-terminal-0.2.4-macos-arm64.dmg"  # ad-hoc 재서명 DMG (tests/rc/mac-resign.sh 와 같은 절차)
WIN = "wave-terminal-0.2.4-windows-x64-setup.exe"
MAC_SHA = "8050262e26577f6a61dd5faea7b85a5752e8968fe2f8cb1c45fc3186602f2a06"
CDHASH = "f2d4970218d1f8b51276981cbac8c4ce7de6d26a"


def test_resolved_release_maps_each_macos_asset_to_its_hash_and_signature() -> None:
    release = json.loads(STEPS.read_text(encoding="utf-8"))["release"]

    # macos_x64 는 별도 빌드가 없어 arm64 자산을 그대로 가리킨다(RC 러너 rc_release.py 와 같은 매핑).
    assert release["repository"] == "greatson79/wave-terminal"
    assert release["version"] == "0.2.4"
    assert release["macos_version"] == "0.2.4"
    assert release["asset_name"] == {"macos_arm64": MAC, "macos_x64": MAC, "windows_x64": WIN}
    assert release["asset_url"] == {
        "macos_arm64": f"{BASE}/{MAC}",
        "macos_x64": f"{BASE}/{MAC}",
        "windows_x64": f"{WIN_BASE}/{WIN}",
    }
    assert release["sha256"] == {
        "macos_arm64": MAC_SHA,
        "macos_x64": MAC_SHA,
        "windows_x64": "4d075b88b277b1ee019e64acc3b341e4415de6cb555df8c9c041168d12efe908",
    }
    assert release["bytes"] == {"windows_x64": 128960090}
    # minisign 은 설치기가 더 이상 쓰지 않는다(SHA256 + codesign/CDHash · Authenticode).
    assert release["minisig_url"] == {"macos_arm64": None, "macos_x64": None, "windows_x64": None}
    assert release["cdhash"] == {"macos_arm64": CDHASH, "macos_x64": CDHASH}
    assert release["sha256sums_url"] == f"{BASE}/SHA256SUMS"
    assert release["windows_sha256sums_url"] == f"{WIN_BASE}/SHA256SUMS"
    assert release["minisign_public_key"] == "RWShBLhu6xe+AnzdLhOKUuXyZb6FPjuBSWG0s7SPacy3v9o4Qt8Y9mqI"
    # 「다시 설치」: 맥 = 공개 입구 그대로 · 윈도우 = 앱 릴리스 bootstrap.ps1.
    steps = json.loads(STEPS.read_text(encoding="utf-8"))
    assert steps["reinstall"]["command"]["macos"] == "curl -fsSL https://waveainetworks.com/mac | bash -s -- --reinstall"
    assert "wave-terminal/releases/download/v0.2.4/bootstrap.ps1" in steps["reinstall"]["command"]["windows"]


if __name__ == "__main__":
    test_resolved_release_maps_each_macos_asset_to_its_hash_and_signature()
    print("PASS: S2 release mapping")
