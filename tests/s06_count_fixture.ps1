param([string]$Source = (Join-Path $PSScriptRoot "../bootstrap.ps1"), [string]$OutputRoot = (Join-Path ([IO.Path]::GetTempPath()) ("s06-" + [guid]::NewGuid().ToString("N"))))
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
function Assert($Condition, [string]$Message) { if (-not $Condition) { throw $Message } }
function Get-ArtifactHash([string]$Path) { (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant() }
function Say([string]$Message) { Write-Host $Message }
function Write-Log([string]$Message) { Write-Host $Message }
function Invoke-BoundedCheck($Exe, $Arguments, $Name, $Timeout) {
  if ($Name -eq 'init-pack') {
    foreach ($key in $script:FixtureManifest.Keys) {
      $dest = Join-Path $PackHome $key
      if ((Get-ArtifactHash $dest) -ne $script:FixtureManifest[$key]) { [IO.File]::WriteAllText(($dest + '.new'), 'new app directive') }
    }
    return [pscustomobject]@{ timed_out=$false; exit_code=0; stdout=''; stderr='' }
  }
  Assert ($Name -eq 'pack-manifest') 'unexpected external command'
  return [pscustomobject]@{ timed_out=$false; exit_code=0; stdout=(@{files=$script:FixtureManifest}|ConvertTo-Json); stderr='' }
}
$tokens=$null; $parseErrors=$null
$ast=[Management.Automation.Language.Parser]::ParseFile($Source,[ref]$tokens,[ref]$parseErrors)
Assert ($parseErrors.Count -eq 0) 'parse errors'
$fn=$ast.Find({param($n) $n -is [Management.Automation.Language.FunctionDefinitionAst] -and $n.Name -eq 'Run-S06'},$false)
Assert ($null -ne $fn) 'Run-S06 missing'
. ([scriptblock]::Create($fn.Extent.Text))
Write-Host "PowerShell=$($PSVersionTable.PSVersion) Source=$Source"
foreach ($count in 0,1,2) {
  $case = Join-Path $OutputRoot ('case-'+$count)
  $WaveHome=Join-Path $case 'wave'; $PackHome=Join-Path $case 'pack'; $ScriptDir=Join-Path $case 'source'
  $null=New-Item -ItemType Directory -Path (Join-Path $ScriptDir 'wave-pack/directives'),(Join-Path $PackHome 'directives'),(Join-Path $WaveHome 'bin') -Force
  $script:FixtureManifest=@{}; $before=@{}
  foreach ($i in 1,2) {
    $name="directives/file$i.md"; $dest=Join-Path $PackHome $name
    [IO.File]::WriteAllText($dest,'new app directive')
    $script:FixtureManifest[$name]=Get-ArtifactHash $dest
    if ($i -le $count) { [IO.File]::WriteAllText($dest,"custom bytes $i`r`n"); $before[$name]=Get-ArtifactHash $dest }
  }
  $StepObserved=[ordered]@{}; $failed=$false; $failure=$null
  try { Run-S06 } catch { $failure=$_; $failed=$true; Write-Host "THROW count=$count line=$($_.InvocationInfo.ScriptLineNumber) expression=$($_.InvocationInfo.Line.Trim()) error=$($_.Exception.Message)" }
  foreach ($name in $before.Keys) { $after=Get-ArtifactHash (Join-Path $PackHome $name); Assert ($before[$name] -eq $after) 'custom file changed'; Write-Host "PRESERVED $name before=$($before[$name]) after=$after" }
  $pending=@(Get-ChildItem -LiteralPath $PackHome -Filter '*.new' -Recurse -File)
  Assert ($pending.Count -eq $count) 'sidecar count mismatch'
  Assert (-not $failed) 'S06 must succeed for every valid custom-file count'
  if (-not $failed) { Run-S06; Write-Host "RERUN PASS count=$count" }
  Write-Host "CASE PASS custom=$count expected_throw=$failed sidecars=$($pending.Count)"
}

Set-StrictMode -Version Latest
$ErrorActionPreference='Stop'
function Assert($Condition,[string]$Message) { if (-not $Condition) { throw $Message } }
function Save-State { }
function Now-Utc { 'fixture' }
$t=$null;$errors=$null
$ast=[Management.Automation.Language.Parser]::ParseFile($Source,[ref]$t,[ref]$errors)
Assert ($errors.Count -eq 0) 'parse error'
$want=@('Get-StateField','Test-ByteCount','Test-SyntheticBypass','Summarize-State')
foreach ($fn in $ast.FindAll({param($n) $n -is [Management.Automation.Language.FunctionDefinitionAst]},$false)) {
 if ($fn.Name -in $want) { . ([scriptblock]::Create($fn.Extent.Text)) }
}
Write-Host "PS=$($PSVersionTable.PSVersion) Source=$Source"
foreach ($kind in 'dictionary','pscustomobject') {
 foreach ($count in 0,1,2) {
  $custom=@();for ($i=0;$i -lt $count;$i++) {$custom+="directives/custom$i.md"}
  $observed=@{original_match=($count -eq 0);custom_preserved=$custom;new_file_count=$count}
  if ($kind -eq 'pscustomobject') {$observed=[pscustomobject]$observed}
  $Config=[pscustomobject]@{steps=@([pscustomobject]@{id='S08_VERIFY';index=8})}
  $State=[pscustomobject]@{steps=[pscustomobject]@{S08_VERIFY=[pscustomobject]@{status='passed';exit_code=0;error_id='';observed=$observed}};required_steps_passed=$false;updated_at='';status='running';current_step='S08_VERIFY'}
  $read=Get-StateField $observed 'custom_preserved'
  if ($count -eq 0) { Assert ($null -eq $read) 'empty field semantics changed' }
  if ($count -eq 1) { Assert ($read -is [string]) 'single field semantics changed' }
  if ($count -eq 2) { Assert ($read -is [array] -and $read.Count -eq 2) 'two field semantics changed' }
  Summarize-State $true
  Assert ($State.required_steps_passed -eq $true) 'summary mismatch'
  Write-Host "SUMMARY PASS kind=$kind custom=$count required=$($State.required_steps_passed) status=$($State.status)"
 }
 foreach ($bad in @($null,'bad scalar')) {
  $observed=@{original_match=$false;custom_preserved=$bad;new_file_count=1}
  if ($kind -eq 'pscustomobject') {$observed=[pscustomobject]$observed}
  $State.steps.S08_VERIFY.observed=$observed
  Summarize-State $true
  Assert (-not $State.required_steps_passed) 'invalid null/scalar accepted'
 }
 foreach ($badObserved in @(@{original_match=$false;custom_preserved=@();new_file_count=0}, @{original_match=$false;new_file_count=0})) {
  if ($kind -eq 'pscustomobject') {$badObserved=[pscustomobject]$badObserved}
  $State.steps.S08_VERIFY.observed=$badObserved
  Summarize-State $true
  Assert (-not $State.required_steps_passed) 'empty/missing custom list accepted'
 }
 foreach ($value in @('abc',0,$false,[pscustomobject]@{a=1})) {
  $obj=@{v=$value};if ($kind -eq 'pscustomobject') {$obj=[pscustomobject]$obj}
  $read=Get-StateField $obj 'v'
  Assert ($read.GetType() -eq $value.GetType()) 'scalar/object type changed'
 }
 Assert ($null -eq (Get-StateField $null 'missing')) 'null object changed'
 Assert ($null -eq (Get-StateField ([pscustomobject]@{}) 'missing')) 'missing field changed'
 Write-Host "BOUNDARY PASS kind=$kind null/scalar rejected; scalar types/missing preserved"
}
