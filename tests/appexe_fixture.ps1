param([string]$Source = (Join-Path $PSScriptRoot "../bootstrap.ps1"),[string]$OutputRoot = (Join-Path ([IO.Path]::GetTempPath()) ("appexe-" + [guid]::NewGuid().ToString("N"))),[switch]$ExpectLegacy)
Set-StrictMode -Version Latest
$ErrorActionPreference='Stop'
function Assert($value,$message) { if (-not $value) { throw $message } }
function Release-Context { }
function Test-SyntheticBypass($entry) { return $false }
function Get-StateField($o,$name) { return $o.$name }
function Get-ArtifactHash($p) { return (Get-FileHash -LiteralPath $p -Algorithm SHA256).Hash.ToLowerInvariant() }
function Start-WaveDetached($p) { $script:Launched=$p }
$tokens=$null;$errors=$null
$ast=[Management.Automation.Language.Parser]::ParseFile($Source,[ref]$tokens,[ref]$errors)
Assert ($errors.Count -eq 0) 'parse failed'
foreach ($name in @('Test-StepComplete','Start-WaveApp')) {
  $fn=$ast.Find({param($n) $n -is [Management.Automation.Language.FunctionDefinitionAst] -and $n.Name -eq $name},$false)
  Assert ($null -ne $fn) "missing $name"
  . ([scriptblock]::Create($fn.Extent.Text))
}
$Reinstall=$false;$Config=[pscustomobject]@{release=[pscustomobject]@{version='0.3.6'}};$WaveWinSha256='fixture-installer-hash'
foreach ($kind in @('canonical-only','legacy-only','both','neither','bad-cli-hash')) {
  $WaveHome=Join-Path $OutputRoot $kind
  $null=New-Item -ItemType Directory -Path (Join-Path $WaveHome 'bin') -Force
  foreach ($name in @('cys.exe','cysd.exe')) { [IO.File]::WriteAllText((Join-Path $WaveHome ('bin/'+$name)),$name) }
  if ($kind -in @('canonical-only','both','bad-cli-hash')) { [IO.File]::WriteAllText((Join-Path $WaveHome 'bin/wave-app.exe'),'fixture canonical GUI') }
  if ($kind -in @('legacy-only','both')) { [IO.File]::WriteAllText((Join-Path $WaveHome 'bin/cys-app.exe'),'fixture legacy GUI') }
  $entry=[pscustomobject]@{status='passed';exit_code=0;error_id=$null;version='0.3.6';observed=[pscustomobject]@{verified_installer_sha256=$WaveWinSha256;cli_sha256=(Get-ArtifactHash (Join-Path $WaveHome 'bin/cys.exe'));daemon_sha256=(Get-ArtifactHash (Join-Path $WaveHome 'bin/cysd.exe'))}}
  $State=[pscustomobject]@{steps=[pscustomobject]@{S04_INSTALL_LINK=$entry}}
  if ($kind -eq 'bad-cli-hash') { $entry.observed.cli_sha256='bad' }
  $skip=Test-StepComplete S04_INSTALL_LINK
  $expected=if ($ExpectLegacy) { $kind -ne 'bad-cli-hash' } else { $kind -in @('canonical-only','both') }
  Assert ($skip -eq $expected) "wrong skip: $kind got=$skip"
  $script:Launched=$null;$thrown=$false
  try { Start-WaveApp } catch { $thrown=$true }
  $canLaunch=if ($ExpectLegacy) { $kind -in @('legacy-only','both') } else { $kind -in @('canonical-only','both','bad-cli-hash') }
  Assert ($thrown -eq (-not $canLaunch)) "wrong launch result: $kind"
  if ($canLaunch) { Assert ((Split-Path -Leaf $script:Launched) -eq $(if($ExpectLegacy){'cys-app.exe'}else{'wave-app.exe'})) 'wrong target' }
  $Reinstall=$true;Assert (-not (Test-StepComplete S04_INSTALL_LINK)) 'Reinstall skipped';$Reinstall=$false
  Write-Host "PASS case=$kind skip=$skip launch=$canLaunch legacy=$ExpectLegacy"
}
Write-Host "PASS PowerShell=$($PSVersionTable.PSVersion) Source=$Source"
