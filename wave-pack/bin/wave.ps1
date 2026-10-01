param(
  [Parameter(Position=0)][string]$Command,
  [Parameter(Position=1)][string]$Action,
  [Parameter(Position=2)][string]$Format,
  [Parameter(Position=3)][string]$RolesArgument,
  [Parameter(Position=4)][Alias("-roles-file", "roles-file")][string]$RolesPath,
  [Alias("-json")][switch]$Json
)

$ErrorActionPreference = "Stop"
$WaveHome = if ($env:WAVE_HOME) { $env:WAVE_HOME } else { Join-Path $env:USERPROFILE ".wave" }
$PackHome = Join-Path $env:USERPROFILE ".cys\pack"
$RolesFile = if ($RolesPath) { $RolesPath } else { Join-Path $PackHome "roles.json" }

function Read-SharedCheckLog([string]$Path) {
  $stream = $null
  $reader = $null
  try {
    # A daemon descendant may still own the redirected writer after its client exits.
    $stream = [IO.File]::Open($Path, [IO.FileMode]::Open, [IO.FileAccess]::Read, [IO.FileShare]::ReadWrite)
    $reader = [IO.StreamReader]::new($stream)
    return $reader.ReadToEnd()
  } catch {
    throw "Diagnostic log read failed ($Path): $($_.Exception.Message)"
  } finally {
    if ($null -ne $reader) { $reader.Dispose() }
    elseif ($null -ne $stream) { $stream.Dispose() }
  }
}

if ($Command -eq "fleet" -and $Action -eq "bootstrap") {
  $fleet = Join-Path $WaveHome "fleet"
  New-Item -ItemType Directory -Force -Path $fleet | Out-Null
  "initial_fleet=master+worker-dept-1" | Set-Content -LiteralPath (Join-Path $fleet "bootstrap-result")
  New-Item -ItemType File -Force -Path (Join-Path $fleet "initial-fleet.ok") | Out-Null
  exit 0
}

if ($Command -eq "fleet" -and $Action -eq "status") {
  $roles = (Get-Content -Raw -LiteralPath $RolesFile | ConvertFrom-Json).roles
  [ordered]@{ seats = @($roles | ForEach-Object { [ordered]@{ role = $_.role; kind = $_.kind; injected_bytes = $null } }); injected_bytes = $null } | ConvertTo-Json -Compress
  exit 0
}

if ($Command -eq "doctor" -and ($Action -eq "--json" -or $Json)) {
  $roles = (Get-Content -Raw -LiteralPath $RolesFile | ConvertFrom-Json).roles
  $identifyExit = 1
  $identifyTimedOut = $false
  $identifyKillError = $null
  $identifyTimeoutMs = 20000
  $cys = Join-Path $WaveHome "bin\cys.exe"
  if (Test-Path -LiteralPath $cys) {
    $verify = Join-Path $WaveHome 'verify'
    New-Item -ItemType Directory -Force $verify | Out-Null
    $stdout = Join-Path $verify 'identify-doctor.stdout.log'
    $stderr = Join-Path $verify 'identify-doctor.stderr.log'
    $process = Start-Process -FilePath $cys -ArgumentList 'identify' -PassThru -RedirectStandardOutput $stdout -RedirectStandardError $stderr
    try {
      $null = $process.Handle
      if ($process.WaitForExit($identifyTimeoutMs)) {
        $identifyExit = $process.ExitCode
      } else {
        $identifyExit = $null
        $identifyTimedOut = $true
        # Stop only the client launched here; an autostarted daemon keeps its lifecycle.
        try {
          if (-not $process.HasExited) { $process.Kill() }
        } catch {
          if (-not $process.HasExited) { $identifyKillError = $_.Exception.Message }
        }
      }
      # Do not wait indefinitely on handles inherited by a daemon descendant.
      if (-not $process.WaitForExit(1000) -and -not $identifyKillError) { $identifyKillError = 'Client exit was not confirmed within 1000ms' }
    } finally { $process.Dispose() }
    $identifyOutput = @(
      Read-SharedCheckLog $stdout
      Read-SharedCheckLog $stderr
      if ($identifyTimedOut) { "cys identify timed out after $identifyTimeoutMs ms; exit code is unmeasured." }
    ) -join "`n"
    Set-Content -LiteralPath (Join-Path $verify 'identify-doctor.log') -Value $identifyOutput -Encoding UTF8
  }
  [ordered]@{ identify_exit = $identifyExit; identify_timed_out = $identifyTimedOut; timeout_ms = $identifyTimeoutMs; identify_kill_error = $identifyKillError; seats = @($roles | ForEach-Object { [ordered]@{ role = $_.role; injected_bytes = $null } }) } | ConvertTo-Json -Compress
  exit 0
}

Write-Error "사용법: wave.ps1 fleet bootstrap|status 또는 wave.ps1 doctor --json"
exit 2
