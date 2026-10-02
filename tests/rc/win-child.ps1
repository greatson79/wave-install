# 비관리자 새 계정 안에서 실행(PowerShell 5.1). 시험 릴리스 한 줄 그대로 → G1-CI/G2/G3/G4-CI(+G5/G6) 증거.
#  win-child.ps1 -Mode main|upgrade -RcJson <rc-release.json> -Evidence <폴더> -Repo <체크아웃> -Py <러너 python.exe>
[CmdletBinding()] param([string]$Mode, [string]$RcJson, [string]$Evidence, [string]$Repo, [string]$Py)
$ErrorActionPreference = 'Continue'; $ProgressPreference = 'SilentlyContinue'
Start-Transcript -Path (Join-Path $Evidence 'child.log') -Force | Out-Null
$rc = Join-Path $Repo 'tests\rc'; $h = $env:USERPROFILE
$id = [Security.Principal.WindowsIdentity]::GetCurrent(); $admin = (New-Object Security.Principal.WindowsPrincipal($id)).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
@{ user = $id.Name; administrator = $admin; profile = $h; ps = $PSVersionTable.PSVersion.ToString() } | ConvertTo-Json | Set-Content (Join-Path $Evidence 'identity.json') -Encoding UTF8
if ($admin) { throw 'administrator token is prohibited' }
$one = (Get-Content $RcJson -Raw -Encoding UTF8 | ConvertFrom-Json).one_line
function OneLine([string]$line, [string]$log) { $o = (Invoke-Expression $line 2>&1 | Out-String); $o | Set-Content $log -Encoding UTF8; return $LASTEXITCODE }
function Reset-Fleet {
  Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -match 'fake_claude\.py|cysd' } | ForEach-Object { & taskkill /PID $_.ProcessId /T /F 2>&1 | Out-Null }
  Remove-Item (Join-Path $h '.cys\.master-bootstrapped') -Force -ErrorAction SilentlyContinue
  Remove-Item (Join-Path $h '.wave\rc') -Recurse -Force -ErrorAction SilentlyContinue; Start-Sleep 2
}
function Install-Fake {
  $bin = Join-Path $h '.local\bin'; New-Item -ItemType Directory -Force (Join-Path $bin 'claude') | Out-Null
  Copy-Item (Join-Path $rc 'fake_claude.py') (Join-Path $bin 'claude\fake_claude.py') -Force
  "@echo off`r`n`"$Py`" `"%~dp0claude\fake_claude.py`" %*`r`n" | Set-Content (Join-Path $bin 'claude.cmd') -Encoding ASCII
  $env:PATH = "$bin;$env:PATH"
  [Environment]::SetEnvironmentVariable('Path', "$bin;" + [Environment]::GetEnvironmentVariable('Path', 'User'), 'User')
}
function Collect([string]$d) {
  New-Item -ItemType Directory -Force $d | Out-Null
  $wb = Join-Path $h '.wave\bin'; $env:PATH = "$wb;$env:PATH"
  $bp = Join-Path $wb 'runtime\python\python3.exe'; if (-not (Test-Path $bp)) { $bp = $Py }
  & $Py (Join-Path $rc 'collect.py') g2 --out $d --python $bp --preflight (Join-Path $h '.cys\pack\bin\javis_preflight.py')
  cmd /c "`"$wb\cys.exe`" pack-manifest > `"$d\pack-manifest.src.json`""
  & $Py (Join-Path $rc 'collect.py') g3 --out $d --manifest "$d\pack-manifest.src.json"
  & $Py (Join-Path $rc 'collect.py') g4 --out $d --cys "$wb\cys.exe"
}
$e = Join-Path $Evidence 'win'; New-Item -ItemType Directory -Force $e | Out-Null
try {
  if ($Mode -eq 'upgrade') {
    $g5 = Join-Path $e 'G5'; New-Item -ItemType Directory -Force $g5 | Out-Null; Install-Fake
    $old = ((Get-Content (Join-Path $Repo 'README.md') -Encoding UTF8) | Where-Object { $_ -like 'powershell *install-wave.ps1*' } | Select-Object -First 1) -replace 'download/v[0-9.]+/', 'download/v0.2.3/'
    OneLine $old (Join-Path $g5 'from_v023.log') | Out-Null
    Copy-Item (Join-Path $h '.wave\install-state.json') (Join-Path $g5 'from_v023_state.json') -ErrorAction SilentlyContinue
    $from = (Get-Content (Join-Path $g5 'from_v023_state.json') -Raw | ConvertFrom-Json).installer_version
    if ($from -ne '0.2.3') { Write-Host "v0.2.3 이 아님($from) — G5 측정 불가"; return }
    $sha = (Get-FileHash (Join-Path $g5 'from_v023_state.json') -Algorithm SHA256).Hash.ToLower()
    "{`"from_version`":`"$from`",`"raw`":[{`"path`":`"from_v023_state.json`",`"sha256`":`"$sha`"}]}" | Set-Content (Join-Path $g5 'G5_meta.json') -Encoding ASCII
    Reset-Fleet; OneLine $one (Join-Path $g5 'run.log') | Out-Null; Collect $g5
    return
  }
  New-Item -ItemType Directory -Force (Join-Path $e 'phaseA'), (Join-Path $e 'G6') | Out-Null
  OneLine $one (Join-Path $e 'phaseA\run.log') | Out-Null
  Copy-Item (Join-Path $h '.wave\install-state.json') (Join-Path $e 'phaseA\state.json') -ErrorAction SilentlyContinue
  Install-Fake
  OneLine $one (Join-Path $e 'run.log') | Out-Null
  Copy-Item (Join-Path $h '.wave\install-state.json') (Join-Path $e 'G1_state.json')
  Collect $e
  Copy-Item (Join-Path $h '.wave\rc') (Join-Path $e 'rc-synthetic-logs') -Recurse -ErrorAction SilentlyContinue
  & $Py (Join-Path $rc 'collect.py') claude-hash --out (Join-Path $e 'G6') --phase before
  Reset-Fleet
  (Invoke-Expression "powershell -NoProfile -ExecutionPolicy Bypass -File `"$h\install-wave.ps1`" -Reinstall" 2>&1 | Out-String) | Set-Content (Join-Path $e 'G6\run.log') -Encoding UTF8
  Collect (Join-Path $e 'G6')
  & $Py (Join-Path $rc 'collect.py') claude-hash --out (Join-Path $e 'G6') --phase after
} finally { Stop-Transcript | Out-Null }
