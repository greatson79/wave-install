"""실제 PowerShell 함수 실행: NSIS 프로세스만 격리 대역으로 대체한다."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
PWSH = os.environ.get("PWSH")

class WindowsInstallTests(unittest.TestCase):
    def run_install(self, code=0, missing=False, tamper=False, bad_daemon=False):
        with tempfile.TemporaryDirectory(prefix="wave nsis ") as td:
            root = Path(td)
            home = root / "wave"
            download = home / "downloads"
            download.mkdir(parents=True)
            asset = download / "wave-terminal-0.1.1-windows-x64-setup.exe"
            asset.write_bytes(b"installer-fixture")
            digest = hashlib.sha256(asset.read_bytes()).hexdigest()
            if tamper:
                asset.write_bytes(b"tampered")
            source = (ROOT / "bootstrap.ps1").read_text().split("\nLoad-Config\nif ($DryRun)")[0]
            harness = root / "harness.ps1"
            harness.write_text(source + r'''
function Release-Context {
  $script:ArtifactPath = $env:TEST_ASSET
  $script:ReleaseExpectedSha256 = $env:TEST_DIGEST
  $script:WaveWinBytes = 17
}
function Start-Process {
  param($FilePath, $ArgumentList, [switch]$Wait, [switch]$PassThru)
  @{ file = $FilePath; args = $ArgumentList; wait = [bool]$Wait; pass = [bool]$PassThru } | ConvertTo-Json | Set-Content $env:TEST_CALL
  if ($env:TEST_CODE -eq '0' -and $env:TEST_MISSING -ne '1') {
    $dir = Join-Path $WaveHome 'bin'
    New-Item -ItemType Directory -Force $dir | Out-Null
    foreach ($name in @('cys.exe')) {
      $file = Join-Path $dir $name
      Set-Content $file -Value "#!/bin/sh`nprintf 'cys 0.1.1\n'`nexit 0"
      & chmod +x $file
    }
    $data = [byte[]]::new(2048)
    $data[0] = 0x4D; $data[1] = 0x5A; $data[60] = 128
    $data[128] = 0x50; $data[129] = 0x45; $data[132] = 0x64; $data[133] = 0x86
    if ($env:TEST_BAD_DAEMON -eq '1') { $data[0] = 0 }
    [IO.File]::WriteAllBytes((Join-Path $dir 'cysd.exe'), $data)
  }
  return [pscustomobject]@{ ExitCode = [int]$env:TEST_CODE }
}
try { Run-S04 6>$null; $StepObserved | ConvertTo-Json; exit 0 }
catch { [Console]::Error.WriteLine($_.Exception.Message); exit 1 }
''')
            call = root / "call.json"
            env = dict(os.environ, WAVE_HOME=str(home), USERPROFILE=str(root), TEST_ASSET=str(asset),
                       TEST_DIGEST=digest, TEST_CALL=str(call), TEST_CODE=str(code), TEST_MISSING=str(int(missing)), TEST_BAD_DAEMON=str(int(bad_daemon)))
            result = subprocess.run([PWSH, "-NoProfile", "-File", str(harness)], env=env, capture_output=True, text=True)
            return result, json.loads(call.read_text()) if call.exists() else None

    def test_setup_is_executed_silently_in_user_bin_before_cli_verification(self):
        result, call = self.run_install()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIsNotNone(call, "NSIS_EXECUTION_MISSING")
        self.assertTrue(call["wait"] and call["pass"])
        self.assertTrue(call["args"].startswith("/S /D="), call)
        self.assertNotIn('"', call["args"])
        self.assertTrue(call["args"].endswith("/wave/bin"), call)

    def test_nonzero_nsis_exit_is_failure(self):
        result, call = self.run_install(code=7)
        self.assertIsNotNone(call, "NSIS_EXECUTION_MISSING")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("W-NSIS-EXIT", result.stderr)

    def test_success_exit_without_installed_cli_is_failure(self):
        result, call = self.run_install(missing=True)
        self.assertIsNotNone(call, "NSIS_EXECUTION_MISSING")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("cys/cysd", result.stderr)

    def test_daemon_is_inspected_without_starting_it(self):
        result, call = self.run_install()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        observed = json.loads(result.stdout)
        self.assertIn("daemon_started", observed)
        self.assertFalse(observed["daemon_started"])
        self.assertEqual(observed["daemon_verification"], "PE-x64-and-observed-SHA256")
        self.assertEqual(len(observed["daemon_sha256"]), 64)
        self.assertEqual(len(observed["verified_installer_sha256"]), 64)

    def test_invalid_daemon_binary_fails(self):
        result, call = self.run_install(bad_daemon=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("W-CYSD-PE", result.stderr)

    def test_native_file_dryrun_has_no_install_or_web_command(self):
        with tempfile.TemporaryDirectory(prefix="wave-dryrun-") as td:
            root = Path(td)
            env = dict(os.environ, WAVE_HOME=str(root / "wave"), USERPROFILE=str(root), TEST_INSTALLER=str(ROOT / "bootstrap.ps1"))
            native = subprocess.run([PWSH, "-NoProfile", "-File", str(ROOT / "bootstrap.ps1"), "-DryRun"], env=env, capture_output=True, text=True)
            self.assertEqual(native.returncode, 0, native.stderr)
            self.assertIn("dry-run:", native.stdout)
            self.assertFalse((root / "wave").exists())
            harness = root / "no-web.ps1"
            harness.write_text('''$global:WebCalls = 0
function Invoke-WebRequest { $global:WebCalls++; throw 'DRYRUN_WEB_FORBIDDEN' }
function Invoke-RestMethod { $global:WebCalls++; throw 'DRYRUN_WEB_FORBIDDEN' }
function Start-Process { throw 'DRYRUN_INSTALL_FORBIDDEN' }
& $env:TEST_INSTALLER -DryRun
if ($LASTEXITCODE -ne 0 -or $global:WebCalls -ne 0) { exit 1 }
Write-Host 'DRYRUN_WEB_COMMANDS=0'
''')
            trapped = subprocess.run([PWSH, "-NoProfile", "-File", str(harness)], env=env, capture_output=True, text=True)
            self.assertEqual(trapped.returncode, 0, trapped.stdout + trapped.stderr)
            self.assertIn("DRYRUN_WEB_COMMANDS=0", trapped.stdout)
            self.assertFalse((root / "wave").exists())

    def test_changed_artifact_is_rejected_before_execution(self):
        result, call = self.run_install(tamper=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIsNone(call)
        self.assertIn("W-ARTIFACT-CHANGED", result.stderr)

if __name__ == "__main__":
    unittest.main(verbosity=2)
