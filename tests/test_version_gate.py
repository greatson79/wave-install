#!/usr/bin/env python3
"""S01 회귀: 설치·인증·네트워크·데몬 없이 실제 두 설치기의 함수를 실행한다."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
PWSH = os.environ.get("PWSH") or shutil.which("pwsh")


class VersionGateTests(unittest.TestCase):
    def run_gate(self, engine, version, minimum="2.1.278", legacy="2.1.278", code=0):
        with tempfile.TemporaryDirectory(prefix="wave-s01-unit-") as temp:
            root = Path(temp)
            config = {"tooling": {"claude_code_version": legacy,
                                 "claude_code_min_version": minimum}}
            steps = root / "steps.json"
            steps.write_text(json.dumps(config))
            env = dict(os.environ, WAVE_HOME=str(root / "wave"),
                       USERPROFILE=str(root), TEST_CLAUDE_VERSION=version,
                       TEST_CLAUDE_EXIT=str(code), TEST_STEPS=str(steps))
            if engine == "bash":
                source = (ROOT / "bootstrap.sh").read_text()
                marker = '\nmain "$@"\n'
                self.assertEqual(source.count(marker), 1)
                lib = root / "bootstrap-functions.sh"
                lib.write_text(source.rsplit(marker, 1)[0] + "\n")
                fake = root / "claude"
                fake.write_text('#!/bin/sh\nprintf "%s\\n" "$TEST_CLAUDE_VERSION"\nexit "$TEST_CLAUDE_EXIT"\n')
                fake.chmod(0o755)
                env["PATH"] = str(root) + os.pathsep + env["PATH"]
                command = ["bash", "-c",
                           'source "$1"; STEPS_FILE="$TEST_STEPS"; step_s01',
                           "s01-test", str(lib)]
            else:
                self.assertTrue(PWSH, "PowerShell 실행체 필요: PWSH=/path/to/pwsh")
                source = (ROOT / "bootstrap.ps1").read_text()
                marker = "\nLoad-Config\nif ($DryRun)"
                self.assertEqual(source.count(marker), 1)
                harness = root / "s01.ps1"
                harness.write_text(source.split(marker)[0] + """
$script:Config = Get-Content -LiteralPath $env:TEST_STEPS -Raw | ConvertFrom-Json
function claude {
  $global:LASTEXITCODE = [int]$env:TEST_CLAUDE_EXIT
  return $env:TEST_CLAUDE_VERSION
}
try { Run-S01; exit 0 } catch { [Console]::Error.WriteLine($_.Exception.Message); exit 1 }
""")
                command = [PWSH, "-NoLogo", "-NoProfile", "-NonInteractive", "-File", str(harness)]
            result = subprocess.run(command, env=env, text=True, capture_output=True)
            record = root / "wave/tooling/claude.version"
            recorded = record.read_text(encoding="utf-8-sig").strip() if record.exists() else None
            return result.returncode, result.stdout + result.stderr, recorded

    def test_version_boundaries_and_numeric_order(self):
        cases = [
            ("2.1.278 (Claude Code)", True), ("2.1.279 (Claude Code)", True),
            ("2.2.0", True), ("2.10.0", True), ("3.0.0", True),
            ("2.1.277", False), ("2.1.9", False), ("2.0.999", False),
            ("1.99.999", False), ("2.1.278-rc.1", False),
            ("2.1.279-beta.1", True), ("2.1.278+build.4", True),
            ("2.1.277+2.1.278", False), ("2.1.2780", True),
        ]
        for engine in ("bash", "powershell"):
            for version, accepted in cases:
                with self.subTest(engine=engine, version=version):
                    rc, output, recorded = self.run_gate(engine, version)
                    self.assertEqual(rc == 0, accepted, output)
                    if accepted:
                        self.assertEqual(recorded, version)
                    else:
                        self.assertIn("업그레이드", output)
                        self.assertIn("claude update", output)

    def test_placeholder_and_malformed_input_fail_closed(self):
        cases = [
            ("2.1.278", "2.1.278", "__CLAUDE_CODE_VERSION_PIN__", "핀"),
            ("2.1.278", "__CLAUDE_CODE_MIN_VERSION__", "2.1.278", "미정"),
            ("2.1.278", "", "2.1.278", "미정"),
            ("2.1.278", "2.1.bad", "2.1.278", "semver"),
            ("2.01.278", "2.1.278", "2.1.278", "semver"),
            ("", "2.1.278", "2.1.278", "semver"),
            ("error 2.1.278", "2.1.278", "2.1.278", "semver"),
            ("2.1.278-01", "2.1.278", "2.1.278", "semver"),
        ]
        for engine in ("bash", "powershell"):
            for version, minimum, legacy, message in cases:
                with self.subTest(engine=engine, version=version, minimum=minimum, legacy=legacy):
                    rc, output, _ = self.run_gate(engine, version, minimum, legacy)
                    self.assertNotEqual(rc, 0, output)
                    self.assertIn(message, output)

    def test_command_failure_is_not_accepted(self):
        for engine in ("bash", "powershell"):
            with self.subTest(engine=engine):
                rc, output, _ = self.run_gate(engine, "2.1.278 (Claude Code)", code=9)
                self.assertNotEqual(rc, 0, output)

    def test_public_configuration_is_resolved_and_copies_match(self):
        steps = json.loads((ROOT / "steps.json").read_text())
        self.assertEqual(steps["tooling"].get("claude_code_min_version"), "2.1.278")
        self.assertEqual(steps["tooling"]["claude_code_version"], "2.1.278")
        self.assertEqual((ROOT / "steps.json").read_bytes(), (ROOT / "site/steps.json").read_bytes())


if __name__ == "__main__":
    unittest.main(verbosity=2)
