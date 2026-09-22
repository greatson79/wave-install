#!/usr/bin/env python3
"""S3 steps와 S4 안내 페이지의 조인 계약 테스트."""

from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / "site"
PACK = ROOT / "wave-pack"


def test_site_accepts_s3_steps_and_exposes_windows_preparation_state() -> None:
    steps = json.loads((ROOT / "steps.json").read_text(encoding="utf-8"))
    app = (SITE / "app.js").read_text(encoding="utf-8")
    index = (SITE / "index.html").read_text(encoding="utf-8")

    assert steps["schema"] == "wave-install.steps.v1"
    assert len(steps["steps"]) == 10
    assert "normalizeSteps" in app
    assert "on_fail" in app
    assert "pass" in app
    assert "준비 중" in index
    assert "무시" not in (index + app)


def test_join_contains_install_pack_and_attribution_readme() -> None:
    assert (SITE / "steps.json").is_file()
    assert (PACK / "manifest.json").is_file()
    assert (PACK / "SHA256SUMS").is_file()
    assert (PACK / "CHANGELOG.md").is_file()
    assert (PACK / "LICENSES" / "cys-terminal-MIT.txt").is_file()
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "idoforgod/cys-terminal" in readme
    assert "oogisoogi/jarvis-install" in readme
    assert "MIT" in readme


if __name__ == "__main__":
    test_site_accepts_s3_steps_and_exposes_windows_preparation_state()
    test_join_contains_install_pack_and_attribution_readme()
    print("PASS: S5 local join contract")
