#!/usr/bin/env python3
"""S2 Release와 S3 설치기 매핑 회귀 테스트."""

from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
STEPS = ROOT / "steps.json"
BASE = "https://github.com/greatson79/wave-terminal/releases/download/v0.1.0"
MAC_BASE = "https://github.com/greatson79/wave-terminal/releases/download/v0.1.1"  # 재서명 DMG


def test_resolved_release_maps_each_macos_asset_to_its_hash_and_signature() -> None:
    release = json.loads(STEPS.read_text(encoding="utf-8"))["release"]

    assert release["asset_name"] == {
        "macos_arm64": "wave-terminal-0.1.1-macos-arm64.dmg",
        "macos_x64": "wave-terminal-0.1.1-macos-x64.dmg",
        "windows_x64": "wave-terminal-0.1.0-windows-x64-setup.exe",
    }
    assert release["asset_url"] == {
        "macos_arm64": f"{MAC_BASE}/wave-terminal-0.1.1-macos-arm64.dmg",
        "macos_x64": f"{MAC_BASE}/wave-terminal-0.1.1-macos-x64.dmg",
        "windows_x64": f"{BASE}/wave-terminal-0.1.0-windows-x64-setup.exe",
    }
    assert release["sha256"] == {
        "macos_arm64": "c46aac889c1dfb84827a580f83cb2098eceba30c85b98c961dd74cff6fc0cadc",
        "macos_x64": "aaee7fb8745e16e02e64f95bb698e7695742e7db906fdf1a53c99d88134cbf48",
        "windows_x64": "733a595c1270d62e9ca83e82cda143d8ec223985b857f648939541d20ba12fc3",
    }
    assert release["minisig_url"] == {
        "macos_arm64": f"{BASE}/wave-terminal-0.1.0-macos-arm64.dmg.minisig",
        "macos_x64": f"{BASE}/wave-terminal-0.1.0-macos-x64.dmg.minisig",
        "windows_x64": f"{BASE}/wave-terminal-0.1.0-windows-x64-setup.exe.minisig",
    }
    assert release["cdhash"] == {
        "macos_arm64": "86bdbce54748b3fabeecd4cfa22a73648867e23d",
        "macos_x64": "2bdc189e25310de485de8639412b96e9aa68280b",
    }
    assert release["sha256sums_url"] == f"{BASE}/SHA256SUMS"
    assert release["minisign_public_key"] == "RWShBLhu6xe+AnzdLhOKUuXyZb6FPjuBSWG0s7SPacy3v9o4Qt8Y9mqI"


if __name__ == "__main__":
    test_resolved_release_maps_each_macos_asset_to_its_hash_and_signature()
    print("PASS: S2 release mapping")
