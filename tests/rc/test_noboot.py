"""rc4 가짜 Claude(부트 건너뜀) — 합성 master 스위치와 판정 스크립트 시험. 실행: python3 -m unittest tests.rc.test_noboot"""
import json, os, subprocess, sys, tempfile, time, unittest
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import check_noboot, check_first_run

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

class FirstRunLeak(unittest.TestCase):
    def run_case(self, exit_txt, observed=None, statuses=("passed", "passed", "passed")):
        with tempfile.TemporaryDirectory() as d:
            if exit_txt is not None: open(os.path.join(d, "exit"), "w").write(exit_txt)
            steps = {"S07_INITIAL_FLEET": {"status": statuses[0], "observed": observed or {}}, "S08_VERIFY": {"status": statuses[1]}, "S09_COMPLETE": {"status": statuses[2]}}
            open(os.path.join(d, "s.json"), "w").write(json.dumps({"steps": steps}))
            return check_first_run.judge(os.path.join(d, "exit"), os.path.join(d, "s.json"))[0]
    def test_clean_pass(self): self.assertEqual(self.run_case("0\n", {"fleet_started": True}), 0)
    def test_nonzero_exit_fails_even_with_passed_steps(self): self.assertEqual(self.run_case("1\n"), 1)
    def test_exit2_fails(self): self.assertEqual(self.run_case("2\n", {"fleet_state": "alive_unconfirmed"}, ("failed", "pending", "pending")), 1)
    def test_exit0_but_a_gated_step_failed_fails(self):
        for i in range(3): self.assertEqual(self.run_case("0\n", {}, tuple("failed" if j == i else "passed" for j in range(3))), 1)
    def test_alive_unconfirmed_even_if_exit_0(self): self.assertEqual(self.run_case("0\n", {"fleet_state": "alive_unconfirmed"}), 1)
    def test_missing_evidence_fails(self): self.assertEqual(self.run_case(None, {}), 1)
    def test_signal_evidence_win_gates_is_caught(self):   # 신호용 RC 증거(첫 설치 exit 1 · S07 failed)가 새 단정에서 잡힌다 — 있을 때만
        e = "/Users/kylechoi/Desktop/Ai_works/개발본부/_round/evidence/rc4-signal-37134620023-all/rc-evidence-win-gates-37134620023/win"
        if os.path.isdir(e): self.assertEqual(check_first_run.judge(e + "/run.exit", e + "/G1_state.json")[0], 1)

class FakeClaudeSwitch(unittest.TestCase):
    def boot(self, skip):
        with tempfile.TemporaryDirectory() as home:
            pack = os.path.join(home, "pack"); os.makedirs(os.path.join(pack, "bin"))
            open(os.path.join(pack, "bin", "javis_bootstrap.py"), "w").write("import os;open(os.path.expanduser('~/ran'),'w').write('x')\n")
            os.makedirs(os.path.join(home, ".wave")); os.makedirs(os.path.join(home, "bin"))
            cys = os.path.join(home, "bin", "cys")   # 가짜 cys: 호출 인자만 기록(실제 좌석 기동 흉내는 cys boot 호출 여부로 증명)
            open(cys, "w").write("#!/bin/sh\necho \"$@\" >> \"$HOME/cys_calls\"\n"); os.chmod(cys, 0o755)
            if skip: open(os.path.join(home, ".wave", "rc-skip-bootstrap"), "w").write("")
            env = dict(os.environ, HOME=home, USERPROFILE=home, CYS_ROLE="master", CYS_PACK_DIR=pack, PYTHONDONTWRITEBYTECODE="1", PATH=os.path.join(home, "bin") + os.pathsep + os.environ["PATH"])
            subprocess.run([sys.executable, os.path.join(HERE, "fake_claude.py"), "--logic-only"], env=env, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=60)  # 파이프를 쓰면 fake_claude 의 백그라운드 진단이 닫을 때까지 막힌다
            calls = open(os.path.join(home, "cys_calls")).read().split("\n") if os.path.exists(os.path.join(home, "cys_calls")) else []
            return os.path.exists(os.path.join(home, "ran")), open(os.path.join(home, ".wave", "rc", "bootstrap.rc")).read(), [c for c in calls if c == "boot"]
    def test_default_runs_bootstrap_and_does_not_boot_itself(self): self.assertEqual(self.boot(False), (True, "0", []))
    def test_marker_skips_bootstrap_but_still_boots_the_seats(self):
        ran, rc, boots = self.boot(True)
        self.assertFalse(ran); self.assertEqual(rc, "skipped(cys boot rc=0)"); self.assertEqual(boots, ["boot"])   # 부트 스크립트·표지 없음 + cys boot 정확히 1회

if __name__ == "__main__": unittest.main()
