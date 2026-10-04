$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$t=$null; $e=$null
$a=[System.Management.Automation.Language.Parser]::ParseFile((Join-Path $PWD 'bootstrap.ps1'),[ref]$t,[ref]$e)
$a.FindAll({param($n) $n -is [System.Management.Automation.Language.FunctionDefinitionAst]},$false) | ForEach-Object { Invoke-Expression $_.Extent.Text }
$WaveHome=Join-Path $env:RC5_HOME 'wave'; $bin=Join-Path $WaveHome 'bin'
New-Item -ItemType Directory -Force $bin | Out-Null
foreach($n in 'cys.exe','cysd.exe','cys-app.exe'){ [IO.File]::WriteAllText((Join-Path $bin $n),$n) }
$Reinstall=$false; $Config=[pscustomobject]@{release=[pscustomobject]@{version='test'}}
$WaveWinSha256='a'*64
function Release-Context {}
$obs=[pscustomobject]@{verified_installer_sha256=$WaveWinSha256; cli_sha256=(Get-ArtifactHash (Join-Path $bin 'cys.exe')); daemon_sha256=(Get-ArtifactHash (Join-Path $bin 'cysd.exe')); app_sha256=(Get-ArtifactHash (Join-Path $bin 'cys-app.exe'))}
$State=[pscustomobject]@{steps=[pscustomobject]@{S04_INSTALL_LINK=[pscustomobject]@{status='passed';exit_code=0;error_id=$null;version='test';observed=$obs}}}
if(-not (Test-StepComplete 'S04_INSTALL_LINK')){throw 'intact fingerprint must skip'}
$StateFile=Join-Path $WaveHome 'install-state.json'
Save-ResumeObservation 'S04_INSTALL_LINK'
$saved=Get-Content $StateFile -Raw | ConvertFrom-Json
if(-not $saved.steps.S04_INSTALL_LINK.observed.skipped_by_resume -or $saved.steps.S04_INSTALL_LINK.observed.resume_fingerprint.app_sha256 -ne $obs.app_sha256 -or $saved.steps.S04_INSTALL_LINK.status -ne 'passed'){throw 'resume observation not persisted or original state lost'}

[IO.File]::WriteAllText((Join-Path $bin 'cys-app.exe'),'tampered')
if(Test-StepComplete 'S04_INSTALL_LINK'){throw 'changed app was skipped'}
Write-Host 'PASS app/CLI/daemon fingerprint'
