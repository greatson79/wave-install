$ErrorActionPreference='Stop'
$t=$null;$errors=$null
$ast=[System.Management.Automation.Language.Parser]::ParseFile((Join-Path $PWD 'bootstrap.ps1'),[ref]$t,[ref]$errors)
if($errors.Count){throw ($errors|Out-String)}
$ast.FindAll({param($n) $n -is [System.Management.Automation.Language.FunctionDefinitionAst]},$false) | ForEach-Object {Invoke-Expression $_.Extent.Text}
$env:USERPROFILE=$env:W12_FIXTURE_HOME
$WaveHome=Join-Path $env:USERPROFILE '.wave';$PackHome=Join-Path $env:USERPROFILE '.cys/pack'
New-Item -ItemType Directory -Force (Join-Path $PackHome 'directives'),(Join-Path $WaveHome 'verify')|Out-Null
$receipt=Join-Path $WaveHome 'verify/G3_inject.json'
if($null -ne (Test-OriginalInjection)){throw 'absent receipt accepted'}
$script:files=[ordered]@{};$rows=[ordered]@{}
foreach($role in @('master','cso','worker')) {
  $rel='directives/'+$role.ToUpperInvariant()+'_DIRECTIVE.md'
  $path=Join-Path $PackHome $rel
  [IO.File]::WriteAllText($path,('original '+$role+';')*3000)
  $snapshot=Join-Path $WaveHome ('verify/hook_'+$role+'.out')
  [IO.File]::WriteAllBytes($snapshot,([byte[]](65,10)+[IO.File]::ReadAllBytes($path)+[byte[]](10,90)))
  $hash=Get-ArtifactHash $path;$bytes=(Get-Item $path).Length
  $files[$rel]=$hash
  $rows[$role]=[ordered]@{injected_sha256=$hash;pack_sha256=$hash;injected_bytes=$bytes;pack_bytes=$bytes}
}
function Invoke-BoundedCheck($FilePath,$Arguments,$Name,$TimeoutMs) {
  if(($Arguments -join ' ') -ne 'pack-manifest'){throw 'unexpected CLI'}
  return [pscustomobject]@{timed_out=$false;exit_code=0;stdout=(@{files=$files}|ConvertTo-Json -Depth 8);stderr=''}
}
function Write-Receipt { @{roles=$rows}|ConvertTo-Json -Depth 8|Set-Content -LiteralPath $receipt -Encoding UTF8 }
Write-Receipt
$verified=Test-OriginalInjection
if($verified.original_match -cne $true -or $verified.new_file_count -ne 0 -or $verified.roles.Count -ne 3){throw 'valid original rejected'}
function Assert-Rejected {
  $rejected=$false
  try {$null=Test-OriginalInjection} catch {$rejected=$true}
  if(-not $rejected){throw 'invalid receipt accepted'}
}
$masterSnapshot=Join-Path $WaveHome 'verify/hook_master.out'
$savedSnapshot=[IO.File]::ReadAllBytes($masterSnapshot)
Move-Item -LiteralPath $masterSnapshot -Destination ($masterSnapshot+'.held')
Assert-Rejected
Move-Item -LiteralPath ($masterSnapshot+'.held') -Destination $masterSnapshot
[IO.File]::WriteAllBytes($masterSnapshot,[Text.Encoding]::UTF8.GetBytes('unrelated stdout'))
Assert-Rejected
[IO.File]::WriteAllBytes($masterSnapshot,$savedSnapshot)
$rows.master.injected_bytes='45000';Write-Receipt;Assert-Rejected
$rows.master.injected_bytes=$rows.master.pack_bytes
$rows.master.injected_sha256='0'*64;Write-Receipt;Assert-Rejected
$rows.master.injected_sha256=$rows.master.pack_sha256
$prior=$rows.cso;$rows.Remove('cso');Write-Receipt;Assert-Rejected;$rows.cso=$prior
Write-Receipt
$priorHash=$files['directives/MASTER_DIRECTIVE.md'];$files['directives/MASTER_DIRECTIVE.md']='f'*64
Assert-Rejected;$files['directives/MASTER_DIRECTIVE.md']=$priorHash
$masterPath=Join-Path $PackHome 'directives/MASTER_DIRECTIVE.md'
$priorText=[IO.File]::ReadAllText($masterPath);[IO.File]::WriteAllText($masterPath,'edited')
Assert-Rejected;[IO.File]::WriteAllText($masterPath,$priorText)
[IO.File]::WriteAllText((Join-Path $PackHome 'directives/MASTER_DIRECTIVE.md.new'),'pending')
Assert-Rejected
# Completion contract: genuine booleans + integer zero only; old caps cannot substitute.
$Config=[pscustomobject]@{steps=@([pscustomobject]@{id='S08_VERIFY';index=8})}
$State=[pscustomobject]@{steps=[pscustomobject]@{S08_VERIFY=[pscustomobject]@{status='passed';exit_code=0;error_id='';observed=[pscustomobject]@{original_match=$true;new_file_count=0}}};required_steps_passed=$false;updated_at=''}
function Save-State { }
function Now-Utc { 'fixture' }
Summarize-State $false
if(-not $State.required_steps_passed){throw 'valid summary rejected'}
foreach($bad in @('true',$null,$false,1)) {
  $State.steps.S08_VERIFY.observed.original_match=$bad
  Summarize-State $false
  if($State.required_steps_passed){throw 'weak original_match accepted'}
}
$State.steps.S08_VERIFY.observed.original_match=$true
foreach($bad in @('0',$null,$false,1)) {
  $State.steps.S08_VERIFY.observed.new_file_count=$bad
  Summarize-State $false
  if($State.required_steps_passed){throw 'weak new_file_count accepted'}
}
Write-Host 'PASS G3 roles/hash/positive bytes/app anchor/new-files/strict completion; original >20KB accepted'
