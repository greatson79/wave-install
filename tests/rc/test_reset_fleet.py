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


if __name__ == "__main__":
    unittest.main()
