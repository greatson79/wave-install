import os
import pathlib
import subprocess
import tempfile
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
        self.assertRegex(text, r'reset-fleet\.sh"\s*\|\|\s*exit 1')


if __name__ == "__main__":
    unittest.main()
