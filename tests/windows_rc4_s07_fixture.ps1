# rc.4 S07 (윈): 확인 창이 떠 있는 동안 예산 정지 · 상한 도달 시 좌석이 살아 있으면 종료값 2. 데몬·앱·실제 홈을 쓰지 않는다.
param([string]$Mode = 'unit')
$ErrorActionPreference = 'Stop'
$t = $null; $errors = $null
$ast = [System.Management.Automation.Language.Parser]::ParseFile((Join-Path $PWD 'bootstrap.ps1'), [ref]$t, [ref]$errors)
if ($errors.Count) { $errors | Out-String | Write-Host; exit 1 }
$ast.FindAll({ param($n) $n -is [System.Management.Automation.Language.FunctionDefinitionAst] }, $false) | ForEach-Object { Invoke-Expression $_.Extent.Text }
$script:GatePausedMs = 0; $script:AliveUnconfirmed = $false; $script:GateVisible = $false
function Say([string]$m) { $script:Said += $m }
$script:Said = @()
$HelpRules=[object[]]([regex]::Match((Get-Content (Join-Path $PWD 'bootstrap.ps1') -Raw),"(?s)\`$HelpRulesJson = @'\r?\n(.*?)\r?\n'@").Groups[1].Value|ConvertFrom-Json)
$script:Logged = @()
function Write-Log([string]$m) { $script:Logged += $m }

Set-StrictMode -Version Latest   # 설치기와 같은 모드 — 없는 속성을 읽으면 예외(rc.4 윈 실기 RC 37134620023 의 실패 모양)
# 응답은 실물 cys 바이너리 출력의 녹취 고정본에서만 가져온다(머리 provenance 에 명령·시각·바이너리 커밋). 손으로 쓴 응답 금지 —
# 부정 사례는 녹취 응답의 행을 고르거나 한 필드(agent_alive·exited)를 뒤집어 만든다.
function Real([string]$Name) {
  $doc = Get-Content -LiteralPath (Join-Path $PWD "tests/fixtures/real_cys/$Name") -Raw -Encoding UTF8 | ConvertFrom-Json
  foreach ($k in 'command', 'recorded_at', 'binary') { if (-not $doc.provenance.$k) { throw "fixture $Name lacks provenance.$k" } }
  return $doc.response
}
function Only($Resp, [string[]]$Roles) { [pscustomobject]@{ surfaces = @($Resp.surfaces | Where-Object { $Roles -contains ([string]$_.role) }) } }

if ($Mode -eq 'unit') {
  foreach ($n in 'win_status_three_seats.json', 'win_status_noboot.json', 'mac_status_three_seats.json') {
    foreach ($row in (Real $n).surfaces) { if ($null -ne $row.PSObject.Properties['launch_complete']) { throw "${n}: status recording must not carry launch_complete" } }
  }
  if ((Get-AwakeningBudgetMs 420000) -ne 0) { throw 'no pause: deadline moved' }
  $script:GatePausedMs = 60000
  if ((Get-AwakeningBudgetMs 420000) -ne 5000) { throw 'pause not added to the budget' }
  if ((Get-AwakeningBudgetMs 479999) -ne 1) { throw 'paused deadline boundary' }
  if ((Get-AwakeningBudgetMs 480000) -ne 0) { throw 'paused deadline not enforced' }
  $script:GatePausedMs = 0
  Write-Host 'PASS budget = 420s + paused gate time'

  $three = Real 'win_status_three_seats.json'
  if ((@(Get-LiveRoleSeats $three) -join ',') -ne 'cso,master,worker') { throw 'live role seats (real three-seat status)' }
  if ((@(Get-LiveRoleSeats (Real 'win_status_noboot.json')) -join ',') -ne 'master') { throw 'live role seats (real noboot status)' }
  if (@(Get-LiveRoleSeats $null).Count -ne 0) { throw 'null status not empty' }
  Write-Host 'PASS live role seats = live master/cso/worker only'

  function Get-LiveFleet([int]$TimeoutMs = 5000) { return $script:Fleet }
  # 실물 모양(launch_complete 없음)에서도 세 칸 생존이면 종료값 2 경로 — 결재 (가)
  $script:Fleet = Real 'win_status_three_seats.json'
  $msg = ''; try { Complete-S07Unfinished } catch { $msg = $_.Exception.Message }
  if ($msg -ne 'W-FLEET-ALIVE-UNCONFIRMED' -or -not $script:AliveUnconfirmed) { throw "alive fleet not flagged ($msg)" }
  if ($StepObserved.fleet_started -ne $false -or $StepObserved.fleet_state -ne 'alive_unconfirmed' -or $StepObserved.seats_alive -ne 3 -or $StepObserved.j_code -ne 'J-VER-04') { throw 'observed contract' }
  if ($null -ne $StepObserved.launch_complete) { throw 'launch_complete must be null when the response carries no signal' }
  if ((Get-JCode $msg) -ne 'J-VER-04') { throw 'W-FLEET-ALIVE-UNCONFIRMED not mapped to J-VER-04' }
  $said = ($script:Said -join ' ')
  if ($said -match '실패' -or $said -match '주입') { throw 'exit-2 screen must state observed facts only' }
  if ($said -notmatch '세 칸이 살아 있습니다 · master 첫 답을 확인하세요' -or $said -notmatch '같은 설치 명령을 다시 실행') { throw 'next-step line missing' }
  # 신호가 있는 응답(surface.list 녹취의 행을 살아 있다고 뒤집은 것)에서는 개수만 기록한다
  $script:AliveUnconfirmed = $false
  $list = (Get-Content -LiteralPath (Join-Path $PWD 'tests/fixtures/real_cys/mac_surface_list.json') -Raw -Encoding UTF8 | ConvertFrom-Json).response.result
  foreach ($row in $list.surfaces) { $row.agent_alive = $true }
  $script:Fleet = $list
  $msg = ''; try { Complete-S07Unfinished } catch { $msg = $_.Exception.Message }
  if ($msg -ne 'W-FLEET-ALIVE-UNCONFIRMED' -or $StepObserved.launch_complete -ne 2) { throw "launch_complete must be recorded only ($msg / $($StepObserved.launch_complete))" }
  # 실패(좌석 부족·사망)
  $dead = Real 'win_status_three_seats.json'; foreach ($row in $dead.surfaces) { $row.agent_alive = $false }
  foreach ($case in @(
      @{ resp = (Real 'win_status_noboot.json'); want = '살아 있는 칸 1/3' },
      @{ resp = (Only (Real 'win_status_three_seats.json') @('master', 'cso')); want = '살아 있는 칸 2/3' },
      @{ resp = $dead; want = '살아 있는 칸 0/3' })) {
    $script:AliveUnconfirmed = $false
    $script:Fleet = $case.resp
    $msg = ''; try { Complete-S07Unfinished } catch { $msg = $_.Exception.Message }
    if ($script:AliveUnconfirmed -or $msg -notmatch '420초' -or $msg -notmatch [regex]::Escape($case.want)) { throw "must stay a failure: $($case.want) ($msg)" }
  }
  $env:USERPROFILE = $env:RC4_FIXTURE_DIR
  $script:Logged = @()
  Write-WaitingFor (Real 'win_status_noboot.json')
  if (($script:Logged -join ' ') -notmatch '기다리는 것: 각성 표지 없음 · 좌석 1/3' -or ($script:Logged -join ' ') -match '주입') { throw "waiting line: $($script:Logged -join ' ')" }
  Write-Host 'PASS waiting line: marker / seats n/3'
  Write-Host 'PASS unfinished: three live seats -> alive_unconfirmed (no failure wording), fewer/dead -> failure'
  exit 0
}

if ($Mode -eq 'exit2') {
  $script:Rec = Join-Path $env:RC4_FIXTURE_DIR 'rec.txt'
  $CurrentStep = '8/10'; $StepStatus = 'passed'; $DiagnosticWritten = $false   # 설치기가 전역에 두는 값(StrictMode 에서 미설정 변수 읽기 방지)
  $Config = [pscustomobject]@{ steps = @([pscustomobject]@{ id = 'S07_INITIAL_FLEET'; optional = $false; on_fail = [pscustomobject]@{ error_id = 'WT-S07-FLEET' } }) }
  function Send-Progress { }
  function Update-Step([string]$Id, [string]$Status, [int]$ExitCode, [string]$ErrorId, [object]$Observed) { Add-Content $script:Rec "$Id|$Status|$ExitCode|$ErrorId" }
  function Write-JCode([string]$Code) { Add-Content $script:Rec "jcode|$Code" }
  Invoke-Step 'S07_INITIAL_FLEET' { $script:AliveUnconfirmed = $true; $script:StepObserved = [ordered]@{ fleet_started = $false }; throw 'W-FLEET-ALIVE-UNCONFIRMED' }
  Write-Host 'NOT REACHED'; exit 9
}

if ($Mode -eq 'cwd') {
  # 2238 결재: 설치기가 띄우는 모든 cys 호출(데몬 자동기동 포함)은 홈에서 시작한다 — 호출자 cwd(예: 프로젝트 폴더)를 상속시키지 않는다.
  $home1 = Join-Path $env:RC4_FIXTURE_DIR 'userhome'; New-Item -ItemType Directory -Force $home1 | Out-Null
  $elsewhere = Join-Path $env:RC4_FIXTURE_DIR 'project'; New-Item -ItemType Directory -Force $elsewhere | Out-Null
  $env:USERPROFILE = $home1; $WaveHome = Join-Path $home1 '.wave'
  Set-Location $elsewhere
  $r = Invoke-BoundedCheck (Get-Process -Id $PID).Path @('-NoProfile', '-Command', '(Get-Location).Path') 'cwd' 20000
  $got = ([string]$r.stdout).Trim()
  # macOS 임시 폴더의 /private 별칭 차이만 흡수한다
  if (($got -replace '^/private', '') -ne ($home1 -replace '^/private', '')) { throw "child cwd was '$got', expected the user home" }
  Write-Host 'PASS bounded cys calls start in the user home'
  exit 0
}
