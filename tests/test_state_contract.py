#!/usr/bin/env python3
"""Bash/PowerShell 공통 상태 계약 단위 회귀. 실설치·실데몬은 호출하지 않는다."""
import copy
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
PWSH = os.environ.get("PWSH") or shutil.which("pwsh")


from platform_scope import skip_bash_engine, write_fake_exe  # noqa: E402

class StateContractTests(unittest.TestCase):
    def run_unit(self, engine, state, bash, powershell, doctor=None, producer=False):
        with tempfile.TemporaryDirectory(prefix="wave-state-unit-") as td:
            home = Path(td)
            wave = home / "wave"
            (wave / "bin").mkdir(parents=True)
            state_file = wave / "install-state.json"
            state_file.write_text(json.dumps(state))
            before = state_file.read_bytes()
            steps = home / "steps.json"
            shutil.copyfile(ROOT / "steps.json", steps)
            env = dict(os.environ, HOME=str(home), USERPROFILE=str(home), WAVE_HOME=str(wave),
                       TEST_STEPS=str(steps), TEST_DOCTOR=str(home / "doctor.json"))
            (home / "doctor.json").write_text(json.dumps(doctor or {}))
            for name in ("cys", "cys.exe"):
                write_fake_exe(wave / "bin" / name, PWSH)
            fake_wave = wave / "bin/wave"
            fake_wave.write_text('#!/bin/sh\ncat "$TEST_DOCTOR"\n')
            fake_wave.chmod(0o755)
            pack = home / ".cys/pack"
            pack.mkdir(parents=True)
            shutil.copyfile(ROOT / "wave-pack/roles.json", pack / "roles.json")
            if producer:
                command = ["bash", str(ROOT / "wave-pack/bin/wave"), "doctor", "--json"] if engine == "bash" else [PWSH, "-NoLogo", "-NoProfile", "-File", str(ROOT / "wave-pack/bin/wave.ps1"), "doctor", "--json"]
            elif engine == "bash":
                source = (ROOT / "bootstrap.sh").read_text()
                marker = '\nmain "$@"\n'
                self.assertEqual(source.count(marker), 1)
                lib = home / "functions.sh"
                lib.write_text(source.rsplit(marker, 1)[0] + "\n")
                command = ["bash", "-c", 'source "$1"; STEPS_FILE="$TEST_STEPS"; ' + bash,
                           "state-unit", str(lib)]
            else:
                self.assertTrue(PWSH, "PWSH 실행체 필요")
                source = (ROOT / "bootstrap.ps1").read_text()
                marker = "\nLoad-Config\nif ($DryRun)"
                self.assertEqual(source.count(marker), 1)
                script = home / "functions.ps1"
                script.write_text(source.split(marker)[0] + '''
$script:Config = Get-Content -LiteralPath $env:TEST_STEPS -Raw | ConvertFrom-Json
$script:State = Get-Content -LiteralPath $StateFile -Raw | ConvertFrom-Json
function Invoke-BoundedCheck {
  param($FilePath, $Arguments, $Name, $TimeoutMs)
  $output = if ($Name -eq 'doctor') { Get-Content -LiteralPath $env:TEST_DOCTOR -Raw } else { '' }
  return [pscustomobject]@{ timed_out=$false; timeout_ms=$TimeoutMs; exit_code=0; stdout=$output; stderr=''; kill_error=$null }
}
try {
''' + powershell + '\nexit 0\n} catch { [Console]::Error.WriteLine($_.Exception.Message); exit 1 }\n')
                command = [PWSH, "-NoLogo", "-NoProfile", "-NonInteractive", "-File", str(script)]
            proc = subprocess.run(command, env=env, text=True, capture_output=True, timeout=15)
            result = json.loads(state_file.read_text(encoding="utf-8-sig"))
            start = wave / "START-HERE.md"
            return proc, result, before == state_file.read_bytes(), start.read_text(encoding="utf-8-sig") if start.exists() else ""

    def clean_state(self):
        state = json.loads((ROOT / "install-state.json").read_text())
        for entry in state["steps"].values():
            entry.update(status="passed", exit_code=0, error_id=None, observed={})
        state["steps"]["S07_INITIAL_FLEET"]["observed"] = {"fleet_started": True}
        state["steps"]["S08_VERIFY"]["observed"] = {"original_match": True, "new_file_count": 0}
        return state

    def test_passed_with_error_is_rejected_before_write(self):
        for engine in ("bash", "powershell"):
            with self.subTest(engine=engine):
                skip_bash_engine(self, engine)
                proc, _, unchanged, _ = self.run_unit(engine, self.clean_state(),
                    'state_patch S02_CLAUDE_LOGIN passed 0 WT-S02-AUTH \'{}\'',
                    "Update-Step 'S02_CLAUDE_LOGIN' 'passed' 0 'WT-S02-AUTH' ([ordered]@{})")
                self.assertNotEqual(proc.returncode, 0)
                self.assertTrue(unchanged)

    def test_observed_json_roundtrips_without_raw_braces(self):
        for engine in ("bash", "powershell"):
            with self.subTest(engine=engine):
                skip_bash_engine(self, engine)
                proc, state, _, _ = self.run_unit(engine, self.clean_state(),
                    'state_patch S08_VERIFY passed 0 "" \'{"max_injected_bytes":null,"injection_measured":false}\'',
                    "Update-Step 'S08_VERIFY' 'passed' 0 '' ([ordered]@{max_injected_bytes=$null;injection_measured=$false})")
                self.assertEqual(proc.returncode, 0, proc.stderr)
                self.assertEqual(state["steps"]["S08_VERIFY"]["observed"],
                                 {"max_injected_bytes": None, "injection_measured": False})

    def test_summary_is_nonblocking_and_reports_every_exception(self):
        mutations = ["clean", "error", "bypass_observed", "bypass_entry", "bypass_root",
                     "skipped", "unmeasured", "missing_measurement", "legacy_zero", "missing_step",
                     "fleet_unmeasured", "fleet_missing", "nonzero_exit", "failed", "original_mismatch", "pending_new", "string_zero"]
        for engine in ("bash", "powershell"):
            for mutation in mutations:
                with self.subTest(engine=engine, mutation=mutation):
                    skip_bash_engine(self, engine)
                    state = self.clean_state()
                    if mutation == "original_mismatch": state["steps"]["S08_VERIFY"]["observed"]["original_match"] = False
                    if mutation == "pending_new": state["steps"]["S08_VERIFY"]["observed"]["new_file_count"] = 1
                    if mutation == "string_zero": state["steps"]["S08_VERIFY"]["observed"]["new_file_count"] = "0"
                    if mutation == "error": state["steps"]["S02_CLAUDE_LOGIN"]["error_id"] = "WT-S02-AUTH"
                    if mutation == "bypass_observed": state["steps"]["S02_CLAUDE_LOGIN"]["observed"]["TEST_SYNTHETIC_BYPASS"] = True
                    if mutation == "bypass_entry": state["steps"]["S02_CLAUDE_LOGIN"]["TEST_SYNTHETIC_BYPASS"] = True
                    if mutation == "bypass_root": state["TEST_SYNTHETIC_BYPASS"] = True
                    if mutation == "skipped": state["steps"]["S05_DAEMON_REGISTER"]["status"] = "skipped"
                    if mutation == "unmeasured": state["steps"]["S08_VERIFY"]["observed"] = {"max_injected_bytes": None, "injection_measured": False}
                    if mutation == "missing_measurement": state["steps"]["S08_VERIFY"]["observed"] = {}
                    if mutation == "legacy_zero": state["steps"]["S08_VERIFY"]["observed"] = {"max_injected_bytes": 0}
                    if mutation == "missing_step": del state["steps"]["S04_INSTALL_LINK"]
                    if mutation == "fleet_unmeasured": state["steps"]["S07_INITIAL_FLEET"]["observed"]["fleet_started"] = None
                    if mutation == "fleet_missing": state["steps"]["S07_INITIAL_FLEET"]["observed"] = {}
                    if mutation == "nonzero_exit": state["steps"]["S02_CLAUDE_LOGIN"]["exit_code"] = 1
                    if mutation == "failed": state["steps"]["S02_CLAUDE_LOGIN"]["status"] = "failed"
                    proc, result, _, start = self.run_unit(engine, state,
                        'mark_required_complete; step_s09; state_patch S09_COMPLETE passed 0 "" "$STEP_OBSERVED"; mark_install_complete',
                        "Mark-RequiredComplete; Run-S09; Update-Step 'S09_COMPLETE' 'passed' 0 '' $StepObserved; Complete-State")
                    self.assertEqual(proc.returncode, 0, proc.stderr)
                    clean = mutation == "clean"
                    self.assertEqual(result["required_steps_passed"], clean)
                    self.assertEqual(result["status"], "complete" if clean else "complete_with_exceptions")
                    self.assertEqual(bool(result.get("exceptions")), not clean)
                    self.assertTrue(start)
                    if not clean: self.assertIn("예외", start)
                    for entry in result["steps"].values():
                        self.assertFalse(entry["status"] == "passed" and entry.get("error_id"))

    def test_doctor_producer_emits_null_not_fabricated_zero(self):
        for engine in ("bash", "powershell"):
            with self.subTest(engine=engine):
                skip_bash_engine(self, engine)
                proc, _, _, _ = self.run_unit(engine, self.clean_state(), "", "", producer=True)
                self.assertEqual(proc.returncode, 0, proc.stderr)
                doctor = json.loads(proc.stdout)
                self.assertEqual(len(doctor["seats"]), 3)
                self.assertTrue(all(seat.get("injected_bytes") is None for seat in doctor["seats"]))

    def test_original_contract_and_display_copies_are_preserved(self):
        steps = json.loads((ROOT / "steps.json").read_text())
        s08 = next(step for step in steps["steps"] if step["id"] == "S08_VERIFY")
        self.assertFalse(any(item['kind']=='bytes_lte' for item in s08['pass']))
        self.assertNotIn('max_injected_bytes_per_seat',steps['tooling'])
        conditions={v.get('json_path'):v.get('equals') for v in s08['pass']}
        self.assertIs(conditions['steps.S08_VERIFY.observed.original_match'],True)
        self.assertEqual(conditions['steps.S08_VERIFY.observed.new_file_count'],0)
        self.assertEqual((ROOT / "steps.json").read_bytes(), (ROOT / "site/steps.json").read_bytes())


if __name__ == "__main__":
    unittest.main(verbosity=2)
