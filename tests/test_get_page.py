"""/get 화면의 재설치 안내 계약. 재설치 명령의 정본은 steps.json 의 reinstall.command 1개이고 화면은 그것을 그대로 보여 준다.
(tests/test_join.py 의 함수형 시험은 unittest 에 잡히지 않는다 — 이 시험은 discover 에 잡히도록 TestCase 로 둔다.)"""
import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / "site"
MAC_REINSTALL = "curl -fsSL https://waveainetworks.com/mac | bash -s -- --reinstall"


class GetPageReinstall(unittest.TestCase):
    def test_steps_json_is_the_single_source_and_both_copies_match(self):
        steps = json.loads((ROOT / "steps.json").read_text(encoding="utf-8"))
        self.assertEqual(steps["reinstall"]["command"]["macos"], MAC_REINSTALL)
        self.assertEqual((ROOT / "steps.json").read_bytes(), (SITE / "steps.json").read_bytes())

    def test_page_text_matches_steps_json_not_reinstall_sh(self):
        index = (SITE / "index.html").read_text(encoding="utf-8")
        self.assertNotIn("reinstall.sh", index)
        self.assertIn(MAC_REINSTALL, index)  # steps.json 연결 전 기본 문구 = 같은 명령

    @unittest.skipUnless(shutil.which("node"), "node 없음")
    def test_page_shows_whatever_steps_json_says(self):
        steps = json.loads((ROOT / "steps.json").read_text(encoding="utf-8"))
        with tempfile.TemporaryDirectory() as td:
            steps["reinstall"]["command"] = {"macos": "MAC-CMD-FROM-STEPS", "windows": "WIN-CMD-FROM-STEPS"}
            steps["install"]["command"] = {"macos": "MAC-INSTALL-FROM-STEPS", "windows": "WIN-INSTALL-FROM-STEPS"}
            path = Path(td) / "steps.json"
            path.write_text(json.dumps(steps), encoding="utf-8")
            out = subprocess.run(["node", str(ROOT / "tests/site_reinstall_harness.js"), str(SITE / "app.js"), str(path)],
                                 capture_output=True, text=True, check=True)
        self.assertEqual(json.loads(out.stdout), {"after_load": "MAC-CMD-FROM-STEPS", "after_windows_tab": "WIN-CMD-FROM-STEPS",
                                                  "install_mac": "MAC-INSTALL-FROM-STEPS", "install_windows": "WIN-INSTALL-FROM-STEPS"})


class GetPageInstall(unittest.TestCase):
    """설치 한 줄은 README·CI 와 같은 짧은 한 줄 — 정본 scripts/ci/install-lines.json, 화면은 steps.json install.command 를 따른다."""
    def setUp(self):
        self.contract = json.loads((ROOT / "scripts/ci/install-lines.json").read_text(encoding="utf-8"))
        self.steps = json.loads((ROOT / "steps.json").read_text(encoding="utf-8"))

    def test_steps_install_block_equals_the_contract(self):
        self.assertEqual(self.steps["install"]["command"], {"macos": self.contract["mac"], "windows": self.contract["win"]})

    def test_page_defaults_and_fallbacks_are_the_contract_lines_not_the_missing_tag(self):
        index = (SITE / "index.html").read_text(encoding="utf-8")
        app = (SITE / "app.js").read_text(encoding="utf-8")
        self.assertIn(self.contract["mac"], index)
        self.assertIn(self.contract["mac"], app); self.assertIn(self.contract["win"], app)
        for text in (index, app):
            self.assertNotIn("releases/download/v0.3.0/", text)
            self.assertNotIn("refs/tags/v0.3.0.zip", text)

    def test_zip_guidance_points_at_the_rc5_tag(self):
        index = (SITE / "index.html").read_text(encoding="utf-8")
        self.assertIn("archive/refs/tags/v0.3.0-rc.5.zip", index)
        self.assertIn("cd ~/Downloads/wave-install-0.3.0-rc.5", index)

    def test_readme_shows_the_same_lines(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn(self.contract["mac"], readme); self.assertIn(self.contract["win"], readme)


if __name__ == "__main__":
    unittest.main()
