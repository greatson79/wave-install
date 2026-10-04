param([string]$Mode='old')
$ErrorActionPreference='Stop'; Set-StrictMode -Version Latest
$t=$null; $e=$null
$a=[System.Management.Automation.Language.Parser]::ParseFile((Join-Path $PWD 'bootstrap.ps1'),[ref]$t,[ref]$e)
if($e.Count){throw ($e | Out-String)}
$a.FindAll({param($n) $n -is [System.Management.Automation.Language.FunctionDefinitionAst]},$false) | ForEach-Object {Invoke-Expression $_.Extent.Text}
$WaveHome=Join-Path $env:RC5_HOME 'wave'; $env:USERPROFILE=$env:RC5_HOME
New-Item -ItemType Directory -Force (Join-Path $env:USERPROFILE '.cys') | Out-Null
$raw=[IO.File]::ReadAllText((Join-Path $PWD 'tests/fixtures/real_cys/win_status_three_seats.json'))
$old=($raw | ConvertFrom-Json).response
$script:AwakeningStartedAt=$null
function Write-Log {}
if($Mode -eq 'old'){
  $ref=($old.surfaces | Where-Object {$_.role -eq 'master'} | Select-Object -First 1).surface_ref
  @{surface_ref=$ref;orchestra_check='exit 0'} | ConvertTo-Json | Set-Content (Join-Path $env:USERPROFILE '.cys/.master-bootstrapped')
  if(Test-AwakenedFleet $old){throw 'old app with marker must remain unconfirmed'}
  if($null -ne (Get-LaunchCompleteObserved $old)){throw 'missing signal must be null'}
  $script:AliveUnconfirmed=$false
  function Get-LiveFleet {return $old}
  function Say {}
  $msg='';try {Complete-S07Unfinished} catch {$msg=$_.Exception.Message}
  if($msg -ne 'W-FLEET-ALIVE-UNCONFIRMED' -or -not $script:AliveUnconfirmed -or $StepObserved.j_code -ne 'J-VER-04'){throw 'old app with marker must take exit-2 path'}
  Write-Host 'PASS old app remains unconfirmed under StrictMode'
} elseif($Mode -eq 'evidence'){
  function Invoke-BoundedCheck($FilePath,$Arguments,$Name,$TimeoutMs){
    if($Arguments[0] -eq 'list'){
      $list=(Get-Content (Join-Path $PWD 'tests/fixtures/real_cys/rc5_three_list.json') -Raw | ConvertFrom-Json).response
      return [pscustomobject]@{stdout=$list;stderr='';exit_code=0;timed_out=$false}
    }
    return [pscustomobject]@{stdout=($old | ConvertTo-Json -Depth 30);stderr='';exit_code=0;timed_out=$false}
  }
  Save-S07Evidence 2
  $dir=(Get-ChildItem (Join-Path $WaveHome 'fleet') -Directory)[0].FullName
  $r=Get-Content (Join-Path $dir 'result.json') -Raw | ConvertFrom-Json
  $roles=@(Get-Content (Join-Path $dir 'roles.json') -Raw | ConvertFrom-Json)
  if($r.installer_exit_code -ne 2 -or $r.list_exit_code -ne 0 -or $roles.Count -ne 3){throw 'snapshot evidence contract'}
  $want=(Get-Content (Join-Path $PWD 'tests/fixtures/real_cys/rc5_three_list.json') -Raw | ConvertFrom-Json).response
  if([IO.File]::ReadAllText((Join-Path $dir 'list.txt')) -ne $want){throw 'list raw text not preserved'}
  function Invoke-BoundedCheck {throw 'both unavailable'}
  Save-S07Evidence 1
  Write-Host 'PASS failure evidence preserves exit code and tolerates collection failure'
}
if($Mode -eq 'signals'){
  $ready=(Get-Content (Join-Path $PWD 'tests/fixtures/real_cys/rc5_three_status.json') -Raw | ConvertFrom-Json).response
  $partial=(Get-Content (Join-Path $PWD 'tests/fixtures/real_cys/rc5_partial_status.json') -Raw | ConvertFrom-Json).response
  if(-not(Test-AwakenedFleet $ready)){throw 'ready three-role recording rejected without marker'}
  if(Test-AwakenedFleet $partial){throw 'partial recording accepted'}
  foreach($role in 'master','cso','worker'){
    foreach($v in @($false,$null,'true')){
      $copy=$ready | ConvertTo-Json -Depth 30 | ConvertFrom-Json
      ($copy.surfaces | Where-Object {$_.role -eq $role}).launch_complete=$v
      if(Test-AwakenedFleet $copy){throw "non-true signal accepted: $role / $v"}
    }
    $copy=$ready | ConvertTo-Json -Depth 30 | ConvertFrom-Json
    ($copy.surfaces | Where-Object {$_.role -eq $role}).PSObject.Properties.Remove('launch_complete')
    if(Test-AwakenedFleet $copy){throw "missing signal accepted: $role"}
    $copy=$ready | ConvertTo-Json -Depth 30 | ConvertFrom-Json
    ($copy.surfaces | Where-Object {$_.role -eq $role}).agent_alive=$false
    if(Test-AwakenedFleet $copy){throw "dead role accepted: $role"}
  }
  Write-Host 'PASS recorded three roles / partial / missing / nonboolean / dead, StrictMode'
}
