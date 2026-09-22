param(
  [Parameter(Position=0)][string]$Command,
  [Parameter(Position=1)][string]$Action,
  [Parameter(Position=2)][string]$Format,
  [Parameter(Position=3)][string]$RolesArgument,
  [Parameter(Position=4)][string]$RolesPath
)

$ErrorActionPreference = "Stop"
$WaveHome = if ($env:WAVE_HOME) { $env:WAVE_HOME } else { Join-Path $env:USERPROFILE ".wave" }
$PackHome = Join-Path $env:USERPROFILE ".cys\pack"
$RolesFile = Join-Path $PackHome "roles.json"

if ($Command -eq "fleet" -and $Action -eq "bootstrap") {
  $fleet = Join-Path $WaveHome "fleet"
  New-Item -ItemType Directory -Force -Path $fleet | Out-Null
  "initial_fleet=master+worker-dept-1" | Set-Content -LiteralPath (Join-Path $fleet "bootstrap-result")
  New-Item -ItemType File -Force -Path (Join-Path $fleet "initial-fleet.ok") | Out-Null
  exit 0
}

if ($Command -eq "fleet" -and $Action -eq "status") {
  $roles = (Get-Content -Raw -LiteralPath $RolesFile | ConvertFrom-Json).roles
  [ordered]@{ seats = @($roles | ForEach-Object { [ordered]@{ role = $_.role; kind = $_.kind; injected_bytes = 0 } }); injected_bytes = 0 } | ConvertTo-Json -Compress
  exit 0
}

if ($Command -eq "doctor" -and $Action -eq "--json") {
  $roles = (Get-Content -Raw -LiteralPath $RolesFile | ConvertFrom-Json).roles
  $identifyExit = 1
  $cys = Join-Path $WaveHome "bin\cys.exe"
  if (Test-Path -LiteralPath $cys) { & $cys identify *> $null; $identifyExit = $LASTEXITCODE }
  [ordered]@{ identify_exit = $identifyExit; seats = @($roles | ForEach-Object { [ordered]@{ role = $_.role; injected_bytes = 0 } }) } | ConvertTo-Json -Compress
  exit 0
}

Write-Error "사용법: wave.ps1 fleet bootstrap|status 또는 wave.ps1 doctor --json"
exit 2
