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

function Row($ref, $role, $alive = $true, $exited = $false, $injected = $true) { [pscustomobject]@{ surface_ref = $ref; role = $role; exited = $exited; agent_alive = $alive; launch_complete = $injected } }

if ($Mode -eq 'unit') {
  if ((Get-AwakeningBudgetMs 420000) -ne 0) { throw 'no pause: deadline moved' }
  $script:GatePausedMs = 60000
  if ((Get-AwakeningBudgetMs 420000) -ne 5000) { throw 'pause not added to the budget' }
  if ((Get-AwakeningBudgetMs 479999) -ne 1) { throw 'paused deadline boundary' }
  if ((Get-AwakeningBudgetMs 480000) -ne 0) { throw 'paused deadline not enforced' }
  $script:GatePausedMs = 0
  Write-Host 'PASS budget = 420s + paused gate time'

  $all = [pscustomobject]@{ surfaces = @((Row 'surface:1' 'master'), (Row 'surface:2' 'cso'), (Row 'surface:3' 'worker-2'), (Row 'surface:4' 'reviewer-codex'), (Row 'surface:5' 'cso' $false)) }
  if ((@(Get-LiveRoleSeats $all) -join ',') -ne 'cso,master,worker') { throw 'live role seats wrong' }
  if (@(Get-LiveRoleSeats $null).Count -ne 0) { throw 'null status not empty' }
  Write-Host 'PASS live role seats = live master/cso/worker only'

  if ((Get-InjectedRoleCount $all) -ne 3) { throw 'injected role count' }
  function Get-LiveFleet([int]$TimeoutMs = 5000) { return $script:Fleet }
  $script:Fleet = [pscustomobject]@{ surfaces = @((Row 'surface:1' 'master'), (Row 'surface:2' 'cso'), (Row 'surface:3' 'worker')) }
  $msg = ''; try { Complete-S07Unfinished } catch { $msg = $_.Exception.Message }
  if ($msg -ne 'W-FLEET-ALIVE-UNCONFIRMED' -or -not $script:AliveUnconfirmed) { throw "alive fleet not flagged ($msg)" }
  if ($StepObserved.fleet_started -ne $false -or $StepObserved.fleet_state -ne 'alive_unconfirmed' -or $StepObserved.seats_alive -ne 3 -or $StepObserved.j_code -ne 'J-VER-04') { throw 'observed contract' }
  if ((Get-JCode $msg) -ne 'J-VER-04') { throw 'W-FLEET-ALIVE-UNCONFIRMED not mapped to J-VER-04' }
  if (($script:Said -join ' ') -notmatch '세 칸 생존 · master 첫 답을 확인하세요' -or ($script:Said -join ' ') -notmatch '같은 설치 명령을 다시 실행') { throw 'next-step line missing' }
  foreach ($case in @(
      @{ rows = @((Row 'surface:1' 'master'), (Row 'surface:2' 'cso'), (Row 'surface:3' 'worker' $true $false $false)); want = '지침 주입 확인 2/3' },
      @{ rows = @((Row 'surface:1' 'master'), (Row 'surface:3' 'worker')); want = '살아 있는 칸 2/3' },
      @{ rows = @((Row 'surface:1' 'master' $false), (Row 'surface:2' 'cso' $false $true)); want = '살아 있는 칸 0/3' })) {
    $script:AliveUnconfirmed = $false
    $script:Fleet = [pscustomobject]@{ surfaces = $case.rows }
    $msg = ''; try { Complete-S07Unfinished } catch { $msg = $_.Exception.Message }
    if ($script:AliveUnconfirmed -or $msg -notmatch '420초' -or $msg -notmatch [regex]::Escape($case.want)) { throw "must stay a failure: $($case.want) ($msg)" }
  }
  $env:USERPROFILE = $env:RC4_FIXTURE_DIR
  Write-WaitingFor ([pscustomobject]@{ surfaces = @((Row 'surface:1' 'master'), (Row 'surface:2' 'cso')) })
  if (($script:Logged -join ' ') -notmatch '기다리는 것: 각성 표지 없음 · 좌석 2/3 · 지침 주입 2/3') { throw "waiting line: $($script:Logged -join ' ')" }
  Write-Host 'PASS waiting line: marker / seats n/3 / injection n/3'
  Write-Host 'PASS unfinished: alive seats -> alive_unconfirmed, none alive -> failure'
  exit 0
}

if ($Mode -eq 'exit2') {
  $script:Rec = Join-Path $env:RC4_FIXTURE_DIR 'rec.txt'
  $Config = [pscustomobject]@{ steps = @([pscustomobject]@{ id = 'S07_INITIAL_FLEET'; optional = $false; on_fail = [pscustomobject]@{ error_id = 'WT-S07-FLEET' } }) }
  function Send-Progress { }
  function Update-Step([string]$Id, [string]$Status, [int]$ExitCode, [string]$ErrorId, [object]$Observed) { Add-Content $script:Rec "$Id|$Status|$ExitCode|$ErrorId" }
  function Write-JCode([string]$Code) { Add-Content $script:Rec "jcode|$Code" }
  Invoke-Step 'S07_INITIAL_FLEET' { $script:AliveUnconfirmed = $true; $script:StepObserved = [ordered]@{ fleet_started = $false }; throw 'W-FLEET-ALIVE-UNCONFIRMED' }
  Write-Host 'NOT REACHED'; exit 9
}
