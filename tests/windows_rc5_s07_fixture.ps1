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
$script:LogLines=@()
function Write-Log([string]$Message){$script:LogLines += $Message}
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
  if($script:LogLines -notcontains '이 폴더는 이 컴퓨터에만 저장됩니다.'){throw 'local evidence notice missing'}
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
$script:RunStartedUnix=[long][Math]::Floor(($ready.surfaces | Measure-Object created_at -Minimum).Minimum)
New-Item -ItemType Directory -Force (Join-Path $WaveHome 'fleet') | Out-Null
[IO.File]::WriteAllText((Join-Path $WaveHome 'fleet/started-at'),[string]$script:RunStartedUnix)
[IO.File]::WriteAllText((Join-Path $WaveHome 'fleet/master-ref'),[string](($ready.surfaces | Where-Object {$_.role -eq 'master'}).surface_ref))

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

if($Mode -eq 'since'){
  $ready=(Get-Content (Join-Path $PWD 'tests/fixtures/real_cys/rc5_three_status.json') -Raw | ConvertFrom-Json).response
  foreach($seat in $ready.surfaces){$seat.created_at=1}
  $ref=($ready.surfaces | Where-Object {$_.role -eq 'master'}).surface_ref
  New-Item -ItemType Directory -Force (Join-Path $WaveHome 'fleet') | Out-Null
  [IO.File]::WriteAllText((Join-Path $WaveHome 'fleet/master-ref'),$ref)
  function Start-WaveApp {}
  function Wait-GuiOnboarded($Clock) {}
  function Seed-WaveClaudeTrust {}
  function Get-LiveFleet([int]$TimeoutMs=5000){return $ready}
  $script:RunStartedUnix=10000000000L
  foreach($invalid in @('', ' ', '0')){
    [IO.File]::WriteAllText((Join-Path $WaveHome 'fleet/started-at'),$invalid)
    if(Test-AwakenedFleet $ready){throw "invalid started-at accepted by S08: [$invalid]"}
    $rejected=$false
    try { Run-S07 } catch { $rejected=$true }
    if(-not $rejected){throw "invalid started-at accepted by resume: [$invalid]"}
  }
  Write-Host 'PASS invalid started-at rejected by S08 and resume'
}

if($Mode -eq 'start-time-floor'){
  if($null -ne (ConvertTo-ValidStartTime '0000000000')){throw 'zero accepted as a recorded start time'}
  if($null -ne (ConvertTo-ValidStartTime '0999999999')){throw 'below-floor ten-digit value accepted as a recorded start time'}
  if((ConvertTo-ValidStartTime 1000000000) -ne 1000000000){throw 'minimum ten-digit epoch value rejected'}
  Write-Host 'PASS start-time lower bound'
}

if($Mode -eq 'recorded-decimal'){
  $recordedRaw=[IO.File]::ReadAllText((Join-Path $PWD 'tests/fixtures/real_cys/rc5_signal1_fleet_status.stdout.log'))
  $recorded=$recordedRaw | ConvertFrom-Json
  foreach($seat in $recorded.surfaces){if($null -ne $seat.created_at){$seat.created_at=[decimal]$seat.created_at}}
  $since=[long]1791102186
  if(-not (Test-AwakenedFleet $recorded 'surface:1' $since)){throw 'recorded launch_complete fleet with decimal timestamps rejected'}
  if((ConvertTo-ValidStartTime ([decimal]1791102186)) -ne 1791102186){throw 'decimal integer start time rejected'}
  if($null -ne (ConvertTo-ValidStartTime ([decimal]1791102186.5))){throw 'fractional decimal start time accepted'}
  if(-not (Test-ByteCount ([decimal]2147483648)) -or -not (Test-ByteCount ([decimal][long]::MaxValue))){throw 'in-range decimal JSON integer rejected as byte count'}
  if((Test-ByteCount ([decimal]9223372036854775808)) -or (Test-ByteCount ([decimal]1.5)) -or (Test-ByteCount $true) -or (Test-ByteCount '1')){throw 'invalid decimal/bool/string byte count accepted'}
  $stringCopy=$recorded | ConvertTo-Json -Depth 30 | ConvertFrom-Json
  ($stringCopy.surfaces | Where-Object {$_.role -eq 'cso'}).created_at='1791102238.3658855'
  if(Test-AwakenedFleet $stringCopy 'surface:1' $since){throw 'string created_at accepted'}
  $boolCopy=$recorded | ConvertTo-Json -Depth 30 | ConvertFrom-Json
  ($boolCopy.surfaces | Where-Object {$_.role -eq 'cso'}).created_at=$true
  if(Test-AwakenedFleet $boolCopy 'surface:1' $since){throw 'boolean created_at accepted'}
  Write-Host 'PASS recorded decimal fleet / string and boolean rejected'
}
