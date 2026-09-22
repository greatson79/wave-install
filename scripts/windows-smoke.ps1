[CmdletBinding()]
param(
  [Parameter(Mandatory)][ValidatePattern('^v[0-9]+\.[0-9]+\.[0-9]+$')][string]$TerminalTag,
  [Parameter(Mandatory)][ValidatePattern('^[0-9a-f]{64}$')][string]$ExpectedInstallerSha256
)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
if ($env:OS -ne 'Windows_NT' -or $env:CI -ne 'true') { throw 'GitHub Windows 러너 전용 검증' }
$source = Split-Path -Parent $PSScriptRoot
$run = Join-Path $env:USERPROFILE ('wave-runner-smoke-' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $run | Out-Null
Copy-Item (Join-Path $source 'bootstrap.ps1'), (Join-Path $source 'steps.json'), (Join-Path $source 'install-state.json') -Destination $run
$env:WAVE_HOME = Join-Path $run 'wave'
$version = $TerminalTag.Substring(1)
$asset = "wave-terminal-$version-windows-x64-setup.exe"
$base = "https://github.com/greatson79/wave-terminal/releases/download/$TerminalTag"
$configPath = Join-Path $run 'steps.json'
$config = Get-Content -LiteralPath $configPath -Raw | ConvertFrom-Json
$config.release.version = $version
$config.release.asset_name.windows_x64 = $asset
$config.release.asset_url.windows_x64 = "$base/$asset"
$config.release.sha256.windows_x64 = $ExpectedInstallerSha256
$config.release.minisig_url.windows_x64 = "$base/$asset.minisig"
$config.release.sha256sums_url = "$base/SHA256SUMS"
$config | ConvertTo-Json -Depth 30 | Set-Content -LiteralPath $configPath -Encoding utf8NoBOM
# 네이티브 -File 인자 바인딩 경로를 반드시 행사한다.
& pwsh -NoProfile -NonInteractive -File (Join-Path $run 'bootstrap.ps1') -DryRun
if ($LASTEXITCODE -ne 0 -or (Test-Path -LiteralPath $env:WAVE_HOME)) { throw 'W-DRYRUN-SIDE-EFFECT: DryRun 실패 또는 설치 상태 생성' }
# 원본 함수만 로드하며 S02 인증을 합성 성공으로 대체하지 않는다.
$text = Get-Content -LiteralPath (Join-Path $run 'bootstrap.ps1') -Raw -Encoding utf8
$marker = "`nLoad-Config`nif (`$DryRun)"
$idx = $text.IndexOf($marker, [StringComparison]::Ordinal)
if ($idx -lt 0) { throw '설치기 함수 경계 불일치' }
$parts = @($text.Substring(0, $idx), $text.Substring($idx + $marker.Length))
$harness = Join-Path $run 'signed-install-smoke.ps1'
$tail = @'
Load-Config
if ($WaveVersion -cne $env:WAVE_TERMINAL_TAG.Substring(1) -or $WaveWinSha256 -cne $env:WAVE_TERMINAL_SHA256) { throw '요청 자산과 커밋된 Windows 핀 불일치' }
Run-S03
Run-S04
if ($StepObserved.installer_exit -ne 0 -or -not $StepObserved.cys -or -not $StepObserved.cysd) { throw '설치 관측값 불일치' }
[ordered]@{ status = 'completed'; scope = 'S03/S04 Windows runner smoke'; terminal_version = $ReleaseVersion; asset = $ReleaseAssetName; sha256 = $ReleaseExpectedSha256; observed = $StepObserved; exclusions = @('S02 실로그인 미검증','실기기 미검증','10단계 전량 PASS 아님') } | ConvertTo-Json -Depth 10 | Set-Content -LiteralPath (Join-Path $PSScriptRoot 'windows-smoke-evidence.json') -Encoding utf8NoBOM
'@
($parts[0] + "`n" + $tail) | Set-Content -LiteralPath $harness -Encoding utf8NoBOM
& pwsh -NoProfile -NonInteractive -File $harness
if ($LASTEXITCODE -ne 0) { throw '서명 검증 또는 실제 NSIS 설치 실패' }
Copy-Item (Join-Path $run 'windows-smoke-evidence.json') -Destination (Join-Path $source 'windows-smoke-evidence.json')
Write-Host 'PASS: GitHub Windows 러너 S03/S04 스모크. 실기기 미검증.'
