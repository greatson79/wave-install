#!/usr/bin/env python3
"""S2 Release와 S3 설치기 매핑 회귀 테스트."""

from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
STEPS = ROOT / "steps.json"
BASE = "https://github.com/greatson79/wave-install/releases/download/v0.3.0-rc.1"  # 앱 자산은 설치기 RC 프리릴리스에 동봉
MAC = "wave-terminal-0.2.0-macos-arm64.dmg"  # ad-hoc 재서명 DMG (tests/rc/mac-resign.sh 와 같은 절차)
WIN = "wave-terminal-0.2.0-windows-x64-setup.exe"
MAC_SHA = "97e3c9344b5ae1b20dd502aed6ee015ff5c33bfd89e686c334acc369974a966b"
CDHASH = "17730251fcebff0a7ee60f72b8322255a1627f3a"


def test_resolved_release_maps_each_macos_asset_to_its_hash_and_signature() -> None:
    release = json.loads(STEPS.read_text(encoding="utf-8"))["release"]

    # macos_x64 는 별도 빌드가 없어 arm64 자산을 그대로 가리킨다(RC 러너 rc_release.py 와 같은 매핑).
    assert release["repository"] == "greatson79/wave-install"
    assert release["version"] == "0.2.0"
    assert release["macos_version"] == "0.2.0"
    assert release["asset_name"] == {"macos_arm64": MAC, "macos_x64": MAC, "windows_x64": WIN}
    assert release["asset_url"] == {
        "macos_arm64": f"{BASE}/{MAC}",
        "macos_x64": f"{BASE}/{MAC}",
        "windows_x64": f"{BASE}/{WIN}",
    }
    assert release["sha256"] == {
        "macos_arm64": MAC_SHA,
        "macos_x64": MAC_SHA,
        "windows_x64": "0f107d409a69cb71318639762daee8e093ae92e334f8014f3e504fcc1d66c2ff",
    }
    assert release["bytes"] == {"windows_x64": 128718773}
    # minisign 은 설치기가 더 이상 쓰지 않는다(SHA256 + codesign/CDHash · Authenticode).
    assert release["minisig_url"] == {"macos_arm64": None, "macos_x64": None, "windows_x64": None}
    assert release["cdhash"] == {"macos_arm64": CDHASH, "macos_x64": CDHASH}
    assert release["sha256sums_url"] == f"{BASE}/SHA256SUMS"
    assert release["windows_sha256sums_url"] == f"{BASE}/SHA256SUMS"
    assert release["minisign_public_key"] == "RWShBLhu6xe+AnzdLhOKUuXyZb6FPjuBSWG0s7SPacy3v9o4Qt8Y9mqI"


if __name__ == "__main__":
    test_resolved_release_maps_each_macos_asset_to_its_hash_and_signature()
    print("PASS: S2 release mapping")
