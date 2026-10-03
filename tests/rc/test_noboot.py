"""rc4 가짜 Claude(부트 건너뜀) — 합성 master 스위치와 판정 스크립트 시험. 실행: python3 -m unittest tests.rc.test_noboot"""
import json, os, subprocess, sys, tempfile, time, unittest
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import check_noboot

class Judge(unittest.TestCase):
    def run_case(self, exp, exit_txt="7", absent=True, log="", state=None):
        with tempfile.TemporaryDirectory() as d:
            if exit_txt is not None: open(os.path.join(d, "exit"), "w").write(exit_txt + "\n")
            if absent: open(os.path.join(d, "marker_absent"), "w").write("")
            open(os.path.join(d, "run.log"), "w").write(log)
            if state is not None: open(os.path.join(d, "install-state.json"), "w").write(json.dumps({"steps": {"S07_INITIAL_FLEET": {"observed": state}}}))
            open(os.path.join(d, "e.json"), "w").write(json.dumps(exp))
            return check_noboot.judge(d, os.path.join(d, "e.json"))[0]
    def test_undecided_is_not_pass(self): self.assertEqual(self.run_case({"unconfirmed_exit": None}), 3)
    def test_match(self): self.assertEqual(self.run_case({"unconfirmed_exit": 7}), 0)
    def test_exit1_fails(self): self.assertEqual(self.run_case({"unconfirmed_exit": 7}, exit_txt="1"), 1)
    def test_other_exit_fails(self): self.assertEqual(self.run_case({"unconfirmed_exit": 7}, exit_txt="0"), 1)
    def test_missing_exit_fails(self): self.assertEqual(self.run_case({"unconfirmed_exit": 7}, exit_txt=None), 1)
    def test_marker_present_invalidates(self): self.assertEqual(self.run_case({"unconfirmed_exit": 7}, absent=False), 1)
    def test_observed_values(self):
        exp = {"unconfirmed_exit": 7, "observed": {"fleet_state": "alive_unconfirmed", "fleet_started": False, "seats_alive": 3}}
        ok = {"fleet_state": "alive_unconfirmed", "fleet_started": False, "seats_alive": 3, "j_code": "J-VER-04"}
        self.assertEqual(self.run_case(exp, state=ok), 0)
        self.assertEqual(self.run_case(exp, state=dict(ok, fleet_started=True)), 1)
        self.assertEqual(self.run_case(exp, state=dict(ok, seats_alive=2)), 1)
        self.assertEqual(self.run_case(exp), 1)   # install-state.json 없음
    def test_real_expect_file_is_exit_2(self):
        exp = json.load(open(os.path.join(HERE, "rc4-expect.json")))
        self.assertEqual((exp["unconfirmed_exit"], exp["diag_code"]), (2, "J-VER-04"))
    def test_diag_code(self):
        self.assertEqual(self.run_case({"unconfirmed_exit": 7, "diag_code": "J-X"}, log="… J-X …"), 0)
        self.assertEqual(self.run_case({"unconfirmed_exit": 7, "diag_code": "J-X"}, log="J-UNK-00"), 1)

class FakeClaudeSwitch(unittest.TestCase):
    def boot(self, skip):
        with tempfile.TemporaryDirectory() as home:
            pack = os.path.join(home, "pack"); os.makedirs(os.path.join(pack, "bin"))
            open(os.path.join(pack, "bin", "javis_bootstrap.py"), "w").write("import os;open(os.path.expanduser('~/ran'),'w').write('x')\n")
            os.makedirs(os.path.join(home, ".wave"))
            if skip: open(os.path.join(home, ".wave", "rc-skip-bootstrap"), "w").write("")
            env = dict(os.environ, HOME=home, USERPROFILE=home, CYS_ROLE="master", CYS_PACK_DIR=pack, PYTHONDONTWRITEBYTECODE="1")
            subprocess.run([sys.executable, os.path.join(HERE, "fake_claude.py"), "--logic-only"], env=env, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=60)  # 파이프를 쓰면 fake_claude 의 백그라운드 진단이 닫을 때까지 막힌다
            return os.path.exists(os.path.join(home, "ran")), open(os.path.join(home, ".wave", "rc", "bootstrap.rc")).read()
    def test_default_runs_bootstrap(self): self.assertEqual(self.boot(False), (True, "0"))
    def test_marker_skips_bootstrap(self): self.assertEqual(self.boot(True), (False, "skipped"))

if __name__ == "__main__": unittest.main()
