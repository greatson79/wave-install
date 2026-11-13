param([Parameter(Mandatory = $true)][string]$Setup)
# Fresh Windows runner only. Both install destinations are injected under RUNNER_TEMP.
$ErrorActionPreference = 'Stop'
if ($PSVersionTable.PSVersion.ToString() -notlike '5.1.*') { throw 'Requires PS 5.1' }
if (-not $env:GITHUB_ACTIONS -or -not $env:RUNNER_TEMP) { throw 'Fresh CI runner required' }
$repo = Split-Path $PSScriptRoot -Parent
$root = Join-Path $env:RUNNER_TEMP ('manual-rerun-' + [guid]::NewGuid().ToString('N'))
$oldProfile = $env:USERPROFILE
$oldWaveHome = $env:WAVE_HOME
$oldProgress = $env:WAVE_NO_PROGRESS
try {
  $env:USERPROFILE = Join-Path $root 'profile'
  $env:WAVE_HOME = Join-Path $env:USERPROFILE '.wave'
  $env:WAVE_NO_PROGRESS = '1'
  New-Item -ItemType Directory -Force $env:USERPROFILE, $env:WAVE_HOME | Out-Null
  $source = [IO.File]::ReadAllText((Join-Path $repo 'bootstrap.ps1'))
  $boundary = $source.IndexOf("`nLoad-Config`nif (`$DryRun)")
  if ($boundary -lt 0) { throw 'Bootstrap function-only boundary missing' }
  . ([scriptblock]::Create($source.Substring(0, $boundary)))
  $script:ScriptDir = $repo
  $script:StepsFile = Join-Path $repo 'steps.json'
  Load-Config
  Release-Context
  if ((Get-FileHash -LiteralPath $Setup -Algorithm SHA256).Hash.ToLowerInvariant() -ne $ReleaseExpectedSha256) { throw 'Pinned setup hash mismatch' }
  if ((Get-Item -LiteralPath $Setup).Length -ne $WaveWinBytes) { throw 'Pinned setup size mismatch' }
  $manual = Join-Path $root 'manual setup location'
  New-Item -ItemType Directory -Force $manual | Out-Null
  if ((Invoke-NsisSetup $Setup $manual) -ne 0) { throw 'Initial alternate-location install failed' }
  $guiNames = @('wave-app.exe', 'cys-app.exe')
  $initial = @(Get-ChildItem -LiteralPath $manual -File | Where-Object { $guiNames -contains $_.Name })
  if (-not $initial.Count) { throw 'Initial GUI file not found; rerun proof is unmeasured' }
  $download = Split-Path $ArtifactPath -Parent
  New-Item -ItemType Directory -Force $download | Out-Null
  Copy-Item -LiteralPath $Setup -Destination $ArtifactPath
  Run-S04
  $target = Join-Path $WaveHome 'bin'
  $duplicates = @($initial | Where-Object {
    $newPath = Join-Path $target $_.Name
    (Test-Path -LiteralPath $_.FullName -PathType Leaf) -and (Test-Path -LiteralPath $newPath -PathType Leaf)
  } | ForEach-Object { $_.Name })
  $result = [ordered]@{
    setup_sha256 = $ReleaseExpectedSha256
    first_install = $manual
    rerun_target = $target
    initial_gui_names = @($initial.Name)
    remaining_manual_gui_names = @($initial | Where-Object { Test-Path -LiteralPath $_.FullName } | ForEach-Object { $_.Name })
    duplicate_gui_names = $duplicates
    gui_started = $false
    daemon_started = $false
    scope = 'Two injected locations; not the real NSIS default folder or a running app'
  }
  $result | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $root 'result.json') -Encoding UTF8
  Write-Host ('MANUAL_RERUN_RESULT=' + ($result | ConvertTo-Json -Depth 5 -Compress))
  if ($duplicates.Count) { throw 'RERUN_DUPLICATE_COPY: stop for design decision; do not recommend rerun' }
} finally {
  $env:USERPROFILE = $oldProfile
  $env:WAVE_HOME = $oldWaveHome
  $env:WAVE_NO_PROGRESS = $oldProgress
}
exit 0
