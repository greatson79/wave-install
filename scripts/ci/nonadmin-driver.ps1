[CmdletBinding()]
param([ValidateSet('published', 'post-login')][string]$Mode)
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$root = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$out = Join-Path $root "ci-evidence\$Mode"
New-Item -ItemType Directory -Force $out | Out-Null
$name = 'waveci' + (Get-Random -Minimum 10000 -Maximum 99999)
$password = ConvertTo-SecureString ('WaveCI!' + [guid]::NewGuid().ToString('N') + 'a9') -AsPlainText -Force
$user = New-LocalUser -Name $name -Password $password -Description 'Disposable standard installer CI user'
$users = Get-LocalGroup -SID 'S-1-5-32-545'
Add-LocalGroupMember -Group $users -Member $user
$admins = Get-LocalGroup -SID 'S-1-5-32-544'
if (@(Get-LocalGroupMember $admins | Where-Object { $_.SID -eq $user.SID }).Count) { throw 'CI user is administrator' }
# Only this disposable test tree is writable by the standard user.
& icacls $out /grant "${name}:(OI)(CI)M" | Out-Host
if ($LASTEXITCODE -ne 0) { throw 'Evidence ACL failed' }
$cred = New-Object Management.Automation.PSCredential("$env:COMPUTERNAME\$name", $password)
$childArguments = '-NoProfile -ExecutionPolicy Bypass -File "{0}" -Mode {1} -Root "{2}" -Evidence "{3}"' -f (Join-Path $PSScriptRoot 'nonadmin-child.ps1'), $Mode, $root, $out
$p = Start-Process "$env:SystemRoot\System32\WindowsPowerShell\v1.0\powershell.exe" -Credential $cred -LoadUserProfile -WorkingDirectory $out -ArgumentList $childArguments -PassThru
# Bounded equivalent of -Wait: Start-Process -Wait waits on descendants too,
# including the daemon under test. WaitForExit measures the installer root only.
$finished = $p.WaitForExit(900000)
if (-not $finished) {
  $ErrorActionPreference = 'Continue'
  & taskkill /PID $p.Id /T /F 2>&1 | Out-Host
  $ErrorActionPreference = 'Stop'
}
# Retire all processes owned by this unique disposable user, including a daemon
# whose parent already exited. Never match an executable name shared by the runner.
$owned = @(Get-CimInstance Win32_Process | ForEach-Object {
  $owner = Invoke-CimMethod -InputObject $_ -MethodName GetOwner -ErrorAction SilentlyContinue
  if ($owner -and $owner.User -eq $name -and $owner.Domain -eq $env:COMPUTERNAME) { $_ }
})
$ErrorActionPreference = 'Continue'
foreach ($proc in $owned) {
  & taskkill /PID $proc.ProcessId /T /F 2>&1 | Out-Host
}
$ErrorActionPreference = 'Stop'
@{ user = $name; cleanup_attempted_pids = @($owned | ForEach-Object { $_.ProcessId }) } | ConvertTo-Json | Set-Content (Join-Path $out 'process-cleanup.json') -Encoding UTF8
$profileKey = "HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion\ProfileList\$($user.SID.Value)"
$profile = (Get-ItemProperty $profileKey).ProfileImagePath
$wave = Join-Path $profile '.wave'
if (Test-Path $wave) {
  $evidenceWave = Join-Path $out 'wave'
  New-Item -ItemType Directory -Force $evidenceWave | Out-Null
  # Keep state/log evidence; the 128 MB installer and installed executables are not logs.
  foreach ($relative in @('install-state.json', 'install.log', 'START-HERE.md', 'verify', 'fleet', 'install')) {
    $item = Join-Path $wave $relative
    if (Test-Path $item) { Copy-Item $item $evidenceWave -Recurse -Force }
  }
}
@{ mode = $Mode; sid = $user.SID.Value; profile = $profile; timed_out = (-not $finished); exit_code = $(if ($finished) { $p.ExitCode } else { $null }); scope = 'Windows hosted runner; physical clean PC not measured' } | ConvertTo-Json | Set-Content (Join-Path $out 'runner.json') -Encoding UTF8
if (-not (Test-Path (Join-Path $out 'identity.json'))) { throw 'Standard user identity evidence missing' }
$statePath = Join-Path $out 'wave\install-state.json'
if (-not (Test-Path $statePath)) { throw 'Installer did not create state' }
$s = Get-Content $statePath -Raw -Encoding UTF8 | ConvertFrom-Json
if ($Mode -eq 'published') {
  if ($s.steps.S00_PREFLIGHT.status -ne 'passed' -or $s.steps.S01_CLAUDE_INSTALL.status -ne 'passed') { throw 'Failed before login boundary' }
  if ($s.steps.S02_CLAUDE_LOGIN.status -notin @('running', 'failed')) { throw 'Expected unauthenticated S02 stop; investigate unexpected authentication' }
  if ($s.steps.S03_DOWNLOAD_VERIFY.status -ne 'pending') { throw 'Unexpected execution beyond login boundary' }
  Write-Host 'LOGIN_BOUNDARY_OBSERVED: S00/S01 passed, S02 stopped. This is NOT a 10/10 pass.'
} else {
  if (-not $finished -or $p.ExitCode -ne 0) { throw 'Post-login fixture failed or timed out; inspect artifacts' }
  foreach ($id in @('S03_DOWNLOAD_VERIFY','S04_INSTALL_LINK','S05_DAEMON_REGISTER','S06_PACK_INSTALL','S07_INITIAL_FLEET','S08_VERIFY','S09_COMPLETE')) {
    if ($s.steps.$id.status -ne 'passed') { throw "$id did not pass in post-login fixture" }
  }
  if ($s.required_steps_passed -or $s.status -eq 'complete') { throw 'Synthetic authentication incorrectly reported full success' }
  if (-not (Test-Path (Join-Path $out 'schtasks-control.json'))) { Write-Warning 'Old S05 denial evidence missing; inspect control warnings' }
  Write-Host 'POST_LOGIN_FIXTURE_PASSED: real S03-S09; authentication synthetic; NOT full end-to-end success.'
}
