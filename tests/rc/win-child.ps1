# 비관리자 새 계정 안에서 실행(PowerShell 5.1). 시험 릴리스 한 줄 그대로 → G1-CI/G2/G3/G4-CI(+G5/G6) 증거.
#  win-child.ps1 -Mode main|upgrade -RcJson <rc-release.json> -Evidence <폴더> -Repo <체크아웃> -Py <러너 python.exe>
[CmdletBinding()] param([string]$Mode, [string]$RcJson, [string]$Evidence, [string]$Repo, [string]$Py)
$ErrorActionPreference = 'Continue'; $ProgressPreference = 'SilentlyContinue'
$env:WAVE_NO_PROGRESS = '1'   # 실서버(waveainetworks.com) 진행 신호 전송 0 — 새 계정 환경은 러너 env 를 물려받지 않는다
$env:PYTHONUTF8 = '1'   # 한글 프로필 경로가 콘솔 코드페이지(cp1252)에서 파이썬을 깨지 않게
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
  # 네이티브 claude.exe 런처(ubuntu 에서 mingw 로 cross-compile, rcrel 에 동봉) — 이름이 처음부터 claude.exe 여야 cysd 워치독(앱 8e124a4 의 .exe 인식)이 잡는다. cfg 는 UTF-16LE(한글 경로 안전)
  $launcher = Join-Path (Split-Path -Parent $RcJson) 'claude-launcher.exe'
  if (Test-Path $launcher) {
    Copy-Item $launcher (Join-Path $bin 'claude.exe') -Force
    ($Py + "`r`n" + (Join-Path $bin 'claude\fake_claude.py') + "`r`n") | Set-Content (Join-Path $bin 'claude.cfg') -Encoding Unicode
  }
  $env:PATH = "$bin;$env:PATH"
  [Environment]::SetEnvironmentVariable('Path', "$bin;" + [Environment]::GetEnvironmentVariable('Path', 'User'), 'User')
}
function Collect([string]$d) {
  New-Item -ItemType Directory -Force $d | Out-Null
  $wb = Join-Path $h '.wave\bin'; $env:PATH = "$wb;$env:PATH"
  $bp = Join-Path $wb 'runtime\python\python3.exe'; if (-not (Test-Path $bp)) { $bp = $Py }
  $log = Join-Path $d 'collect.log'   # 14차: g2 수집기가 조용히 실패(G2_preflight.json 없음, 원인 로그 0) → 모든 수집기 stdout/stderr 를 파일로
  & $Py (Join-Path $rc 'collect.py') g2 --out $d --python $bp --preflight (Join-Path $h '.cys\pack\bin\javis_preflight.py') *>> $log
  cmd /c "`"$wb\cys.exe`" pack-manifest > `"$d\pack-manifest.src.json`""   # 14차에서 동작한 형태 — 8e37480 편집이 따옴표를 망가뜨려 17차 윈 G3 가 빠졌다
  & $Py (Join-Path $rc 'collect.py') g3 --out $d --manifest "$d\pack-manifest.src.json" *>> $log
  & $Py (Join-Path $rc 'collect.py') g4 --out $d --cys "$wb\cys.exe" *>> $log
  Copy-Item (Join-Path $h '.wave\verify\G3_inject.json') (Join-Path $d 'installer_G3_inject.json') -ErrorAction SilentlyContinue
}
$e = Join-Path $Evidence 'win'; New-Item -ItemType Directory -Force $e | Out-Null
try {
  if ($Mode -eq 'ctrlc') {
    # 측정 전용(관문 미산입): 설치 실패 → 도움 대기(대화형) 진입 → 실제 Ctrl+C 주입 → 종료값·상태 파일·남는 프로세스·도움 서버 close 호출을 기록한다.
    #  실패 주입 = 드라이버가 서빙 폴더에서 앱 설치 파일을 지워 둔다(S03 다운로드 실패). 대화형 판정 = 도움 서버 로그에 폴링(GET) 줄이 생겼는가.
    $cd = Join-Path $e 'ctrlc'; New-Item -ItemType Directory -Force $cd | Out-Null
    Install-Fake   # 합성 claude(auth 즉시 0) — 없으면 콘솔 stdin 에서 진짜 `claude auth login` 이 S02 에서 로그인 대기로 멈춘다(37096440885 실측: help_posted=false)
    Remove-Item Env:WAVE_NO_PROGRESS -ErrorAction SilentlyContinue   # 설정돼 있으면 설치기가 도움 요청을 건너뛴다
    $env:WAVE_HELP_BASE_URL = 'https://127.0.0.1:8443/'; $env:BROWSER = 'false'
    $helpLog = Join-Path $cd 'help_server.log'; $codeFile = Join-Path $cd 'exit_code.txt'
    $enc = [Convert]::ToBase64String([Text.Encoding]::Unicode.GetBytes($one))
    # 리다이렉트 없는 새 콘솔(숨김)에서 실행 — 설치기는 stdin·stdout 이 리다이렉트되지 않을 때만 대화형 대기에 들어간다. cmd /v:on 으로 설치기 종료값을 파일에 남긴다(Ctrl+C 에 cmd 가 먼저 죽지 않는지도 함께 본다)
    $victim = Start-Process cmd.exe -ArgumentList @('/v:on', '/d', '/c', ('powershell -NoProfile -ExecutionPolicy Bypass -EncodedCommand ' + $enc + ' & echo !errorlevel!> "' + $codeFile + '"')) -PassThru -WindowStyle Hidden
    $t0 = Get-Date; $posted = $false
    while (((Get-Date) - $t0).TotalSeconds -lt 600 -and -not $victim.HasExited) {
      if ((Test-Path $helpLog) -and (Select-String -Path $helpLog -Pattern 'POST /api/help$' -Quiet)) { $posted = $true; break }
      Start-Sleep 2
    }
    $meta = [ordered]@{ victim_pid = $victim.Id; help_posted = $posted; victim_exited_before_signal = $victim.HasExited; user = $id.Name }
    if ($posted) {
      Start-Sleep 25   # 첫 폴링(즉시)·두 번째 폴링(20초 뒤)까지 보여 대기 루프 진입을 확인
      $meta.polls_before_signal = @(Select-String -Path $helpLog -Pattern 'GET /api/help/').Count
      $meta.signal_time = (Get-Date).ToString('o')
      Start-Process powershell -ArgumentList @('-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', (Join-Path $rc 'ctrlc_send.ps1'), '-TargetPid', $victim.Id, '-Out', (Join-Path $cd 'ctrlc_send.json')) -Wait -WindowStyle Hidden
      $meta.exited_after_signal = $victim.WaitForExit(60000)
    }
    $meta.cmd_exit_code = if ($victim.HasExited) { $victim.ExitCode } else { $null }
    $meta.installer_exit_code_file = if (Test-Path $codeFile) { (Get-Content $codeFile -Raw).Trim() } else { $null }
    $meta.user_interactive = [Environment]::UserInteractive
    Start-Sleep 5
    $meta.closed_called = (Test-Path $helpLog) -and (Select-String -Path $helpLog -Pattern 'POST /api/help/.+/close' -Quiet)
    $meta.polls_total = if (Test-Path $helpLog) { @(Select-String -Path $helpLog -Pattern 'GET /api/help/').Count } else { 0 }
    $meta.remaining_processes = @(Get-CimInstance Win32_Process | Where-Object { $_.ProcessId -ne $PID -and $_.CommandLine -match 'install-wave|bootstrap\.ps1|wave-install|EncodedCommand|cysd|claude' } | ForEach-Object { '{0} {1}' -f $_.ProcessId, ($_.CommandLine -replace '\s+', ' ').Substring(0, [Math]::Min(200, ($_.CommandLine -replace '\s+', ' ').Length)) })
    foreach ($f in @('install-state.json', 'install.log', 'install-done.txt')) {
      $src = Join-Path $h ".wave\$f"; $meta["state_$($f -replace '\W','_')"] = Test-Path $src
      Copy-Item $src (Join-Path $cd $f) -ErrorAction SilentlyContinue
    }
    $meta | ConvertTo-Json -Depth 4 | Set-Content (Join-Path $cd 'ctrlc_result.json') -Encoding UTF8
    return
  }
  if ($Mode -eq 'upgrade') {
    $g5 = Join-Path $e 'G5'; New-Item -ItemType Directory -Force $g5 | Out-Null; Install-Fake
    $old = ((Get-Content (Join-Path $Repo 'README.md') -Encoding UTF8) | Where-Object { $_ -like 'powershell *install-wave.ps1*' } | Select-Object -First 1) -replace 'download/v[0-9.]+/', 'download/v0.2.3/'
    OneLine $old (Join-Path $g5 'from_v023.log') | Out-Null
    Copy-Item (Join-Path $h '.wave\install-state.json') (Join-Path $g5 'from_v023_state.json') -ErrorAction SilentlyContinue
    Copy-Item (Join-Path $h '.cys\pack\schedule.json') (Join-Path $g5 'installed_schedule_v023.json') -ErrorAction SilentlyContinue   # 증거만(G7b 기준 아님)
    # 윈 설치 로그에는 설치팩 주소가 안 찍힌다(13차) → 한 줄이 받아 실행한 ~\install-wave.ps1(릴리스가 주입한 zip 주소 보유)에서 판독
    $m = [regex]::Match((Get-Content (Join-Path $h 'install-wave.ps1') -Raw -Encoding UTF8), 'wave-install-(\d+\.\d+\.\d+)\.zip'); $from = if ($m.Success) { $m.Groups[1].Value } else { 'unknown' }
    if ($from -ne '0.2.3') { Write-Host "v0.2.3 이 아님($from) — G5 측정 불가"; return }
    $sha = (Get-FileHash (Join-Path $g5 'from_v023_state.json') -Algorithm SHA256).Hash.ToLower()
    "{`"from_version`":`"$from`",`"raw`":[{`"path`":`"from_v023_state.json`",`"sha256`":`"$sha`"}]}" | Set-Content (Join-Path $g5 'G5_meta.json') -Encoding ASCII
    Reset-Fleet; OneLine $one (Join-Path $g5 'run.log') | Out-Null; Collect $g5
    Copy-Item (Join-Path $h '.cys\pack\schedule.json') (Join-Path $g5 'installed_schedule_rc.json') -ErrorAction SilentlyContinue   # 증거만
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
  # 배포용 최상위 bootstrap에는 ZIP 해시가 주입된다. src 안의 재설치 파일은 ZIP 속 원본과 대조한다.
  $expectedBootstrapSha = (Get-FileHash -LiteralPath (Join-Path $Repo 'bootstrap.ps1') -Algorithm SHA256).Hash
  $installedBootstrap = Get-ChildItem -LiteralPath (Join-Path $h '.wave\src') -Recurse -Filter bootstrap.ps1 -File |
    Where-Object { (Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash -eq $expectedBootstrapSha } |
    Sort-Object FullName | Select-Object -First 1
  if (-not $installedBootstrap) { throw 'G6: installed bootstrap.ps1 missing' }
  if ((OneLine "powershell -NoProfile -ExecutionPolicy Bypass -File `"$($installedBootstrap.FullName)`" -Reinstall" (Join-Path $e 'G6\run.log')) -ne 0) { throw 'G6: reinstall failed' }
  Collect (Join-Path $e 'G6')
  & $Py (Join-Path $rc 'collect.py') claude-hash --out (Join-Path $e 'G6') --phase after
} finally { Stop-Transcript | Out-Null }
