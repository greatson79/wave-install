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
            self.assertNotIn('ACTION-S06', expired)
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
$Config.release.minisig_url.windows_x64 = 'https://example.test/setup.exe.minisig'
$script:mode = 'valid'
$script:verified = 0
function Invoke-WebRequest {
  param([switch]$UseBasicParsing, $Uri, $OutFile)
  if ($OutFile -eq $ArtifactPath) {
    [IO.File]::WriteAllBytes($OutFile, $data)
    if ($mode -eq 'tamper') { [IO.File]::WriteAllBytes($OutFile, [byte[]]::new($data.Length)) }
    if ($mode -eq 'bytes') { [IO.File]::WriteAllText($OutFile, 'short') }
  } elseif ($OutFile -like '*.minisig') {
    Set-Content -LiteralPath $OutFile -Value 'fixture signature'
  } else {
    $row = "$WaveWinSha256  $WaveWinFile"
    if ($mode -eq 'duplicate') { $row += "`n$row" }
    if ($mode -eq 'prefix') { $row += '.other' }
    Set-Content -LiteralPath $OutFile -Value $row
  }
}
function minisign { $script:verified++; $global:LASTEXITCODE = $(if ($mode -eq 'signature') { 1 } else { 0 }) }
Run-S03
if ($verified -ne 1 -or -not $StepObserved.minisig_verified) { throw 'signed gate not exercised' }
foreach ($script:mode in @('tamper', 'bytes', 'duplicate', 'prefix', 'signature')) {
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

    def test_step_numbers_resume_and_failed_dispatch(self):
        output = self.run_ps(r'''
$StepsFile = Join-Path $env:TEST_ROOT 'steps.json'
$StateTemplate = Join-Path $env:TEST_ROOT 'install-state.json'
Load-Config
Init-State
foreach ($step in $Config.steps) { Say-Step $step 'test' }
$id = 'S06_PACK_INSTALL'
Update-Step $id 'passed' 0 '' @{}
if (-not (Test-StepComplete $id)) { throw 'automatic resume missing' }
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
