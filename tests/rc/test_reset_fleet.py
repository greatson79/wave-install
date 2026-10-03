import os
import pathlib
import subprocess
import tempfile
import time
import unittest


SCRIPT = pathlib.Path(__file__).with_name("reset-fleet.sh")


class ResetFleetTest(unittest.TestCase):
    def test_uninstall_and_wait_in_isolated_home(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = pathlib.Path(tmp)
            fakebin = home / "fakebin"
            fakebin.mkdir()
            for name, body in {
                "ps": '#!/bin/sh\nexit 0\n',
                "pkill": '#!/bin/sh\nexit 1\n',
            }.items():
                tool = fakebin / name
                tool.write_text(body)
                tool.chmod(0o755)
            bin_dir = home / ".wave" / "bin"
            bin_dir.mkdir(parents=True)
            cys = bin_dir / "cys"
            cys.write_text('#!/bin/sh\ncase "$2" in uninstall) echo uninstall >> "$HOME/calls" ;; '
                           'status) echo "registered=false loaded=false socket_alive=false" ;; esac\n')
            cys.chmod(0o755)
            env = dict(os.environ, HOME=str(home), PATH=str(fakebin) + os.pathsep + os.environ["PATH"])
            result = subprocess.run(["bash", str(SCRIPT)], env=env, capture_output=True, text=True, timeout=10)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual((home / "calls").read_text().strip(), "uninstall")

    def run_script(self, ps_out="", status="registered=false loaded=false socket_alive=false", lsof_out=""):
        """ps_out 의 {home} 는 격리 HOME 으로 치환된다."""
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        home = pathlib.Path(tmp.name)
        fakebin = home / "fakebin"
        fakebin.mkdir()
        tools = {"ps": f"#!/bin/sh\nprintf '%s' '{ps_out.format(home=home)}'\n", "pkill": "#!/bin/sh\nexit 1\n",
                 "lsof": f"#!/bin/sh\nprintf '%s' '{lsof_out}'\n", "osascript": "#!/bin/sh\nexit 0\n"}
        for name, body in tools.items():
            (fakebin / name).write_text(body)
            (fakebin / name).chmod(0o755)
        (home / ".wave" / "bin").mkdir(parents=True)
        cys = home / ".wave" / "bin" / "cys"
        cys.write_text(f'#!/bin/sh\ncase "$2" in status) echo "{status}" ;; esac\n')
        cys.chmod(0o755)
        env = dict(os.environ, HOME=str(home), PATH=str(fakebin) + os.pathsep + os.environ["PATH"])
        return subprocess.run(["bash", str(SCRIPT)], env=env, capture_output=True, text=True, timeout=30)

    def test_helper_process_or_open_file_under_app_blocks_reset(self):
        # 설치기 관문은 Contents/ 아래 모든 프로세스와 열린 파일을 본다 — 러너가 더 느슨하면 통과 뒤 설치기가 막힌다.
        for kind, kwargs in (("helper", {"ps_out": "{home}/.wave/apps/Wave Terminal.app/Contents/Frameworks/helper"}),
                             ("open-file", {"lsof_out": "123"})):
            with self.subTest(kind=kind):
                result = self.run_script(**kwargs)
                self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_daemon_that_never_dies_fails_the_reset(self):
        result = self.run_script(status="registered=false loaded=false socket_alive=true")
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)

    def test_mac_upgrade_stops_when_reset_fails(self):
        text = SCRIPT.with_name("mac-upgrade.sh").read_text()
        self.assertRegex(text, r'reset-fleet\.sh" "[^"]*"\s*\|\|\s*exit 1')

    def run_with_fakes(self, spawn, extra_args=()):
        """격리 HOME 에서 reset-fleet.sh 를 돌린다. spawn(home) 이 띄운 가짜 프로세스 목록과 결과를 돌려준다.
        가짜 cys 는 $HOME/daemon.pid 의 프로세스가 살아 있는 동안만(부모가 아직 안 거둔 좀비는 죽은 것으로 본다) socket_alive=true 를 보고한다."""
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        home = pathlib.Path(tmp.name)
        fakebin = home / "fakebin"
        fakebin.mkdir()
        # ps·pkill 은 진짜를 쓴다 — 이 시험의 요점이 pkill 패턴이다
        for name, body in {"lsof": "#!/bin/sh\nexit 1\n", "osascript": "#!/bin/sh\nexit 0\n"}.items():
            (fakebin / name).write_text(body)
            (fakebin / name).chmod(0o755)
        (home / ".wave" / "bin").mkdir(parents=True)
        cys = home / ".wave" / "bin" / "cys"
        cys.write_text('#!/bin/sh\ncase "$2" in\n status) if [ -f "$HOME/daemon.pid" ] && ps -o stat= -p "$(cat "$HOME/daemon.pid")" | grep -qv "^Z"; '
                       'then echo "registered=false loaded=false socket_alive=true"; '
                       'else echo "registered=false loaded=false socket_alive=false"; fi ;;\nesac\n')
        cys.chmod(0o755)
        procs = spawn(home)
        self.addCleanup(lambda: [(q.poll() is None and q.kill(), q.wait()) for q in procs.values()])
        time.sleep(0.7)
        for name, proc in procs.items():
            self.assertIsNone(proc.poll(), "%s died before the script ran" % name)
        env = dict(os.environ, HOME=str(home), PATH=str(fakebin) + os.pathsep + os.environ["PATH"])
        result = subprocess.run(["bash", str(SCRIPT), *extra_args], env=env, capture_output=True, text=True, timeout=60)
        return home, procs, result

    @staticmethod
    def fake(path):
        # argv[0] 만 원하는 경로로 보이게 한다(서명 문제 없이 실제 실행 파일은 /bin/sleep)
        return subprocess.Popen([str(path), "60"], executable="/bin/sleep")

    def test_daemon_not_owned_by_launchd_is_stopped_by_command_line(self):
        # 공개판 v0.2.3 의 데몬은 launchd 소유가 아니라 daemon uninstall 로 안 멈춘다 — 안내하는 pkill 과 같은 패턴으로 멈춘다
        def spawn(home):
            daemon = self.fake(home / ".wave/bin/cysd")
            (home / "daemon.pid").write_text(str(daemon.pid))
            return {"daemon": daemon}
        home, procs, result = self.run_with_fakes(spawn)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIsNotNone(procs["daemon"].poll())

    def test_leftover_seat_diagnostic_loops_are_stopped_and_other_processes_survive(self):
        def spawn(home):
            return {"loop": self.fake(home / ".wave/rc/alive_series_cso.txt"),
                    "bystander": self.fake(home / "elsewhere/keep-me")}
        home, procs, result = self.run_with_fakes(spawn)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIsNotNone(procs["loop"].poll(), "diagnostic loop must be stopped before the daemon check")
        self.assertIsNone(procs["bystander"].poll(), "unrelated process must survive")

    def test_office_bridge_and_its_events_clients_are_stopped_but_other_installs_survive(self):
        # 오피스 브리지(cysd 의 자식)와 그 이벤트 구독 클라이언트는 데몬이 launchd 소유가 아니면 cysd 정지로 안 죽는다
        # (클라이언트는 데몬이 없어도 재연결 루프로 남아 앱 번들 cys 를 연 채 다음 설치를 막는다).
        def line_proc(line):
            return subprocess.Popen([line, "60"], executable="/bin/sleep")  # argv[0] 만 명령줄처럼 보이게
        def spawn(home):
            return {
                "bridge": line_proc("%s/.wave/apps/Wave Terminal.app/Contents/Resources/python/bin/python3 %s/.cys/pack/bin/javis_hud_bridge.py" % (home, home)),
                "bridge-framework": line_proc("/opt/homebrew/Cellar/python@3.14/3.14.0/Frameworks/Python.framework/Versions/3.14/Resources/Python.app/Contents/MacOS/Python %s/.cys/pack/bin/javis_hud_bridge.py" % home),
                "events-link": line_proc("%s/.wave/bin/cys events --reconnect --cursor-file x" % home),
                "events-app": line_proc("%s/.wave/apps/Wave Terminal.app/Contents/MacOS/cys events --reconnect" % home),
                "other-bridge": line_proc("python3 %s/other/.cys/pack/bin/javis_hud_bridge.py" % home),
                "status-call": line_proc("%s/.wave/bin/cys status --json" % home),
            }
        home, procs, result = self.run_with_fakes(spawn)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        for name in ("bridge", "bridge-framework", "events-link", "events-app"):
            self.assertIsNotNone(procs[name].poll(), "%s must be stopped" % name)
        for name in ("other-bridge", "status-call"):
            self.assertIsNone(procs[name].poll(), "%s must survive" % name)

    def test_failure_dumps_process_and_daemon_state_to_the_given_file(self):
        def spawn(home):
            daemon = subprocess.Popen(["/bin/sleep", "60"])  # 패턴에 안 맞는 데몬 = 안 죽는 경로
            (home / "daemon.pid").write_text(str(daemon.pid))
            return {"stubborn": daemon}
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        dump = pathlib.Path(tmp.name) / "reset-fail.txt"
        home, procs, result = self.run_with_fakes(spawn, extra_args=(str(dump),))
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        text = dump.read_text()
        self.assertIn("socket_alive=true", text)
        self.assertIn("sleep", text)  # ps 목록


if __name__ == "__main__":
    unittest.main()
