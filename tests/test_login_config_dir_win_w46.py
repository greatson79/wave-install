import unittest
import test_windows_bootstrap as helper


@unittest.skipUnless(helper.PWSH, 'pwsh required')
class WindowsSeatLogin(unittest.TestCase):
    def run_case(self, body):
        return helper.BootstrapTests.run_ps(self, r'''
function claude {
  param([string]$noun, [string]$verb)
  Add-Content -LiteralPath (Join-Path $env:USERPROFILE 'calls') -Value "$verb|$env:CLAUDE_CONFIG_DIR"
  if ($verb -eq 'status') {
    $global:LASTEXITCODE = if (Test-Path -LiteralPath (Join-Path $env:CLAUDE_CONFIG_DIR 'loggedin')) { 0 } else { 1 }
  } elseif ($verb -eq 'login') {
    if ($env:FAKE_LOGIN_OK -eq '1') { New-Item -ItemType File -Path (Join-Path $env:CLAUDE_CONFIG_DIR 'loggedin') | Out-Null }
    $global:LASTEXITCODE = 0
  }
}
''' + body)

    def test_s02_uses_seat_folder_and_restores_environment(self):
        out = self.run_case(r'''
$env:CLAUDE_CONFIG_DIR = 'original-value'
$env:FAKE_LOGIN_OK = '1'
New-Item -ItemType Directory -Path (Join-Path $env:USERPROFILE '.claude') | Out-Null
New-Item -ItemType File -Path (Join-Path $env:USERPROFILE '.claude/loggedin') | Out-Null
Run-S02
$calls = @(Get-Content -LiteralPath (Join-Path $env:USERPROFILE 'calls'))
$seat = Join-Path $env:USERPROFILE '.cys\claude'
if ($calls.Count -ne 3 -or $calls[0] -ne "status|$seat" -or $calls[1] -ne "login|$seat" -or $calls[2] -ne "status|$seat") { throw "wrong calls: $($calls -join ',')" }
if ($env:CLAUDE_CONFIG_DIR -ne 'original-value') { throw 'environment leaked' }
Write-Output 'PASS S02 default-only login uses seat folder and restores env'
''')
        self.assertIn('PASS S02', out)

    def test_s02_seat_only_login_skips_login(self):
        out = self.run_case(r'''
$seat = Join-Path $env:USERPROFILE '.cys\claude'
New-Item -ItemType Directory -Path $seat -Force | Out-Null
New-Item -ItemType File -Path (Join-Path $seat 'loggedin') | Out-Null
Run-S02
$calls = @(Get-Content -LiteralPath (Join-Path $env:USERPROFILE 'calls'))
if ($calls.Count -ne 1 -or $calls[0] -ne "status|$seat") { throw "unexpected login: $($calls -join ',')" }
Write-Output 'PASS S02 seat-only login skips login'
''')
        self.assertIn('PASS S02', out)

    def test_s02_neither_login_fails(self):
        out = self.run_case(r'''
$env:FAKE_LOGIN_OK = '0'
try { Run-S02; throw 'S02 unexpectedly passed' } catch {
  if ($_.Exception.Message -notmatch '재확인 실패') { throw }
}
$calls = @(Get-Content -LiteralPath (Join-Path $env:USERPROFILE 'calls'))
if ($calls.Count -ne 3) { throw "wrong call count: $($calls -join ',')" }
Write-Output 'PASS S02 neither login fails after recheck'
''')
        self.assertIn('PASS S02', out)

    def test_s07_rechecks_custom_folder_after_s02(self):
        out = self.run_case(r'''
$env:CYS_ACCOUNT_DIR = Join-Path $env:USERPROFILE 'custom'
$env:FAKE_LOGIN_OK = '1'
Run-S02
function Start-WaveApp { throw 'stopped after auth' }
try { Run-S07 } catch { if ($_.Exception.Message -ne 'stopped after auth') { throw } }
$calls = @(Get-Content -LiteralPath (Join-Path $env:USERPROFILE 'calls'))
if ($calls.Count -ne 4 -or $calls[3] -ne "status|$env:CYS_ACCOUNT_DIR") { throw "S07 recheck missing: $($calls -join ',')" }
Write-Output 'PASS S07 rechecks custom seat folder after S02'
''')
        self.assertIn('PASS S07', out)

    def test_s07_login_loss_stops_before_timeout(self):
        out = self.run_case(r'''
$env:FAKE_LOGIN_OK = '1'
Run-S02
function Start-WaveApp { }
function Wait-GuiOnboarded { param($clock) }
function Seed-WaveClaudeTrust { }
function Get-LiveFleet { return [pscustomobject]@{ surfaces = @() } }
function Test-AwakenedFleet { return $false }
function Invoke-BoundedCheck {
  Remove-Item -LiteralPath (Join-Path $env:USERPROFILE '.cys\claude\loggedin') -Force
  return [pscustomobject]@{ timed_out = $false; exit_code = 0 }
}
function Send-MasterDeclaration { param($clock,$path) }
try { Run-S07; throw 'S07 unexpectedly passed' } catch {
  if ($_.Exception.Message -notmatch '작업 칸 로그인이 풀렸습니다') { throw }
}
if ($script:StepObserved.j_code -ne 'J-LOGIN-03') { throw 'diagnostic missing' }
Write-Output 'PASS S07 detects seat login loss before timeout'
''')
        self.assertIn('PASS S07 detects', out)
