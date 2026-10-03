"""윈 앱 핀 갱신 도구 — 임시 사본에서 실측 sha·바이트·태그가 한 번에 바뀌고 릴리스 매핑 시험이 통과하는지. 실행: python3 -m unittest tests.rc.test_apply_win_pin"""
import hashlib, json, os, pathlib, shutil, subprocess, sys, tempfile, unittest
ROOT = pathlib.Path(__file__).resolve().parents[2]

class ApplyWinPin(unittest.TestCase):
    def test_pins_follow_the_measured_exe(self):
        with tempfile.TemporaryDirectory() as t:
            t = pathlib.Path(t); (t / "tests").mkdir()
            (t / "site").mkdir()
            for f in ("steps.json", "site/steps.json", "README.md", "tests/test_release_mapping.py"): shutil.copy2(ROOT / f, t / f)
            exe = t / json.loads((ROOT / "steps.json").read_text(encoding="utf-8"))["release"]["asset_name"]["windows_x64"]; exe.write_bytes(os.urandom(4096))
            r = subprocess.run([sys.executable, str(ROOT / "tests/rc/apply_win_pin.py"), str(t), str(exe), "v0.3.0-rc.9"], capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stderr)
            rel = json.loads((t / "steps.json").read_text(encoding="utf-8"))["release"]
            self.assertEqual((rel["sha256"]["windows_x64"], rel["bytes"]["windows_x64"]), (hashlib.sha256(exe.read_bytes()).hexdigest(), 4096))
            self.assertIn("v0.3.0-rc.9", rel["asset_url"]["windows_x64"]); self.assertIn("v0.3.0-rc.9", rel["windows_sha256sums_url"])
            self.assertEqual((t / "site/steps.json").read_bytes(), (t / "steps.json").read_bytes())
            m = subprocess.run([sys.executable, str(t / "tests/test_release_mapping.py")], capture_output=True, text=True, cwd=t)
            self.assertEqual(m.returncode, 0, m.stdout + m.stderr)
    def test_wrong_asset_name_is_refused(self):
        with tempfile.TemporaryDirectory() as t:
            exe = pathlib.Path(t) / "other.exe"; exe.write_bytes(b"x")
            r = subprocess.run([sys.executable, str(ROOT / "tests/rc/apply_win_pin.py"), str(ROOT), str(exe), "v0.3.0-rc.9"], capture_output=True, text=True)
            self.assertNotEqual(r.returncode, 0)
            self.assertIn("자산 파일명", r.stderr)

if __name__ == "__main__": unittest.main()
