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
}
Complete-State
'@
  $env:WAVE_CI_EVIDENCE = $Evidence
  $harness = Join-Path $run 'post-login.ps1'
  ($text.Substring(0, $idx) + "`n" + $tail) | Set-Content $harness -Encoding UTF8
  & powershell -NoProfile -ExecutionPolicy Bypass -File $harness
  exit $LASTEXITCODE
} finally { Stop-Transcript | Out-Null }
