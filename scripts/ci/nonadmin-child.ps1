[CmdletBinding()]
param([string]$Mode, [string]$Root, [string]$Evidence)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
Start-Transcript -Path (Join-Path $Evidence 'child.log') -Force | Out-Null
try {
  if ($PSVersionTable.PSVersion.Major -ne 5) { throw 'Windows PowerShell 5.1 required' }
  $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
  $principal = New-Object Security.Principal.WindowsPrincipal($identity)
  $admin = $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
  if ($admin -or @($identity.Groups | Where-Object { $_.Value -eq 'S-1-5-32-544' }).Count) { throw 'Administrator token/group is prohibited' }
  $profile = (Get-ItemProperty "HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion\ProfileList\$($identity.User.Value)").ProfileImagePath
  # A loaded profile path alone is not evidence that HKCU points to this user's hive.
  $probeKey = 'Software\WaveInstallerCI'
  $nonce = [guid]::NewGuid().ToString('N')
  New-Item -Path ('HKCU:\' + $probeKey) -Force | Out-Null
  New-ItemProperty -Path ('HKCU:\' + $probeKey) -Name ProfileProbe -Value $nonce -PropertyType String -Force | Out-Null
  $sidHive = 'Registry::HKEY_USERS\' + $identity.User.Value + '\' + $probeKey
  if ((Get-ItemProperty $sidHive).ProfileProbe -cne $nonce) { throw 'HKCU is not the standard user SID hive' }
  $env:USERNAME = $identity.Name.Split('\')[-1]
  $env:USERPROFILE = $profile
  $env:HOME = $profile
  $env:HOMEDRIVE = [IO.Path]::GetPathRoot($profile).TrimEnd('\')
  $env:HOMEPATH = $profile.Substring($env:HOMEDRIVE.Length)
  $env:LOCALAPPDATA = Join-Path $profile 'AppData\Local'
  $env:APPDATA = Join-Path $profile 'AppData\Roaming'
  $env:TEMP = Join-Path $env:LOCALAPPDATA 'Temp'
  $env:TMP = $env:TEMP
  New-Item -ItemType Directory -Force $env:TEMP | Out-Null
  # Exclude runner credentials/configuration and tool paths from the fresh user's environment.
  Get-ChildItem Env: | Where-Object { $_.Name -match '^(WAVE_|CLAUDE_|ANTHROPIC_|CYS_)' } | ForEach-Object { Remove-Item "Env:$($_.Name)" }
  $env:PATH = "$env:SystemRoot\System32;$env:SystemRoot;$env:SystemRoot\System32\WindowsPowerShell\v1.0"
  if (Test-Path (Join-Path $profile '.wave')) { throw 'Profile was not empty' }
  @{ user = $identity.Name; sid = $identity.User.Value; administrator = $admin; profile = $profile; powershell = $PSVersionTable.PSVersion.ToString(); fresh_wave_home = $true; hkcu_sid_verified = $true; evidence_acl = (Get-Acl $Evidence).Sddl } | ConvertTo-Json | Set-Content (Join-Path $Evidence 'identity.json') -Encoding UTF8
  if ($Mode -eq 'published') {
    $line = @(Get-Content (Join-Path $Root 'README.md') -Encoding UTF8 | Where-Object { $_ -like 'powershell *install-wave.ps1*' })
    if ($line.Count -ne 1) { throw 'Expected exactly one README Windows command' }
    $line[0] | Set-Content (Join-Path $Evidence 'readme-command.txt') -Encoding UTF8
    Invoke-Expression $line[0]
    exit $LASTEXITCODE
  }
  $run = Join-Path $profile 'post-login-fixture'
  New-Item -ItemType Directory $run | Out-Null
  Copy-Item (Join-Path $Root 'steps.json'), (Join-Path $Root 'install-state.json') -Destination $run
  Copy-Item (Join-Path $Root 'wave-pack') -Destination $run -Recurse
  Get-FileHash (Join-Path $Root 'bootstrap.ps1'), (Join-Path $Root 'steps.json') -Algorithm SHA256 | Select-Object Path, Hash | ConvertTo-Json | Set-Content (Join-Path $Evidence 'tested-source-hashes.json') -Encoding UTF8
  $text = (Get-Content (Join-Path $Root 'bootstrap.ps1') -Raw -Encoding UTF8) -replace "`r`n", "`n"
  $marker = "`nLoad-Config`nif (`$DryRun)"
  $idx = $text.IndexOf($marker, [StringComparison]::Ordinal)
  if ($idx -lt 0) { throw 'Bootstrap function boundary not found' }
  $tail = @'
Load-Config
Init-State
# Explicit synthetic authentication fixture, never a real authenticated account.
$State | Add-Member -NotePropertyName TEST_SYNTHETIC_BYPASS -NotePropertyValue $true -Force
foreach ($id in @('S00_PREFLIGHT','S01_CLAUDE_INSTALL','S02_CLAUDE_LOGIN')) {
  Update-Step $id 'passed' 0 '' ([ordered]@{ TEST_SYNTHETIC_BYPASS = $true; fixture = 'post-login precondition; not executed' })
}
$auth = Join-Path $WaveHome 'auth'
New-Item -ItemType Directory -Force $auth | Out-Null
Set-Content (Join-Path $auth 'claude-authenticated') 'TEST_SYNTHETIC_BYPASS'
# Reproduce the exact pre-fix scheduling operation with real installed cysd.
foreach ($n in 3..9) {
  $step = $Config.steps | Where-Object { $_.id -like ('S{0:D2}_*' -f $n) }
  if ($n -eq 5) {
    $runtimePath = Join-Path $WaveHome 'daemon'
    $runtimeItem = Get-Item -LiteralPath $runtimePath -Force -ErrorAction SilentlyContinue
    $runtimeAcl = if ($runtimeItem) { (Get-Acl -LiteralPath $runtimePath).Sddl } else { $null }
    @{ path = $runtimePath; exists = [bool]$runtimeItem; is_directory = $(if ($runtimeItem) { $runtimeItem.PSIsContainer } else { $null }); acl = $runtimeAcl; handle_measurement = 'not measured'; daemon_processes = @(Get-Process cysd -ErrorAction SilentlyContinue | Select-Object Id, Path) } | ConvertTo-Json -Depth 5 | Set-Content (Join-Path $env:WAVE_CI_EVIDENCE 'daemon-path-before-s05.json') -Encoding UTF8
    # Measure the original mkdir call on the natural post-S04 path. A missing
    # collision is not proof of the incident hypothesis.
    $natural = [ordered]@{ synthetic = $false; path = $runtimePath; old_call = 'New-Item -ItemType Directory -Force -Path $WaveHome\\daemon'; outcome = 'not_reproduced'; error = $null; error_id = $null }
    $createdNaturalDirectory = $false
    try {
      New-Item -ItemType Directory -Force -Path $runtimePath -ErrorAction Stop | Out-Null
      $createdNaturalDirectory = -not [bool]$runtimeItem
    } catch {
      $natural.error = $_.Exception.Message
      $natural.error_id = $_.FullyQualifiedErrorId
      if ($natural.error -match '(?i)access.*denied|액세스.*거부') { $natural.outcome = 'access_denied_reproduced' }
    } finally {
      $natural | ConvertTo-Json -Depth 5 | Set-Content (Join-Path $env:WAVE_CI_EVIDENCE 'daemon-natural-old-call.json') -Encoding UTF8
      # Restore an originally absent path so this probe cannot create the very
      # directory/file collision that later daemon startup is meant to measure.
      if ($createdNaturalDirectory) { [IO.Directory]::Delete($runtimePath, $false) }
    }
    $savedWaveHome = $WaveHome
    $savedDaemonOption = $env:WAVE_ENABLE_DAEMON
    $savedStepObserved = $StepObserved
    $savedStepStatus = $StepStatus
    $fixtureHome = Join-Path $env:USERPROFILE ('daemon-lock-fixture-' + [guid]::NewGuid().ToString('N'))
    New-Item -ItemType Directory -Path $fixtureHome | Out-Null
    $fixturePath = Join-Path $fixtureHome 'daemon'
    $fixtureEvidence = [ordered]@{ synthetic = $true; scope = 'isolated exclusive file lock; not the natural runtime path'; path = $fixturePath; file_share = 'None'; old_call_outcome = 'not_reproduced'; old_error = $null; old_error_id = $null; new_call_succeeded = $false; installer_result = $null; failure = $null }
    $lock = $null
    try {
      $lock = [IO.File]::Open($fixturePath, [IO.FileMode]::CreateNew, [IO.FileAccess]::ReadWrite, [IO.FileShare]::None)
      try {
        New-Item -ItemType Directory -Force -Path $fixturePath -ErrorAction Stop | Out-Null
      } catch {
        $fixtureEvidence.old_error = $_.Exception.Message
        $fixtureEvidence.old_error_id = $_.FullyQualifiedErrorId
        if ($fixtureEvidence.old_error -match '(?i)access.*denied|액세스.*거부') { $fixtureEvidence.old_call_outcome = 'access_denied_reproduced' }
      }
      # Keep the exclusive lock held while calling the unmodified new Run-S05.
      $script:WaveHome = $fixtureHome
      $env:WAVE_ENABLE_DAEMON = '0'
      Run-S05
      $fixtureResult = Join-Path $fixtureHome 'install\daemon-register-result'
      $fixtureEvidence.installer_result = $fixtureResult
      if (-not (Test-Path -LiteralPath $fixtureResult -PathType Leaf)) { throw 'New S05 did not create its installer-owned result' }
      if ((Get-Content -LiteralPath $fixtureResult -Raw).Trim() -cne 'skipped_by_user' -or $StepStatus -cne 'skipped') { throw 'New S05 disabled-daemon result mismatch' }
      $fixtureEvidence.new_call_succeeded = $true
      if ($fixtureEvidence.old_call_outcome -ne 'access_denied_reproduced') { throw 'Synthetic locked-file old-call Access denied control not reproduced; inspect exact error' }
    } catch {
      $fixtureEvidence.failure = $_.Exception.Message
      throw
    } finally {
      if ($null -ne $lock) { $lock.Dispose() }
      $script:WaveHome = $savedWaveHome
      if ($null -eq $savedDaemonOption) { Remove-Item Env:WAVE_ENABLE_DAEMON -ErrorAction SilentlyContinue } else { $env:WAVE_ENABLE_DAEMON = $savedDaemonOption }
      $script:StepObserved = $savedStepObserved
      $script:StepStatus = $savedStepStatus
      $fixtureEvidence | ConvertTo-Json -Depth 5 | Set-Content (Join-Path $env:WAVE_CI_EVIDENCE 'daemon-locked-file-control.json') -Encoding UTF8
    }
    $oldPreference = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    $denial = & schtasks /Create /TN ('WaveTerminal-cysd-' + $env:USERNAME) /SC ONLOGON /TR (Join-Path $WaveHome 'bin\cysd.exe') /F 2>&1 | Out-String
    $code = $LASTEXITCODE
    $ErrorActionPreference = $oldPreference
    @{ exit_code = $code; output = $denial; expected = 'Access is denied'; synthetic = $false } | ConvertTo-Json | Set-Content (Join-Path $env:WAVE_CI_EVIDENCE 'schtasks-control.json') -Encoding UTF8
    if ($code -eq 0 -or $denial -notmatch 'Access is denied|Access denied|액세스가 거부') { throw 'Old S05 access-denied control not reproduced' }
  }
  if ($n -eq 9) { Mark-RequiredComplete }
  Say-Step $step 'CI: actual function with synthetic authentication precondition'
  $fn = 'Run-S{0:D2}' -f $n
  Invoke-Step $step.id { & $fn }
  if ($n -eq 6) {
    $wrapperPaths = @((Join-Path $env:WAVE_CI_ROOT 'wave-pack\bin\wave.ps1'), (Join-Path $ScriptDir 'wave-pack\bin\wave.ps1'), (Join-Path $PackHome 'bin\wave.ps1'), (Join-Path $WaveHome 'bin\wave.ps1'))
    $wrapperHashes = @(Get-FileHash -LiteralPath $wrapperPaths -Algorithm SHA256 | Select-Object Path, Hash)
    $wrapperHashes | ConvertTo-Json | Set-Content (Join-Path $env:WAVE_CI_EVIDENCE 'wave-wrapper-copy-hashes.json') -Encoding UTF8
    if (@($wrapperHashes.Hash | Select-Object -Unique).Count -ne 1) { throw 'Checkout/fixture/pack/installed wave.ps1 hashes differ' }
  }
}
Complete-State
'@
  $env:WAVE_CI_EVIDENCE = $Evidence
  $env:WAVE_CI_ROOT = $Root
  $harness = Join-Path $run 'post-login.ps1'
  ($text.Substring(0, $idx) + "`n" + $tail) | Set-Content $harness -Encoding UTF8
  & powershell -NoProfile -ExecutionPolicy Bypass -File $harness
  exit $LASTEXITCODE
} finally { Stop-Transcript | Out-Null }
