$ErrorActionPreference='Stop'
$t=$null;$errors=$null
$ast=[System.Management.Automation.Language.Parser]::ParseFile((Join-Path $PWD 'bootstrap.ps1'),[ref]$t,[ref]$errors)
if($errors.Count){$errors|Out-String|Write-Host;exit 1}
$ast.FindAll({param($n) $n -is [System.Management.Automation.Language.FunctionDefinitionAst]},$false) | ForEach-Object {Invoke-Expression $_.Extent.Text}
$env:USERPROFILE=$env:W12_FIXTURE_HOME
$WaveHome=Join-Path $env:USERPROFILE '.wave';$PackHome=Join-Path $env:USERPROFILE '.cys/pack';$ScriptDir=Join-Path $env:USERPROFILE 'bundle'
$script:AwakeningStartedAt=$null
New-Item -ItemType Directory -Force (Join-Path $ScriptDir 'wave-pack/directives'),(Join-Path $PackHome 'directives')|Out-Null
$stub=Join-Path $ScriptDir 'wave-pack/directives/MASTER_DIRECTIVE.md';$target=Join-Path $PackHome 'directives/MASTER_DIRECTIVE.md'
[IO.File]::WriteAllText($stub,'old stub');Copy-Item $stub $target
[IO.File]::WriteAllText(($target+'.new'),'previous original')
$env:CYS_PACK_DIR='sentinel-parent-pack'
$script:Original='full app directive';$script:Hash=''
function Invoke-BoundedCheck($FilePath,$Arguments,$Name,$TimeoutMs){
 if($Arguments[0] -eq 'init-pack'){[IO.File]::WriteAllText($target,$script:Original);$script:Hash=Get-ArtifactHash $target;return [pscustomobject]@{timed_out=$false;exit_code=0;stderr='';stdout=''}}
 return [pscustomobject]@{timed_out=$false;exit_code=0;stderr='';stdout=('{"files":{"directives/MASTER_DIRECTIVE.md":"'+$script:Hash+'"}}')}
}
Run-S06
if($env:CYS_PACK_DIR -ne 'sentinel-parent-pack'){throw 'pack environment leaked'}
if(Test-Path ($target+'.new')){throw 'legacy sidecar left behind'}
if(-not $StepObserved.directive_bytes_match -or $StepObserved.legacy_backed_up.Count -ne 1){throw 'S06 migration assertion'}
$live=[pscustomobject]@{surfaces=@([pscustomobject]@{surface_ref='surface:1';role='master';exited=$false;agent_alive=$true},[pscustomobject]@{surface_ref='surface:2';role='worker-1';exited=$false;agent_alive=$true})}
$marker=Join-Path $env:USERPROFILE '.cys/.master-bootstrapped'
'{"surface_ref":"surface:1","orchestra_check":"exit 0"}'|Set-Content $marker
if(Test-AwakenedFleet $live){throw 'missing CSO accepted'}
$live.surfaces += [pscustomobject]@{surface_ref='surface:3';role='cso';exited=$false;agent_alive=$true}
if(-not(Test-AwakenedFleet $live)){throw 'valid three-seat fleet rejected'}
$live.surfaces[2].agent_alive=$false
if(Test-AwakenedFleet $live){throw 'dead CSO accepted'}
$live.surfaces[2].agent_alive=$true
$live.surfaces += [pscustomobject]@{surface_ref='surface:4';role='reviewer';exited=$true;agent_alive=$false}
if(-not(Test-AwakenedFleet $live)){throw 'reviewer incorrectly required'}
$live.surfaces[1].agent_alive=$false
if(Test-AwakenedFleet $live){throw 'dead child accepted'}
Write-Host 'PASS parser; S06 exact stub backup + app hash; live marker; dead child rejected'
$live.surfaces[1].agent_alive=$true
$script:AwakeningStartedAt=[DateTime]::UtcNow.AddMinutes(1)
if(Test-AwakenedFleet $live){throw 'stale marker accepted'}
$script:AwakeningStartedAt=$null
[IO.File]::WriteAllText($target,'custom user text')
function Invoke-BoundedCheck($FilePath,$Arguments,$Name,$TimeoutMs){
 if($Arguments[0] -eq 'init-pack'){[IO.File]::WriteAllText(($target+'.new'),'new original');return [pscustomobject]@{timed_out=$false;exit_code=0;stderr='';stdout=''}}
 return [pscustomobject]@{timed_out=$false;exit_code=0;stderr='';stdout=('{"files":{"directives/MASTER_DIRECTIVE.md":"'+$script:Hash+'"}}')}
}
$blocked=$false
try {Run-S06} catch {$blocked=$true}
if(-not $blocked -or [IO.File]::ReadAllText($target) -ne 'custom user text'){throw 'custom preservation fail'}
Write-Host 'PASS stale marker rejected; custom directive preserved; mismatch/new blocked'

if((Get-AwakeningBudgetMs 0) -ne 5000){throw 'initial status budget wrong'}
if((Get-AwakeningBudgetMs 419999) -ne 1){throw 'remaining budget not enforced'}
if((Get-AwakeningBudgetMs 420000) -ne 0){throw 'deadline not enforced'}
if((Get-AwakeningBudgetMs 420001) -ne 0){throw 'expired deadline became negative'}
$runText=($ast.FindAll({param($n) $n -is [System.Management.Automation.Language.FunctionDefinitionAst] -and $n.Name -eq 'Run-S07'},$false))[0].Extent.Text
if($runText -match 'for \(\$attempt' -or $runText -notmatch 'Stopwatch.*StartNew' -or $runText -notmatch 'Get-LiveFleet \(Get-AwakeningBudgetMs'){throw 'deadline wiring absent'}
Write-Host 'PASS CSO required/alive; reviewer excluded; 420-second remaining budget boundaries'
function Start-WaveApp { }
$HelpRules=[object[]]([regex]::Match((Get-Content (Join-Path $PWD 'bootstrap.ps1') -Raw),"(?s)\`$HelpRulesJson = @'\r?\n(.*?)\r?\n'@").Groups[1].Value|ConvertFrom-Json)
function Invoke-BoundedCheck($FilePath,$Arguments,$Name,$TimeoutMs){ return [pscustomobject]@{timed_out=$false;exit_code=0;stderr='';stdout="cys 9.9.9`n"} }
$onboarded=Join-Path $env:USERPROFILE '.cys/.gui-onboarded'
$clock=[Diagnostics.Stopwatch]::StartNew()
$blocked=$false; try {Wait-GuiOnboarded $clock 300} catch {$blocked=($_.Exception.Message -match 'W-ONBOARD' -and (Get-JCode $_.Exception.Message) -eq 'J-VER-02')}
if(-not $blocked){throw 'missing onboarding marker accepted or wrong J-code'}
'9.9.8'|Set-Content $onboarded
$blocked=$false; try {Wait-GuiOnboarded $clock 300} catch {$blocked=$true}
if(-not $blocked){throw 'onboarding marker of another app version accepted'}
"9.9.9`n"|Set-Content $onboarded
Wait-GuiOnboarded $clock 300
Write-Host 'PASS onboarding marker wait: absent/mismatch blocked (J-VER-02), matching version accepted'
function Get-LiveFleet([int]$TimeoutMs=5000) {
  if($TimeoutMs -le 0 -or $TimeoutMs -gt 5000){throw 'invalid status timeout budget'}
  return $live
}
Run-S07
if(-not $StepObserved.fleet_started -or $StepObserved.seats -ne 3 -or ($StepObserved.roles -join ',') -ne 'master,cso,worker'){throw 'three-seat observed contract mismatch'}
Write-Host 'PASS S07 observed roles and live status timeout budget'
$live.surfaces[0] | Add-Member -NotePropertyName cwd -NotePropertyValue 'C:\Users\설치 user'
if((Get-MasterAwakeState $live) -ne 'unconfirmed'){throw 'awake confirmed without transcript'}
$proj=Join-Path $env:USERPROFILE '.cys/claude/projects/C--Users----user'
New-Item -ItemType Directory -Force $proj|Out-Null
'{"type":"user"}'|Set-Content (Join-Path $proj 's.jsonl')
if((Get-MasterAwakeState $live) -ne 'unconfirmed'){throw 'user-only transcript counted as awake'}
'{"type":"user"}','{"type":"assistant"}'|Set-Content (Join-Path $proj 's.jsonl')
if((Get-MasterAwakeState $live) -ne 'confirmed'){throw 'assistant reply not detected'}
$script:AwakeningStartedAt=[DateTime]::UtcNow.AddMinutes(1)
if((Get-MasterAwakeState $live) -ne 'unconfirmed'){throw 'stale transcript counted as awake'}
$script:AwakeningStartedAt=$null
Write-Host 'PASS master awake evidence: assistant record confirmed; user-only/stale/missing unconfirmed'
$script:calls=@(); $script:launched=$false; $script:sendExit=0
'9.9.9'|Set-Content $onboarded
function Get-LiveFleet([int]$TimeoutMs=5000) { if($script:launched){return $live}; return [pscustomobject]@{surfaces=@()} }
function Invoke-BoundedCheck($FilePath,$Arguments,$Name,$TimeoutMs){
 $script:calls += ($Arguments -join ' ')
 if($Arguments[0] -eq 'launch-agent'){$script:launched=$true;'{"surface_ref":"surface:1","orchestra_check":"exit 0"}'|Set-Content $marker}
 return [pscustomobject]@{timed_out=$false;exit_code=$(if($Arguments[0] -eq 'send'){$script:sendExit}else{0});stderr='';stdout="cys 9.9.9`n"}
}
Run-S07
$li=[array]::FindIndex([string[]]$script:calls,[Predicate[string]]{param($c) $c -like 'launch-agent --role master*'})
$si=[array]::FindIndex([string[]]$script:calls,[Predicate[string]]{param($c) $c -like 'send --queued --to master "너는 마스터다 — *'})
if($li -lt 0 -or $si -le $li -or $script:calls[$si].Contains("`n")){throw 'declaration not queued after launch-agent'}
$script:calls=@(); $script:launched=$false; $script:sendExit=3
$blocked=$false; try {Run-S07} catch {$blocked=((Get-JCode $_.Exception.Message) -eq 'J-PATH-02')}
if(-not $blocked){throw 'declaration send failure not mapped to J-PATH-02'}
Write-Host 'PASS master launch-agent then queued one-line declaration; send failure J-PATH-02'
