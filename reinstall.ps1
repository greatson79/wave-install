[CmdletBinding()]
param([switch]$List, [switch]$DryRun)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$WaveHome = if ($env:WAVE_HOME) { $env:WAVE_HOME } else { Join-Path $env:USERPROFILE '.wave' }
$WaveHome = [IO.Path]::GetFullPath($WaveHome)
$profileRoot = [IO.Path]::GetFullPath($env:USERPROFILE).TrimEnd('\') + '\'
if (-not $WaveHome.StartsWith($profileRoot, [StringComparison]::OrdinalIgnoreCase)) { throw '재설치 경로는 사용자 홈 내부여야 합니다.' }
$cursor = $WaveHome
while ($cursor -and $cursor.Length -ge $profileRoot.TrimEnd('\').Length) {
  if (Test-Path -LiteralPath $cursor) {
    if ((Get-Item -LiteralPath $cursor -Force).Attributes -band [IO.FileAttributes]::ReparsePoint) { throw '재설치 경로의 링크는 보존하고 중단합니다.' }
  }
  $cursor = Split-Path -Parent $cursor
}
$statePath = Join-Path $WaveHome 'install-state.json'
$donePath = Join-Path $WaveHome 'install-done.txt'
$targets = @()
Write-Host "백업 이동 후보: $statePath / $donePath (스키마·해시 확인 후)"
Write-Host '보존: 앱·bin·pack·로그·사용자 파일 전체. 소유 manifest 부재로 삭제하지 않습니다.'
Write-Host '정리: 현재 프로세스 WAVE_ENABLE_DAEMON, 정확히 현재 cysd 경로인 옛 HKCU Run 값.'
foreach ($path in @($statePath, $donePath)) {
  if (Test-Path -LiteralPath $path) {
    $item = Get-Item -LiteralPath $path -Force
    if ($item.PSIsContainer -or ($item.Attributes -band [IO.FileAttributes]::ReparsePoint)) { throw "일반 파일이 아니므로 보존: $path" }
  }
}
if (Test-Path -LiteralPath $statePath) {
  $previous = Get-Content -LiteralPath $statePath -Raw -Encoding UTF8 | ConvertFrom-Json
  if ($previous.schema -cne 'wave-install.state.v1' -or $previous.product -cne 'Wave Terminal' -or $null -eq $previous.steps) { throw '상태 스키마 불일치: 보존하고 중단합니다.' }
  $targets += $statePath
}
if (Test-Path -LiteralPath $donePath) {
  $mark = Get-Content -LiteralPath $donePath -Raw -Encoding UTF8 | ConvertFrom-Json
  if (-not (Test-Path -LiteralPath $statePath) -or $mark.state_sha256 -ine (Get-FileHash -LiteralPath $statePath -Algorithm SHA256).Hash -or $mark.sha256 -notmatch '^[a-fA-F0-9]{64}$' -or $mark.config_sha256 -notmatch '^[a-fA-F0-9]{64}$') { throw '완료 표지 소유 증거 불일치: 보존하고 중단합니다.' }
  $targets += $donePath
}
$runKey = 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Run'
$valueName = 'WaveTerminal-cysd'
$expected = '"' + (Join-Path $WaveHome 'bin\cysd.exe') + '"'
$oldCommand = $null
if (Test-Path -LiteralPath $runKey) {
  $entry = Get-ItemProperty -LiteralPath $runKey
  $property = $entry.PSObject.Properties[$valueName]
  if ($null -ne $property) { $oldCommand = [string]$property.Value }
}
if ($List -or $DryRun) { return }
$backup = $null
if ($targets.Count -gt 0 -or $oldCommand -ceq $expected) {
  $backup = Join-Path $WaveHome ('reinstall-backup-' + [DateTime]::UtcNow.ToString('yyyyMMddTHHmmssfffffffZ'))
  New-Item -ItemType Directory -Path $backup -ErrorAction Stop | Out-Null
  foreach ($path in $targets) { Move-Item -LiteralPath $path -Destination $backup -ErrorAction Stop }
}
if ($oldCommand -ceq $expected) {
  @{ path = $runKey; name = $valueName; value = $oldCommand } | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $backup 'legacy-run.json') -Encoding UTF8
  # 다른 설치/사용자 명령은 절대 지우지 않는다.
  Remove-ItemProperty -LiteralPath $runKey -Name $valueName -ErrorAction Stop
}
Remove-Item Env:WAVE_ENABLE_DAEMON -ErrorAction SilentlyContinue
# 사용자/시스템 영구 환경변수의 출처는 증명되지 않아 변경하지 않는다.
& (Join-Path $ScriptDir 'bootstrap.ps1') -Reinstall
