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
            path = Path(td) / "steps.json"
            path.write_text(json.dumps(steps), encoding="utf-8")
            out = subprocess.run(["node", str(ROOT / "tests/site_reinstall_harness.js"), str(SITE / "app.js"), str(path)],
                                 capture_output=True, text=True, check=True)
        self.assertEqual(json.loads(out.stdout), {"after_load": "MAC-CMD-FROM-STEPS", "after_windows_tab": "WIN-CMD-FROM-STEPS"})


if __name__ == "__main__":
    unittest.main()
