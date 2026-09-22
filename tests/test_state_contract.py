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
                p = wave / "bin" / name
                p.write_text('#!/bin/sh\nexit 0\n')
                p.chmod(0o755)
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
function powershell { $global:LASTEXITCODE=0; Get-Content -LiteralPath $env:TEST_DOCTOR -Raw }
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
        state["steps"]["S08_VERIFY"]["observed"] = {"max_injected_bytes": 10, "injection_measured": True}
        return state

    def test_passed_with_error_is_rejected_before_write(self):
        for engine in ("bash", "powershell"):
            with self.subTest(engine=engine):
                proc, _, unchanged, _ = self.run_unit(engine, self.clean_state(),
                    'state_patch S02_CLAUDE_LOGIN passed 0 WT-S02-AUTH \'{}\'',
                    "Update-Step 'S02_CLAUDE_LOGIN' 'passed' 0 'WT-S02-AUTH' ([ordered]@{})")
                self.assertNotEqual(proc.returncode, 0)
                self.assertTrue(unchanged)

    def test_observed_json_roundtrips_without_raw_braces(self):
        for engine in ("bash", "powershell"):
            with self.subTest(engine=engine):
                proc, state, _, _ = self.run_unit(engine, self.clean_state(),
                    'state_patch S08_VERIFY passed 0 "" \'{"max_injected_bytes":null,"injection_measured":false}\'',
                    "Update-Step 'S08_VERIFY' 'passed' 0 '' ([ordered]@{max_injected_bytes=$null;injection_measured=$false})")
                self.assertEqual(proc.returncode, 0, proc.stderr)
                self.assertEqual(state["steps"]["S08_VERIFY"]["observed"],
                                 {"max_injected_bytes": None, "injection_measured": False})

    def test_summary_is_nonblocking_and_reports_every_exception(self):
        mutations = ["clean", "error", "bypass_observed", "bypass_entry", "bypass_root",
                     "skipped", "unmeasured", "missing_measurement", "legacy_zero", "missing_step",
                     "fleet_unmeasured", "fleet_missing", "nonzero_exit", "failed"]
        for engine in ("bash", "powershell"):
            for mutation in mutations:
                with self.subTest(engine=engine, mutation=mutation):
                    state = self.clean_state()
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

    def test_s08_unmeasured_is_null_and_nonblocking(self):
        for engine in ("bash", "powershell"):
            for values in [(None, None), (None, 10), (0, 10), (20481, 10)]:
                with self.subTest(engine=engine, values=values):
                    doctor = {"identify_exit": 0, "seats": [{"injected_bytes": x} for x in values]}
                    proc, state, _, _ = self.run_unit(engine, self.clean_state(),
                        'step_s08; state_patch S08_VERIFY passed 0 "" "$STEP_OBSERVED"',
                        "Run-S08; Update-Step 'S08_VERIFY' 'passed' 0 '' $StepObserved", doctor=doctor)
                    if 20481 in values:
                        self.assertNotEqual(proc.returncode, 0)
                        continue
                    self.assertEqual(proc.returncode, 0, proc.stderr)
                    observed = state["steps"]["S08_VERIFY"]["observed"]
                    measured = None not in values
                    self.assertEqual(observed["injection_measured"], measured)
                    self.assertEqual(observed["max_injected_bytes"], max(values) if measured else None)

    def test_doctor_producer_emits_null_not_fabricated_zero(self):
        for engine in ("bash", "powershell"):
            with self.subTest(engine=engine):
                proc, _, _, _ = self.run_unit(engine, self.clean_state(), "", "", producer=True)
                self.assertEqual(proc.returncode, 0, proc.stderr)
                doctor = json.loads(proc.stdout)
                self.assertEqual(len(doctor["seats"]), 2)
                self.assertTrue(all(seat.get("injected_bytes") is None for seat in doctor["seats"]))

    def test_bytes_contract_and_display_copies_are_preserved(self):
        steps = json.loads((ROOT / "steps.json").read_text())
        s08 = next(step for step in steps["steps"] if step["id"] == "S08_VERIFY")
        condition = next(item for item in s08["pass"] if item["kind"] == "bytes_lte")
        self.assertEqual(condition["max"], 20480)
        self.assertEqual(condition["json_path"], "max_injected_bytes")
        self.assertIn("미측정", s08["title"])
        self.assertEqual((ROOT / "steps.json").read_bytes(), (ROOT / "site/steps.json").read_bytes())


if __name__ == "__main__":
    unittest.main(verbosity=2)
