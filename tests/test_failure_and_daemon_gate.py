#!/usr/bin/env python3
"""D1/D2 단위 회귀. 실제 인증·DMG·데몬·전체 설치는 실행하지 않는다."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class FailureAndDaemonGateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="wave-d1-d2-unit-")
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name)
        source = (ROOT / "bootstrap.sh").read_text()
        marker = '\nmain "$@"\n'
        self.assertEqual(source.count(marker), 1)
        self.lib = self.home / "functions.sh"
        self.lib.write_text(source.rsplit(marker, 1)[0] + "\n")
        self.steps = self.home / "steps.json"
        shutil.copyfile(ROOT / "steps.json", self.steps)
        self.env = dict(os.environ, HOME=str(self.home),
                        WAVE_HOME=str(self.home / "wave"), TEST_STEPS=str(self.steps))

    def bash(self, script, mode="ok"):
        return subprocess.run(["bash", "-c", 'source "$1"; STEPS_FILE="$TEST_STEPS"; ' + script,
                               "unit-test", str(self.lib)],
                              env=dict(self.env, TEST_MODE=mode), text=True,
                              capture_output=True, timeout=10)

    def test_error_id_matches_id_not_list_position(self):
        config = json.loads(self.steps.read_text())
        config["steps"].reverse()
        self.steps.write_text(json.dumps(config))
        for step in config["steps"]:
            with self.subTest(id=step["id"]):
                result = self.bash('step_error_id "' + step["id"] + '"')
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(result.stdout.strip(), step["on_fail"]["error_id"])

    def test_missing_or_malformed_error_config_fails_without_traceback(self):
        for config in [{"steps": []}, {"steps": {}},
                       {"steps": [{"id": "S02_CLAUDE_LOGIN", "on_fail": None}]},
                       {"steps": [{"id": "S02_CLAUDE_LOGIN", "on_fail": {"error_id": ""}}]}]:
            with self.subTest(config=config):
                self.steps.write_text(json.dumps(config))
                result = self.bash('step_error_id S02_CLAUDE_LOGIN')
                self.assertNotEqual(result.returncode, 0)
                self.assertNotIn("Traceback", result.stderr)
                self.assertEqual(result.stdout, "")

    def test_original_failure_and_error_id_reach_state(self):
        wave = self.home / "wave"
        wave.mkdir()
        shutil.copyfile(ROOT / "install-state.json", wave / "install-state.json")
        result = self.bash('step_s02() { printf "original-failure-7\\n" >&2; return 7; }; '
                           'run_step S02_CLAUDE_LOGIN')
        self.assertEqual(result.returncode, 7, result.stderr)
        self.assertIn("original-failure-7", result.stderr)
        self.assertNotIn("Traceback", result.stderr)
        state = json.loads((wave / "install-state.json").read_text())["steps"]["S02_CLAUDE_LOGIN"]
        self.assertEqual((state["status"], state["exit_code"], state["error_id"]),
                         ("failed", 7, "WT-S02-AUTH"))

    def s04(self, mode="ok"):
        app = self.home / "wave/mount/Fixture.app/Contents/MacOS"
        app.mkdir(parents=True)
        (self.home / "artifact.dmg").write_text("mock only")
        for name, body in [("cys", '#!/bin/sh\nprintf "fixture cys\\n"\n'),
                           ("cysd", '#!/bin/sh\nprintf "invoked\\n" > "$HOME/cysd-executed"\nexit 77\n')]:
            p = app / name
            p.write_text(body)
            p.chmod(0o755)
        if mode == "nonexec":
            (app / "cysd").chmod(0o644)
        script = r'''
set_release_context() { ARTIFACT_PATH="$HOME/artifact.dmg"; }
hdiutil() { return 0; }
ditto() {
  cp -R "$1" "$2" || return 1
  if [[ "$TEST_MODE" == corrupt ]]; then
    printf '\n# changed during copy\n' >> "$2/Contents/MacOS/cysd"
  fi
}
ln() {
  command ln "$@" || return 1
  if [[ "$TEST_MODE" == wronglink && "$*" == *'/bin/cysd'* ]]; then
    cp "$WAVE_HOME/apps/Wave Terminal.app/Contents/MacOS/cysd" "$HOME/wrong-cysd"
    command ln -sfn "$HOME/wrong-cysd" "$WAVE_HOME/bin/cysd"
  fi
}
step_s04
printf '%s\n' "$STEP_OBSERVED"
'''
        return self.bash(script, mode)

    def test_s04_valid_copy_passes_without_starting_daemon(self):
        result = self.s04()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse((self.home / "cysd-executed").exists(), "S04 must never execute cysd")
        observed = json.loads(result.stdout.strip())
        self.assertEqual(observed["cysd_check"], "file+executable+symlink+copy-match")

    def test_s04_nonexecutable_daemon_is_rejected_without_start(self):
        result = self.s04("nonexec")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("실행 파일", result.stderr)
        self.assertFalse((self.home / "cysd-executed").exists())

    def test_s04_corrupted_copy_is_rejected_without_start(self):
        result = self.s04("corrupt")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("무결성", result.stderr)
        self.assertFalse((self.home / "cysd-executed").exists())

    def test_s04_wrong_symlink_is_rejected_without_start(self):
        result = self.s04("wronglink")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("심링크", result.stderr)
        self.assertFalse((self.home / "cysd-executed").exists())


if __name__ == "__main__":
    unittest.main(verbosity=2)
