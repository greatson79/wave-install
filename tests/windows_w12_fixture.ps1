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
$live=[pscustomobject]@{surfaces=@([pscustomobject]@{surface_ref='surface:1';role='master';exited=$false;agent_alive=$true;directive_verified=$true;awakened_at=1},[pscustomobject]@{surface_ref='surface:2';role='worker-1';exited=$false;agent_alive=$true;directive_verified=$true;awakened_at=1})}
$marker=Join-Path $env:USERPROFILE '.cys/.master-bootstrapped'
'{"surface_ref":"surface:1","orchestra_check":"exit 0"}'|Set-Content $marker
if(-not(Test-AwakenedFleet $live)){throw 'valid fleet rejected'}
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
