param([string]$Mode)
$ErrorActionPreference='Stop'; Set-StrictMode -Version Latest
$t=$null; $e=$null
$a=[System.Management.Automation.Language.Parser]::ParseFile((Join-Path $PWD 'bootstrap.ps1'),[ref]$t,[ref]$e)
$a.FindAll({param($n) $n -is [System.Management.Automation.Language.FunctionDefinitionAst]},$false) | ForEach-Object {Invoke-Expression $_.Extent.Text}
$WaveHome=Join-Path $env:RC5_HOME 'wave'
$ready=(Get-Content (Join-Path $PWD 'tests/fixtures/real_cys/rc5_three_status.json') -Raw | ConvertFrom-Json).response
$masterRef=($ready.surfaces | Where-Object {$_.role -eq 'master'}).surface_ref
$since=[Math]::Floor(($ready.surfaces | Measure-Object created_at -Minimum).Minimum)
if(-not (Test-AwakenedFleet $ready $masterRef $since)){throw 'positive recorded control rejected'}
if($Mode -eq 'old'){
 foreach($role in 'cso','worker'){
  foreach($created in @(1,'9999999999',$true)){
   $copy=$ready | ConvertTo-Json -Depth 30 | ConvertFrom-Json
   ($copy.surfaces | Where-Object {$_.role -eq $role}).created_at=$created
   if(Test-AwakenedFleet $copy $masterRef $since){throw "old or invalid created_at accepted: $role/$created"}
  }
 }
} elseif($Mode -eq 'master'){
 $copy=$ready | ConvertTo-Json -Depth 30 | ConvertFrom-Json
 $other=($copy.surfaces | Where-Object {$_.role -eq 'master'}) | ConvertTo-Json -Depth 20 | ConvertFrom-Json
 $other.surface_ref='surface:999999'
 ($copy.surfaces | Where-Object {$_.role -eq 'master'}).launch_complete=$false
 $copy.surfaces += $other
 if(Test-AwakenedFleet $copy $masterRef $since){throw 'another master signal accepted'}
} elseif($Mode -eq 'fields'){
 foreach($field in 'exited','agent_alive'){
  foreach($value in @('missing',$null,0,1,'false','true')){
   $copy=$ready | ConvertTo-Json -Depth 30 | ConvertFrom-Json
   $seat=$copy.surfaces | Where-Object {$_.role -eq 'cso'}
   if($value -eq 'missing'){$seat.PSObject.Properties.Remove($field)}else{$seat.$field=$value}
   if(Test-AwakenedFleet $copy $masterRef $since){throw "invalid live field accepted: $field/$value"}
   if(@(Get-LiveRoleSeats $copy).Count -ne 2){throw 'invalid live field counted'}
   if((Get-LaunchCompleteObserved $copy) -ne 2){throw 'invalid live signal counted'}
  }
 }
 foreach($name in 'csoXYZ','cso-extra','workers','worker-'){
  $copy=$ready | ConvertTo-Json -Depth 30 | ConvertFrom-Json
  ($copy.surfaces | Where-Object {$_.role -eq 'cso'}).role=$name
  if(@(Get-LiveRoleSeats $copy).Count -eq 3){throw "invalid role counted: $name"}
 }
}
Write-Host "PASS binding $Mode"
