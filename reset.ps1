[CmdletBinding()]
param(
  [switch]$List,
  [switch]$Apply,
  [ValidateSet("wave", "pack", "all")]
  [string]$Target = "wave"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$targets = switch ($Target) {
  "wave" { @((Join-Path $env:USERPROFILE ".wave")); break }
  "pack" { @((Join-Path $env:USERPROFILE ".cys\pack")); break }
  "all" { @((Join-Path $env:USERPROFILE ".wave"), (Join-Path $env:USERPROFILE ".cys\pack")); break }
}

if (-not $Apply) {
  Write-Host "reset 대상(삭제하지 않음):"
  $targets | ForEach-Object { Write-Host " - $_" }
  exit 0
}

# Undo reads the same .wave that reset removes, regardless of inherited WAVE_HOME.
if ($Target -eq 'wave' -or $Target -eq 'all') {
  $previousWaveHome = $env:WAVE_HOME
  try {
    $env:WAVE_HOME = Join-Path $env:USERPROFILE '.wave'
    & (Join-Path $PSScriptRoot 'bootstrap.ps1') -UndoTrust
    if ($LASTEXITCODE -ne 0) { throw "seed rollback failed (exit $LASTEXITCODE); reset stopped" }
  } finally { $env:WAVE_HOME = $previousWaveHome }
}

Write-Host "reset 적용 대상:"
foreach ($targetPath in $targets) {
  Write-Host " - $targetPath"
  if (Test-Path -LiteralPath $targetPath) { Remove-Item -LiteralPath $targetPath -Recurse -Force }
}
Write-Host "reset 완료: 지정된 사용자 폴더만 제거됨"
