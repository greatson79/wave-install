import json
import os
import pathlib
import subprocess
import sys
import tempfile
import unittest


COLLECT = pathlib.Path(__file__).with_name("collect.py")


class G4StepMappingTest(unittest.TestCase):
    def test_boot_and_boot_extra_are_distinct(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = pathlib.Path(tmp)
            state = home / ".cys" / "state"
            state.mkdir(parents=True)
            steps = [("①preflight", 0), ("②ping", 0), ("③claim-role", 0),
                     ("④boot", 1), ("④b-retry", 0), ("⑤check#1", 1),
                     ("⑤check#2", 0), ("⑥extra", 1)]
            (state / "boot-last.json").write_text(json.dumps({"steps": [
                {"step": name, "exit": code} for name, code in steps]}))
            cys = home / "fake-cys"
            cys.write_text('#!/bin/sh\necho \'{"surfaces":[]}\'\n')
            cys.chmod(0o755)
            out = home / "evidence"
            env = dict(os.environ, HOME=str(home))
            result = subprocess.run([sys.executable, str(COLLECT), "g4", "--out", str(out),
                                     "--cys", str(cys)], env=env, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            got = json.loads((out / "G4_boot.json").read_text())["steps"]
            self.assertEqual(got, [{"n": 1, "exit": 0}, {"n": 2, "exit": 0},
                                   {"n": 3, "exit": 0}, {"n": 4, "exit": 1},
                                   {"n": 5, "exit": 0}])


if __name__ == "__main__":
    unittest.main()
