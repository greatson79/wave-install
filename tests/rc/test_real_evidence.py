"""G9 실기 증거 — 설치기 종료값·fleet_state 필수. 실행: python3 -m unittest tests.rc.test_real_evidence"""
import json, os, subprocess, sys, tempfile, unittest
HERE = os.path.dirname(os.path.abspath(__file__)); TOOL = os.path.join(HERE, "real_evidence.py")

def run(*a): return subprocess.run([sys.executable, TOOL, *a], capture_output=True, text=True, timeout=30)

class Real(unittest.TestCase):
    def make(self, tmp, code, observed):
        home = os.path.join(tmp, "w"); os.makedirs(home)
        json.dump({"steps": {"S07_INITIAL_FLEET": {"observed": observed}}}, open(os.path.join(home, "install-state.json"), "w"))
        return run("make", "--os", "mac", "--exit", str(code), "--seats", "master,cso,worker", "--login-approve", "1", "--wave-home", home, "--out", os.path.join(tmp, "real"))
    def test_clean_run_passes_and_is_hash_bound(self):
        with tempfile.TemporaryDirectory() as t:
            self.assertEqual(self.make(t, 0, {"fleet_state": "started", "fleet_started": True}).returncode, 0)
            d = json.load(open(os.path.join(t, "real", "mac.json")))
            self.assertEqual((d["installer_exit"], d["fleet_state"], d["seats"]), (0, "started", ["master", "cso", "worker"]))
            self.assertEqual(run("check", os.path.join(t, "real")).returncode, 0)
            self.assertTrue(os.path.isfile(os.path.join(t, "real", "raw", "mac_install-state.json")))
            self.assertEqual([f for f in os.listdir(os.path.join(t, "real")) if f.endswith(".json")], ["mac.json"])   # gate.py 글롭에 원본이 안 걸린다
    def test_exit2_is_recorded_truthfully_and_check_fails(self):
        with tempfile.TemporaryDirectory() as t:
            self.assertEqual(self.make(t, 2, {"fleet_state": "alive_unconfirmed", "fleet_started": False}).returncode, 0)
            self.assertEqual(json.load(open(os.path.join(t, "real", "mac.json")))["installer_exit"], 2)
            r = run("check", os.path.join(t, "real")); self.assertEqual(r.returncode, 1); self.assertIn("alive_unconfirmed", r.stdout)
    def test_check_rejects_doc_without_the_fields_and_empty_folder(self):
        with tempfile.TemporaryDirectory() as t:
            json.dump({"os": "win", "seats": ["master"]}, open(os.path.join(t, "win.json"), "w"))
            self.assertEqual(run("check", t).returncode, 1)
            with tempfile.TemporaryDirectory() as e: self.assertEqual(run("check", e).returncode, 1)

if __name__ == "__main__": unittest.main()
