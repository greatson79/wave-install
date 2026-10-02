# 비관리자 새 계정 안에서 실행(PowerShell 5.1). 시험 릴리스 한 줄 그대로 → G1-CI/G2/G3/G4-CI(+G5/G6) 증거.
#  win-child.ps1 -Mode main|upgrade -RcJson <rc-release.json> -Evidence <폴더> -Repo <체크아웃> -Py <러너 python.exe>
[CmdletBinding()] param([string]$Mode, [string]$RcJson, [string]$Evidence, [string]$Repo, [string]$Py)
$ErrorActionPreference = 'Continue'; $ProgressPreference = 'SilentlyContinue'
$env:WAVE_NO_PROGRESS = '1'   # 실서버(waveainetworks.com) 진행 신호 전송 0 — 새 계정 환경은 러너 env 를 물려받지 않는다
Start-Transcript -Path (Join-Path $Evidence 'child.log') -Force | Out-Null
$rc = Join-Path $Repo 'tests\rc'; $h = $env:USERPROFILE
$id = [Security.Principal.WindowsIdentity]::GetCurrent(); $admin = (New-Object Security.Principal.WindowsPrincipal($id)).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
@{ user = $id.Name; administrator = $admin; profile = $h; ps = $PSVersionTable.PSVersion.ToString() } | ConvertTo-Json | Set-Content (Join-Path $Evidence 'identity.json') -Encoding UTF8
if ($admin) { throw 'administrator token is prohibited' }
$one = (Get-Content $RcJson -Raw -Encoding UTF8 | ConvertFrom-Json).one_line
function OneLine([string]$line, [string]$log, [int]$sec = 1500) {
  # 로그인 대기로 멈추지 않게: stdin 은 빈 파일, 25분 상한, 시간 초과 시 프로세스 트리 종료(exit 124)
  $enc = [Convert]::ToBase64String([Text.Encoding]::Unicode.GetBytes($line)); $empty = Join-Path $env:TEMP 'rc-empty.txt'; '' | Set-Content $empty
  $p = Start-Process powershell -ArgumentList @('-NoProfile', '-ExecutionPolicy', 'Bypass', '-EncodedCommand', $enc) -RedirectStandardOutput $log -RedirectStandardError "$log.err" -RedirectStandardInput $empty -PassThru -WindowStyle Hidden
  if (-not $p.WaitForExit($sec * 1000)) { & taskkill /PID $p.Id /T /F 2>&1 | Out-Null; Get-Process claude -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue; return 124 }
  return $p.ExitCode
}
function Reset-Fleet {
  Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -match 'fake_claude\.py|cysd' } | ForEach-Object { & taskkill /PID $_.ProcessId /T /F 2>&1 | Out-Null }
  Remove-Item (Join-Path $h '.cys\.master-bootstrapped') -Force -ErrorAction SilentlyContinue
  Remove-Item (Join-Path $h '.wave\rc') -Recurse -Force -ErrorAction SilentlyContinue; Start-Sleep 2
}
function Install-Fake {
  $bin = Join-Path $h '.local\bin'; New-Item -ItemType Directory -Force (Join-Path $bin 'claude') | Out-Null
  # 12차: S01 이 설치한 진짜 claude.exe 가 같은 폴더의 claude.cmd 보다 PATHEXT 순서(.EXE 가 .CMD 앞)로 먼저 잡혀 합성이 쓰이지 않고 실제 로그인으로 멈췄다 → 진짜는 이름을 바꿔 치운다(맥의 claude.real 과 같은 취급)
  foreach ($n in @('claude.exe')) { $real = Join-Path $bin $n; if (Test-Path $real) { Move-Item $real ($real + '.real') -Force } }
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
  Copy-Item (Join-Path $h '.wave\verify\G3_inject.json') (Join-Path $d 'installer_G3_inject.json') -ErrorAction SilentlyContinue
}
$e = Join-Path $Evidence 'win'; New-Item -ItemType Directory -Force $e | Out-Null
try {
  if ($Mode -eq 'upgrade') {
    $g5 = Join-Path $e 'G5'; New-Item -ItemType Directory -Force $g5 | Out-Null; Install-Fake
    $old = ((Get-Content (Join-Path $Repo 'README.md') -Encoding UTF8) | Where-Object { $_ -like 'powershell *install-wave.ps1*' } | Select-Object -First 1) -replace 'download/v[0-9.]+/', 'download/v0.2.3/'
    OneLine $old (Join-Path $g5 'from_v023.log') | Out-Null
    Copy-Item (Join-Path $h '.wave\install-state.json') (Join-Path $g5 'from_v023_state.json') -ErrorAction SilentlyContinue
    $m = [regex]::Match((Get-Content (Join-Path $g5 'from_v023.log') -Raw -Encoding UTF8), 'wave-install-(\d+\.\d+\.\d+)\.(tar\.gz|zip)'); $from = if ($m.Success) { $m.Groups[1].Value } else { 'unknown' }  # 공개 v0.2.3 상태 파일 installer_version 은 0.1.3 이라 받은 설치팩 주소로 판정
    if ($from -ne '0.2.3') { Write-Host "v0.2.3 이 아님($from) — G5 측정 불가"; return }
    $sha = (Get-FileHash (Join-Path $g5 'from_v023_state.json') -Algorithm SHA256).Hash.ToLower()
    "{`"from_version`":`"$from`",`"raw`":[{`"path`":`"from_v023_state.json`",`"sha256`":`"$sha`"}]}" | Set-Content (Join-Path $g5 'G5_meta.json') -Encoding ASCII
    Reset-Fleet; OneLine $one (Join-Path $g5 'run.log') | Out-Null; Collect $g5
    return
  }
  New-Item -ItemType Directory -Force (Join-Path $e 'phaseA'), (Join-Path $e 'G6') | Out-Null
  $env:BROWSER = 'false'; OneLine $one (Join-Path $e 'phaseA\run.log') 300 | Out-Null; Remove-Item Env:BROWSER
  Copy-Item (Join-Path $h '.wave\install-state.json') (Join-Path $e 'phaseA\state.json') -ErrorAction SilentlyContinue
  # 설치기가 시작 직후 죽는 경우(10차: Get-JCode 미인식)를 가리기 위한 진단 — 설치팩 bootstrap.ps1 의 파싱 결과·인코딩·함수 목록·설치 로그
  $pk = Get-ChildItem (Join-Path $h '.wave\src') -Recurse -Filter bootstrap.ps1 -ErrorAction SilentlyContinue | Select-Object -First 1
  if ($pk) {
    $lines = @()
    foreach ($f in @($pk) + @(Get-ChildItem (Join-Path $pk.DirectoryName 'lib') -Filter *.ps1 -ErrorAction SilentlyContinue)) {
      $tk = $null; $er = $null; $ast = [System.Management.Automation.Language.Parser]::ParseFile($f.FullName, [ref]$tk, [ref]$er)
      $bytes = [IO.File]::ReadAllBytes($f.FullName)
      $fn = @($ast.FindAll({ param($n) $n -is [System.Management.Automation.Language.FunctionDefinitionAst] }, $true) | ForEach-Object { $_.Name })
      $nonAscii = @($bytes | Where-Object { $_ -gt 127 }).Count
      $lines += "file=$($f.FullName)"; $lines += "  bytes=$($bytes.Length) head=$((($bytes[0..2] | ForEach-Object { $_.ToString('x2') }) -join ' ')) nonascii_bytes=$nonAscii sha256=$((Get-FileHash $f.FullName -Algorithm SHA256).Hash.ToLower())"
      $lines += "  parse_errors=$($er.Count)"; foreach ($x in $er) { $lines += '  ERR ' + $x.Message + ' @line ' + $x.Extent.StartLineNumber }
      $lines += "  functions($($fn.Count))=" + ($fn -join ',')
    }
    $lines | Set-Content (Join-Path $e 'phaseA\bootstrap_parse_check.txt') -Encoding UTF8
  }
  foreach ($lf in @('install.log', 'install-done.txt')) { Copy-Item (Join-Path $h ".wave\$lf") (Join-Path $e "phaseA\$lf") -ErrorAction SilentlyContinue }
  Install-Fake
  OneLine $one (Join-Path $e 'run.log') | Out-Null
  Copy-Item (Join-Path $h '.wave\install-state.json') (Join-Path $e 'G1_state.json')
  Collect $e
  Copy-Item (Join-Path $h '.wave\rc') (Join-Path $e 'rc-synthetic-logs') -Recurse -ErrorAction SilentlyContinue
  & $Py (Join-Path $rc 'collect.py') claude-hash --out (Join-Path $e 'G6') --phase before
  Reset-Fleet
  OneLine "powershell -NoProfile -ExecutionPolicy Bypass -File `"$h\install-wave.ps1`" -Reinstall" (Join-Path $e 'G6\run.log') | Out-Null
  Collect (Join-Path $e 'G6')
  & $Py (Join-Path $rc 'collect.py') claude-hash --out (Join-Path $e 'G6') --phase after
} finally { Stop-Transcript | Out-Null }
