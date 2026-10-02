"""Portable execution of Windows helpers. External IO uses explicit test doubles."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
PWSH = os.environ.get('PWSH') or shutil.which('pwsh')

class BootstrapTests(unittest.TestCase):
    def run_ps(self, body):
        self.assertTrue(PWSH, 'PWSH is required')
        with tempfile.TemporaryDirectory(dir=ROOT, prefix='.win-test-') as tmp:
            home = Path(tmp)
            source = (ROOT / 'bootstrap.ps1').read_text(encoding='utf-8-sig').split('\nLoad-Config\nif ($DryRun)')[0]
            source = source.replace('$ErrorActionPreference = "Stop"', '$ErrorActionPreference = "Stop"\n[Console]::OutputEncoding = [Text.UTF8Encoding]::new()')
            script = home / 'harness.ps1'
            script.write_text(source + '\n' + body, encoding='utf-8-sig')
            env = dict(os.environ, USERPROFILE=str(home), WAVE_HOME=str(home/'wave'), WAVE_NO_PROGRESS='1', TEST_ROOT=str(ROOT))
            result = subprocess.run([PWSH, '-NoProfile', '-NonInteractive', '-File', str(script)], env=env, capture_output=True, text=True, encoding='utf-8')
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            return result.stdout

    def test_main_rerun_expires_resumes_and_reinstall_bypasses_marker(self):
        self.assertTrue(PWSH)
        with tempfile.TemporaryDirectory(dir=ROOT, prefix='.rerun-test-') as tmp:
            home = Path(tmp)
            for name in ('steps.json', 'install-state.json'):
                shutil.copyfile(ROOT/name, home/name)
            source = (ROOT/'bootstrap.ps1').read_text(encoding='utf-8-sig')
            source = source.replace('$ErrorActionPreference = "Stop"', '$ErrorActionPreference = "Stop"\n[Console]::OutputEncoding = [Text.UTF8Encoding]::new()')
            overrides = r'''
function Run-S00 { Say 'ACTION-S00' }
function Ensure-Pack { }
function Run-S01 { Say 'ACTION-S01' }
function Run-S02 { Say 'ACTION-S02' }
function Run-S03 { Say 'ACTION-S03' }
function Run-S04 { Say 'ACTION-S04' }
function Run-S05 { Say 'ACTION-S05' }
function Run-S06 { Say 'ACTION-S06' }
function Run-S07 { $script:StepObserved = @{ fleet_started = $true } }
function Run-S08 { $script:StepObserved = @{ injection_measured = $true; max_injected_bytes = 1 } }
'''
            script = home/'bootstrap.ps1'
            script.write_text(source.replace('\nLoad-Config\nif ($DryRun)', overrides+'\nLoad-Config\nif ($DryRun)'), encoding='utf-8-sig')
            env = dict(os.environ, USERPROFILE=str(home), WAVE_HOME=str(home/'wave'), WAVE_NO_PROGRESS='1')
            def run(*args):
                result = subprocess.run([PWSH, '-NoProfile', '-File', str(script), *args], env=env, capture_output=True, text=True, encoding='utf-8')
                self.assertEqual(result.returncode, 0, result.stdout+result.stderr)
                return result.stdout
            first = run()
            self.assertIn('ACTION-S06', first)
            mark = home/'wave/install-done.txt'
            self.assertTrue(mark.exists())
            second = run()
            self.assertIn('이미 끝나 있습니다', second)
            self.assertNotIn('ACTION-', second)
            import time
            os.utime(mark, (time.time()-601, time.time()-601))
            expired = run()
            self.assertIn('ACTION-S02', expired)
            # W12 G3/G5: completed pack installs still recheck the app's original bytes.
            self.assertIn('ACTION-S06', expired)
            self.assertIn('ACTION-S06', run('-Reinstall'))

    def test_dispatch_uses_our_rule_examples(self):
        self.run_ps(r'''
$rows = Import-Csv (Join-Path $env:TEST_ROOT 'tests/help-rules.tsv') -Delimiter "`t" -Encoding UTF8
foreach ($row in $rows) {
  $actual = Get-JCode $row.sample
  if ($actual -ne $row.code) { throw "dispatch: $($row.code) != $actual" }
}
if ((Get-JCode 'W-DOWNLOAD-NET: HTTP 404 Not Found') -ne 'J-DL-05') { throw '404 misclassified' }
if ((Get-JCode 'an unclassified failure') -ne 'J-UNK-00') { throw 'fallback' }
''')

    def test_one_line_zip_rejects_hash_and_parent_path_before_relaunch(self):
        self.run_ps(r'''
Add-Type -AssemblyName System.IO.Compression
Add-Type -AssemblyName System.IO.Compression.FileSystem
$script:ScriptDir = $null
$script:WaveHome = Join-Path $env:USERPROFILE 'wave'
$script:BundleUrl = 'https://example.test/wave-install.zip'
$bad = Join-Path $env:USERPROFILE 'bad.zip'
$archive = [IO.Compression.ZipFile]::Open($bad, [IO.Compression.ZipArchiveMode]::Create)
$null = $archive.CreateEntry('../escape.txt')
$archive.Dispose()
function Invoke-WebRequest { param($Uri, $OutFile, [switch]$UseBasicParsing, $ErrorAction) Copy-Item -LiteralPath $bad -Destination $OutFile }
$script:BundleSha256 = '0' * 64
$rejected = $false
try { Ensure-Pack } catch { $rejected = $_.Exception.Message -match 'SHA256 불일치' }
if (-not $rejected) { throw 'wrong zip hash accepted' }
$script:BundleSha256 = (Get-FileHash -LiteralPath $bad -Algorithm SHA256).Hash.ToLowerInvariant()
$rejected = $false
try { Ensure-Pack } catch { $rejected = $_.Exception.Message -match '위험 경로' }
if (-not $rejected -or (Test-Path (Join-Path $env:USERPROFILE 'escape.txt'))) { throw 'zip parent path accepted' }
''')

    def test_release_pins_and_signed_download_gate(self):
        self.run_ps(r'''
$env:PROCESSOR_ARCHITECTURE = 'AMD64'
$StepsFile = Join-Path $env:TEST_ROOT 'steps.json'
Load-Config
$script:WaveVersion = '__UNRESOLVED__'
$rejected = $false
try { Release-Context } catch { $rejected = $_.Exception.Message -match '핀 미확정' }
if (-not $rejected) { throw 'unresolved pin accepted' }
$script:WaveVersion = '1.2.3'
$script:WaveWinFile = "wave-terminal-${WaveVersion}-windows-x64-setup.exe"
$data = [Text.Encoding]::UTF8.GetBytes('signed installer fixture')
$script:WaveWinBytes = $data.Length
$sha = [Security.Cryptography.SHA256]::Create()
$script:WaveWinSha256 = ([BitConverter]::ToString($sha.ComputeHash($data))).Replace('-', '').ToLowerInvariant()
$sha.Dispose()
$Config.release.version = $WaveVersion
$Config.release.asset_name.windows_x64 = $WaveWinFile
$Config.release.asset_url.windows_x64 = 'https://example.test/setup.exe'
$Config.release.sha256.windows_x64 = $WaveWinSha256
$Config.release.windows_sha256sums_url = 'https://example.test/SHA256SUMS'
$Config.release.windows_publisher_subject = 'CN=Wave Test'
$script:mode = 'valid'
$script:verified = 0
function Invoke-WebRequest {
  param([switch]$UseBasicParsing, $Uri, $OutFile)
  if ($OutFile -eq $ArtifactPath) {
    [IO.File]::WriteAllBytes($OutFile, $data)
    if ($mode -eq 'tamper') { [IO.File]::WriteAllBytes($OutFile, [byte[]]::new($data.Length)) }
    if ($mode -eq 'bytes') { [IO.File]::WriteAllText($OutFile, 'short') }
  } else {
    $row = "$WaveWinSha256  $WaveWinFile"
    if ($mode -eq 'duplicate') { $row += "`n$row" }
    if ($mode -eq 'prefix') { $row += '.other' }
    Set-Content -LiteralPath $OutFile -Value $row
  }
}
function Get-AuthenticodeSignature {
  $script:verified++
  if ($mode -eq 'signature') { return @{ Status = 'HashMismatch'; SignerCertificate = $null } }
  if ($mode -eq 'publisher') { return @{ Status = 'Valid'; SignerCertificate = @{ Subject = 'CN=Other Publisher' } } }
  if ($mode -eq 'signed') { return @{ Status = 'Valid'; SignerCertificate = @{ Subject = 'CN=Wave Test' } } }
  return @{ Status = 'NotSigned'; SignerCertificate = $null }
}
Run-S03
if ($verified -ne 1 -or -not $StepObserved.authenticode_checked) { throw 'Authenticode gate not exercised' }
$script:mode = 'signed'
Run-S03
if ($StepObserved.signature_status -ne 'Valid') { throw 'signed publisher rejected' }
foreach ($script:mode in @('tamper', 'bytes', 'duplicate', 'prefix', 'signature', 'publisher')) {
  $rejected = $false
  try { Run-S03 } catch { $rejected = $true }
  if (-not $rejected) { throw "download mutant accepted: $mode" }
}
$Config.release.version = '1.2.4'
$rejected = $false
try { Release-Context } catch { $rejected = $_.Exception.Message -match '핀 불일치' }
if (-not $rejected) { throw 'config drift accepted' }
''')

    @unittest.skipUnless(os.name == 'nt', 'Zone.Identifier requires Windows/NTFS')
    def test_real_ntfs_webmark_is_only_removed_after_hash_match(self):
        self.run_ps(r'''
$p = Join-Path $env:USERPROFILE 'setup.exe'
[IO.File]::WriteAllText($p, 'fixture')
$hash = (Get-FileHash $p -Algorithm SHA256).Hash
Set-Content -LiteralPath $p -Stream Zone.Identifier -Value "[ZoneTransfer]`r`nZoneId=3"
if (-not (Test-WebMark $p)) { throw 'ADS fixture missing' }
$rejected = $false
try { Clear-WebMark $p ('0' * 64) } catch { $rejected = $true }
if (-not $rejected -or -not (Test-WebMark $p)) { throw 'unverified ADS removal' }
if ((Clear-WebMark $p $hash) -ne 'removed' -or (Test-WebMark $p)) { throw 'ADS removal failed' }
''')

    def test_webmark_rehashes_before_unblocking(self):
        self.run_ps(r'''
$p = Join-Path $env:USERPROFILE 'setup.exe'
[IO.File]::WriteAllText($p, 'fixture')
$hash = (Get-FileHash $p -Algorithm SHA256).Hash
$script:unblocked = 0
function Test-WebMark($Path) { return $true }
function Unblock-File { param($LiteralPath, $ErrorAction); $script:unblocked++ }
$result = Clear-WebMark $p $hash
if ($result -ne 'removed' -or $unblocked -ne 1) { throw 'unblock missing' }
[IO.File]::WriteAllText($p, 'mutated')
$rejected = $false
try { Clear-WebMark $p $hash } catch { $rejected = $true }
if (-not $rejected -or $unblocked -ne 1) { throw 'unverified unblock' }
function Test-WebMark($Path) { return $false }
if ((Clear-WebMark $p (Get-FileHash $p).Hash) -ne 'none') { throw 'absent ADS' }
''')

    def test_progress_is_fail_open_without_output_or_secrets(self):
        self.run_ps(r'''
$env:WAVE_NO_PROGRESS = '0'
$script:InstallId = 'test-install-id'
$script:ProgressUrl = 'https://example.test/api/progress'
$script:calls = 0
function Invoke-WebRequest {
  param($Uri, $Method, $Body, $ContentType, $TimeoutSec, [switch]$UseBasicParsing, $ErrorAction)
  $script:calls++
  $payload = [Text.Encoding]::UTF8.GetString($Body) | ConvertFrom-Json
  if ($payload.step -ne '4/10' -or $payload.detail -ne 'J-DL-04' -or $TimeoutSec -gt 5) { throw 'bad payload' }
  $script:payloadOK = $true
  throw 'network down'
}
function Write-Log { throw 'disk full too' }
$output = @(Send-Progress '4/10' 'fail' 3 'J-DL-04')
if ($output.Count -ne 0 -or $calls -ne 1 -or -not $payloadOK) { throw 'progress contract' }
$DryRun = $true
Send-Progress '4/10' 'fail' 3 'J-DL-04'
if ($calls -ne 1) { throw 'dry-run network' }
''')

    def test_recent_done_window_and_pin_changes(self):
        self.run_ps(r'''
$StepsFile = Join-Path $env:TEST_ROOT 'steps.json'
$StateTemplate = Join-Path $env:TEST_ROOT 'install-state.json'
Load-Config
Init-State
$State.status = 'complete'
$State.required_steps_passed = $true
Save-State
Save-InstallDone
if (-not (Test-RecentInstallDone)) { throw 'recent completion missed' }
(Get-Item $InstallDoneFile).LastWriteTimeUtc = [DateTime]::UtcNow.AddSeconds(-601)
if (Test-RecentInstallDone) { throw 'expired marker accepted' }
(Get-Item $InstallDoneFile).LastWriteTimeUtc = [DateTime]::UtcNow.AddSeconds(60)
if (Test-RecentInstallDone) { throw 'future marker accepted' }
Save-InstallDone
$WaveWinSha256 = 'changed'
if (Test-RecentInstallDone) { throw 'changed pin accepted' }
$State.status = 'complete_with_exceptions'
$State.required_steps_passed = $false
Save-InstallDone
if (Test-Path $InstallDoneFile) { throw 'exception falsely completed' }
''')

    def test_optional_error_continues_and_required_error_throws(self):
        self.run_ps(r'''
$StepsFile = Join-Path $env:TEST_ROOT 'steps.json'
$StateTemplate = Join-Path $env:TEST_ROOT 'install-state.json'
Load-Config
Init-State
Invoke-Step 'S05_DAEMON_REGISTER' { throw '오류: 액세스가 거부되었습니다.' }
$entry = $State.steps.S05_DAEMON_REGISTER
if ($entry.status -ne 'skipped_with_reason' -or $entry.exit_code -eq 0 -or $entry.observed.j_code -ne 'J-PERM-02') { throw 'optional failure not preserved' }
if ($entry.observed.reason -notmatch '액세스가 거부') { throw 'reason lost' }
if (-not $entry.observed.position -or (Get-Content $LogFile -Raw) -notmatch 'harness.ps1') { throw 'failure source location lost' }
if ((Get-Content $LogFile -Raw) -notmatch '액세스가 거부') { throw 'original error not logged' }
$threw = $false
try { Invoke-Step 'S06_PACK_INSTALL' { throw 'Access is denied' } } catch { $threw = $true }
if (-not $threw -or $State.steps.S06_PACK_INSTALL.status -ne 'failed') { throw 'required failure swallowed' }
if ((Get-JCode 'Access is denied') -ne 'J-PERM-02') { throw 'English permission code' }
''')

    def test_optional_initial_state_write_error_is_caught(self):
        self.run_ps(r'''
$StepsFile = Join-Path $env:TEST_ROOT 'steps.json'
$StateTemplate = Join-Path $env:TEST_ROOT 'install-state.json'
Load-Config
Init-State
$script:realUpdateStep = ${function:Update-Step}
function Update-Step {
  param($Id, $Status, $ExitCode, $ErrorId, $Observed)
  if ($Status -eq 'running') { throw 'Access is denied during initial state write' }
  & $script:realUpdateStep $Id $Status $ExitCode $ErrorId $Observed
}
$script:actionCalled = $false
Invoke-Step 'S05_DAEMON_REGISTER' { $script:actionCalled = $true }
if ($actionCalled -or $State.steps.S05_DAEMON_REGISTER.status -ne 'skipped_with_reason') { throw 'initial state failure escaped optional boundary' }
if ($State.steps.S05_DAEMON_REGISTER.observed.reason -notmatch 'initial state write') { throw 'initial state reason lost' }
''')

    def test_s05_registers_via_cli_and_checks_bounded_fallbacks(self):
        # W12 delegates registration to cys daemon install.
        self.run_ps(r'''
$script:mode = 'ready'
$script:phase = 0
$script:starts = @()
$script:calls = @()
function Write-Log { param($Message) }
function Start-Sleep { param($Milliseconds, $Seconds) }
function Test-Path { param($LiteralPath, $PathType) return $true }
function New-ItemProperty { throw 'installer must not register HKCU directly' }
function Get-ItemProperty { throw 'installer must not inspect HKCU directly' }
function New-Item { throw 'installer must not create a registry key' }
function Start-Process {
  param($FilePath)
  $script:starts += $FilePath
  $script:phase++
}
function Invoke-BoundedCheck {
  param($FilePath, $Arguments, $Name, $TimeoutMs)
  if ($FilePath -ne (Join-Path $WaveHome 'bin/cys.exe')) { throw 'unexpected CLI path' }
  $script:calls += ($Arguments -join ' ')
  if (($Arguments -join ' ') -eq 'daemon install') {
    if ($TimeoutMs -ne 30000) { throw 'registration not bounded' }
    $code = if ($mode -eq 'registration-failed') { 7 } else { 0 }
    return [pscustomobject]@{ timed_out=$false; exit_code=$code; stdout=''; stderr='fixture' }
  }
  if (($Arguments -join ' ') -ne 'ping' -or $TimeoutMs -ne 3000) { throw 'unexpected/unbounded ping' }
  $ready = ($mode -in @('ready','registration-failed') -or ($mode -eq 'daemon-fallback' -and $phase -ge 1) -or ($mode -eq 'app-fallback' -and $phase -ge 2))
  return [pscustomobject]@{ timed_out=(-not $ready); exit_code=$(if ($ready) { 0 } else { $null }); stdout=$(if ($ready) { 'pong' } else { '' }); stderr='' }
}
foreach ($case in @('ready','daemon-fallback','app-fallback','unavailable','registration-failed')) {
  $script:mode = $case; $script:phase = 0; $script:starts = @(); $script:calls = @(); $script:StepStatus = 'passed'
  Run-S05
  if ($calls[0] -ne 'daemon install' -or $StepObserved.registration -ne 'cys daemon install') { throw 'CLI registration missing' }
  if ($case -eq 'ready' -and ($starts.Count -ne 0 -or -not $StepObserved.daemon_ready -or $StepStatus -ne 'passed')) { throw 'ready daemon was restarted' }
  if ($case -eq 'daemon-fallback' -and ($starts.Count -ne 1 -or $starts[0] -ne (Join-Path $WaveHome 'bin/cysd.exe') -or -not $StepObserved.daemon_ready)) { throw 'daemon fallback wrong' }
  if ($case -eq 'app-fallback' -and ($starts.Count -ne 2 -or $starts[1] -ne (Join-Path $WaveHome 'bin/cys-app.exe') -or -not $StepObserved.daemon_ready)) { throw 'app fallback wrong' }
  if ($case -eq 'unavailable' -and ($StepStatus -ne 'skipped_with_reason' -or $StepObserved.daemon_ready -or $calls.Count -ne 16)) { throw 'unavailable daemon not bounded/nonblocking' }
  if ($case -eq 'registration-failed' -and ($StepStatus -ne 'skipped_with_reason' -or $StepObserved.registered -or -not $StepObserved.daemon_ready)) { throw 'registration failure hidden' }
}
''')

    @unittest.skipUnless(os.name == 'nt' and Path(PWSH or '').name.lower() == 'powershell.exe',
                         'Native stderr control requires Windows PowerShell 5.1')
    def test_s08_and_doctor_preserve_native_exit_and_stderr(self):
        self.run_ps(r'''
$StepsFile = Join-Path $env:TEST_ROOT 'steps.json'
$StateTemplate = Join-Path $env:TEST_ROOT 'install-state.json'
Load-Config
Init-State
$bin = Join-Path $WaveHome 'bin'
New-Item -ItemType Directory -Force $bin | Out-Null
New-Item -ItemType Directory -Force $PackHome | Out-Null
Copy-Item (Join-Path $env:TEST_ROOT 'wave-pack/roles.json') $PackHome
Copy-Item (Join-Path $env:TEST_ROOT 'wave-pack/bin/wave.ps1') $bin
Add-Type -OutputAssembly (Join-Path $bin 'cys.exe') -OutputType ConsoleApplication -TypeDefinition @"
using System;
public class StderrFixture {
  public static int Main(string[] args) {
    Console.Error.WriteLine("[cys] cysd not running - autostarting fixture");
    Console.WriteLine("{}");
    return Environment.GetEnvironmentVariable("WAVE_TEST_CYS_FAIL") == "1" ? 7 : 0;
  }
}
"@
$env:WAVE_TEST_CYS_FAIL = '0'
# Control proves PS5.1 + Stop would reject the successful native stderr call.
$control = $false
try { & (Join-Path $bin 'cys.exe') identify 2>&1 | Out-Null } catch { $control = $true }
if (-not $control) { throw 'PS5.1 native stderr control did not reproduce' }
Run-S08
if ($StepObserved.identify_exit -ne 0 -or $ErrorActionPreference -ne 'Stop') { throw 'S08 lost exit or preference' }
if ((Get-Content $LogFile -Raw) -notmatch 'autostarting fixture') { throw 'S08 diagnostic lost' }
if ((Get-Content (Join-Path $WaveHome 'verify/identify-doctor.log') -Raw) -notmatch 'autostarting fixture') { throw 'doctor diagnostic lost' }
$env:WAVE_TEST_CYS_FAIL = '1'
Run-S08
if ($StepStatus -ne 'unmeasured' -or $StepObserved.reason -ne 'call_failed' -or $StepObserved.command_exit -ne 7 -or $null -ne $StepObserved.max_injected_bytes) { throw 'failed cys observation lost or falsely passed' }
$doctor = & powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $bin 'wave.ps1') doctor --json | ConvertFrom-Json
if ($doctor.identify_exit -ne 7) { throw 'doctor hid native failure' }
''')

    @unittest.skipUnless(os.name == 'nt', 'Run-S07 uses Windows PowerShell child process')
    def test_s07_real_wrapper_accepts_roles_file_switch(self):
        self.run_ps(r'''
$StepsFile = Join-Path $env:TEST_ROOT 'steps.json'
$StateTemplate = Join-Path $env:TEST_ROOT 'install-state.json'
Load-Config
Init-State
$bin = Join-Path $WaveHome 'bin'
New-Item -ItemType Directory -Force $bin | Out-Null
New-Item -ItemType Directory -Force $PackHome | Out-Null
Copy-Item (Join-Path $env:TEST_ROOT 'wave-pack/roles.json') $PackHome
Copy-Item (Join-Path $env:TEST_ROOT 'wave-pack/bin/wave.ps1') $bin
Run-S07
if ($StepObserved.seats -ne 2) { throw 'fleet seats' }
if (-not (Test-Path (Join-Path $WaveHome 'fleet/initial-fleet.ok'))) { throw 'fleet marker absent' }
''')

    @unittest.skipUnless(os.name == 'nt', 'Bounded native child test requires Windows')
    def test_bounded_check_kills_sleeping_child_without_waiting_for_sleep(self):
        self.run_ps(r'''
$watch = [Diagnostics.Stopwatch]::StartNew()
$result = Invoke-BoundedCheck 'powershell.exe' @('-NoProfile', '-Command', 'Start-Sleep -Seconds 30') 'sleep-fixture' 300
$watch.Stop()
if (-not $result.timed_out -or $null -ne $result.exit_code -or $result.kill_error) { throw 'timeout not preserved or child not killed' }
if ($watch.ElapsedMilliseconds -gt 5000) { throw 'timeout did not bound process wait' }
''')

    @unittest.skipUnless(os.name == 'nt', 'Windows file sharing semantics required')
    def test_shared_check_log_reads_while_writer_is_open(self):
        self.run_ps(r'''
New-Item -ItemType Directory -Force $WaveHome | Out-Null
$path = Join-Path $WaveHome 'held.stdout.log'
$writer = [IO.File]::Open($path, [IO.FileMode]::Create, [IO.FileAccess]::Write, [IO.FileShare]::ReadWrite)
try {
  $bytes = [Text.Encoding]::UTF8.GetBytes('writer still open')
  $writer.Write($bytes, 0, $bytes.Length)
  $writer.Flush()
  $oldFailed = $false
  try { $null = [IO.File]::ReadAllText($path) } catch { $oldFailed = $true }
  if (-not $oldFailed) { throw 'old exclusive reader control did not reproduce' }
  if ((Read-SharedCheckLog $path) -cne 'writer still open') { throw 'shared reader lost output' }
} finally { $writer.Dispose() }
''')

    @unittest.skipUnless(os.name == 'nt', 'Windows exclusive file lock required')
    def test_s08_locked_log_read_failure_is_unmeasured_and_reaches_s09(self):
        self.run_ps(r'''
$StepsFile = Join-Path $env:TEST_ROOT 'steps.json'
$StateTemplate = Join-Path $env:TEST_ROOT 'install-state.json'
Load-Config
Init-State
$script:lockedPath = Join-Path $WaveHome 'locked.stdout.log'
$writer = [IO.File]::Open($lockedPath, [IO.FileMode]::Create, [IO.FileAccess]::Write, [IO.FileShare]::None)
function Invoke-BoundedCheck {
  param($FilePath, $Arguments, $Name, $TimeoutMs)
  if ($Name -eq $script:lockedName) { $null = Read-SharedCheckLog $script:lockedPath }
  return [pscustomobject]@{ timed_out = $false; timeout_ms = $TimeoutMs; exit_code = 0; stdout = ''; stderr = ''; kill_error = $null }
}
try {
  foreach ($name in @('identify', 'doctor')) {
    $script:lockedName = $name
    Invoke-Step 'S08_VERIFY' { Run-S08 }
    $entry = $State.steps.S08_VERIFY
    if ($entry.status -ne 'unmeasured' -or $entry.observed.reason -ne 'call_failed' -or $null -ne $entry.observed.max_injected_bytes) { throw 'locked log falsely measured' }
    if ($entry.observed.detail -notmatch 'Diagnostic log read failed' -or $entry.observed.detail -notmatch 'locked.stdout.log') { throw 'read failure reason or path missing' }
    Mark-RequiredComplete
    Invoke-Step 'S09_COMPLETE' { Run-S09 }
    Complete-State
    if ($State.steps.S09_COMPLETE.status -ne 'passed' -or $State.status -ne 'complete_with_exceptions' -or $State.required_steps_passed) { throw 'read failure blocked S09 or falsely passed' }
  }
} finally { $writer.Dispose() }
''')

    def test_s08_timeout_and_call_failure_allow_s09_without_false_measurements(self):
        self.run_ps(r'''
$StepsFile = Join-Path $env:TEST_ROOT 'steps.json'
$StateTemplate = Join-Path $env:TEST_ROOT 'install-state.json'
Load-Config
Init-State
function Invoke-BoundedCheck {
  param($FilePath, $Arguments, $Name, $TimeoutMs)
  return [pscustomobject]@{ timed_out = ($script:failureMode -eq 'timeout' -and $Name -eq $script:timeoutName); timeout_ms = $TimeoutMs; exit_code = $(if ($script:failureMode -eq 'call_failed' -and $Name -eq $script:timeoutName) { 7 } else { 0 }); stdout = ''; stderr = 'fixture detail'; kill_error = $null }
}
foreach ($case in @('timeout:identify', 'timeout:doctor', 'call_failed:identify', 'call_failed:doctor')) {
  $script:failureMode, $script:timeoutName = $case.Split(':')
  Invoke-Step 'S08_VERIFY' { Run-S08 }
  if ($State.steps.S08_VERIFY.status -ne 'unmeasured' -or $State.steps.S08_VERIFY.observed.reason -ne $script:failureMode -or $null -ne $State.steps.S08_VERIFY.observed.max_injected_bytes) { throw 'S08 call failure falsely passed' }
  Mark-RequiredComplete
  Invoke-Step 'S09_COMPLETE' { Run-S09 }
  Complete-State
  if ($State.steps.S09_COMPLETE.status -ne 'passed' -or $State.status -ne 'complete_with_exceptions' -or $State.required_steps_passed) { throw 'S09 continuation or exception semantics broken' }
}
''')

    def test_step_numbers_resume_and_failed_dispatch(self):
        output = self.run_ps(r'''
$StepsFile = Join-Path $env:TEST_ROOT 'steps.json'
$StateTemplate = Join-Path $env:TEST_ROOT 'install-state.json'
Load-Config
Init-State
foreach ($step in $Config.steps) { Say-Step $step 'test' }
$id = 'S06_PACK_INSTALL'
Update-Step $id 'passed' 0 '' @{}
# W12 G3/G5: persisted passed state cannot replace a live original-pack check.
if (Test-StepComplete $id) { throw 'pack verification was skipped on resume' }
$State.steps.$id.version = 'old'
if (Test-StepComplete $id) { throw 'old release skipped' }
try { Invoke-Step $id { throw 'claude 명령 없음' } } catch { }
if ($State.steps.$id.status -ne 'failed' -or $State.steps.$id.observed.j_code -ne 'J-PATH-01') { throw 'failed dispatch missing' }
''')
        for n in range(1, 11):
            self.assertIn(f'[{n}/10]', output)
        self.assertNotIn('/11]', output)

if __name__ == '__main__':
    unittest.main(verbosity=2)
