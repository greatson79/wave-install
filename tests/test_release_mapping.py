#!/usr/bin/env python3
"""S2 Release와 S3 설치기 매핑 회귀 테스트."""

from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
STEPS = ROOT / "steps.json"
BASE = "https://github.com/greatson79/wave-terminal/releases/download/v0.1.0"


def test_resolved_release_maps_each_macos_asset_to_its_hash_and_signature() -> None:
    release = json.loads(STEPS.read_text(encoding="utf-8"))["release"]

    assert release["asset_name"] == {
        "macos_arm64": "wave-terminal-0.1.0-macos-arm64.dmg",
        "macos_x64": "wave-terminal-0.1.0-macos-x64.dmg",
        "windows_x64": None,
    }
    assert release["asset_url"] == {
        "macos_arm64": f"{BASE}/wave-terminal-0.1.0-macos-arm64.dmg",
        "macos_x64": f"{BASE}/wave-terminal-0.1.0-macos-x64.dmg",
        "windows_x64": None,
    }
    assert release["sha256"] == {
        "macos_arm64": "d014f51fbcd50c02fe8f083a2f6d62eb3729738d40b6cd6809313906e6c7dbfd",
        "macos_x64": "90ac641169120156c34d65b722a84601dba2519d32daafbcde79631c26ae2b7f",
        "windows_x64": None,
    }
    assert release["minisig_url"] == {
        "macos_arm64": f"{BASE}/wave-terminal-0.1.0-macos-arm64.dmg.minisig",
        "macos_x64": f"{BASE}/wave-terminal-0.1.0-macos-x64.dmg.minisig",
        "windows_x64": None,
    }
    assert release["sha256sums_url"] == f"{BASE}/SHA256SUMS"
    assert release["minisign_public_key"] == "RWShBLhu6xe+AnzdLhOKUuXyZb6FPjuBSWG0s7SPacy3v9o4Qt8Y9mqI"


if __name__ == "__main__":
    test_resolved_release_maps_each_macos_asset_to_its_hash_and_signature()
    print("PASS: S2 release mapping")
