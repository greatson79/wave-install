[CmdletBinding()]
param(
  [Alias('TerminalTag')][ValidatePattern('^v[0-9]+\.[0-9]+\.[0-9]+(?:-[0-9A-Za-z.-]+)?$')][string]$Tag = 'v0.2.5',
  [Parameter(Mandatory)][ValidatePattern('^[0-9a-f]{64}$')][string]$ExpectedInstallerSha256,
  [ValidatePattern('^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$')][string]$Repo = 'greatson79/wave-terminal'
)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
if ($env:OS -ne 'Windows_NT' -or $env:CI -ne 'true') { throw 'GitHub Windows 러너 전용 검증' }
$source = Split-Path -Parent $PSScriptRoot
$run = Join-Path $env:USERPROFILE ('wave-runner-smoke-' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $run | Out-Null
$env:WAVE_TERMINAL_TAG = $Tag
$env:WAVE_TERMINAL_REPO = $Repo
$env:WAVE_TERMINAL_SHA256 = $ExpectedInstallerSha256
Copy-Item (Join-Path $source 'bootstrap.ps1'), (Join-Path $source 'steps.json'), (Join-Path $source 'install-state.json') -Destination $run
$srcLen = (Get-Item (Join-Path $source 'bootstrap.ps1')).Length
$dstLen = (Get-Item (Join-Path $run 'bootstrap.ps1')).Length
Write-Host "DIAG: bootstrap.ps1 source bytes=$srcLen copy bytes=$dstLen"
$env:WAVE_HOME = Join-Path $run 'wave'
$configPath = Join-Path $run 'steps.json'
$config = Get-Content -LiteralPath $configPath -Raw | ConvertFrom-Json
$version = [string]$config.release.version
if ($version -notmatch '^[0-9]+\.[0-9]+\.[0-9]+$' -or $Tag -notmatch ('^v' + [regex]::Escape($version) + '(?:-[0-9A-Za-z.-]+)?$')) { throw '태그와 고정 앱 버전이 일치하지 않음' }
$asset = [string]$config.release.asset_name.windows_x64
$base = "https://github.com/$Repo/releases/download/$Tag"
$config.release.version = $version
$config.release.repository = $Repo
$config.release.asset_name.windows_x64 = $asset
$config.release.asset_url.windows_x64 = "$base/$asset"
$config.release.sha256.windows_x64 = $ExpectedInstallerSha256
$config.release.minisig_url.windows_x64 = "$base/$asset.minisig"
$config.release.sha256sums_url = "$base/SHA256SUMS"
$config.release.windows_sha256sums_url = "$base/SHA256SUMS"
$config | ConvertTo-Json -Depth 30 | Set-Content -LiteralPath $configPath -Encoding utf8NoBOM
# 네이티브 -File 인자 바인딩 경로를 반드시 행사한다.
& pwsh -NoProfile -NonInteractive -File (Join-Path $run 'bootstrap.ps1') -DryRun
if ($LASTEXITCODE -ne 0 -or (Test-Path -LiteralPath $env:WAVE_HOME)) { throw 'W-DRYRUN-SIDE-EFFECT: DryRun 실패 또는 설치 상태 생성' }
# 원본 함수만 로드하며 S02 인증을 합성 성공으로 대체하지 않는다.
$text = (Get-Content -LiteralPath (Join-Path $run 'bootstrap.ps1') -Raw -Encoding utf8) -replace "`r`n", "`n"
$marker = "`nLoad-Config`nif (`$DryRun)"
$idx = $text.IndexOf($marker, [StringComparison]::Ordinal)
if ($idx -lt 0) {
  $lcIdx = $text.IndexOf('Load-Config', [StringComparison]::Ordinal)
  Write-Host "DIAG: text length=$($text.Length) Load-Config at=$lcIdx"
  if ($lcIdx -ge 0) {
    $ctx = $text.Substring([Math]::Max(0, $lcIdx - 5), [Math]::Min(60, $text.Length - [Math]::Max(0, $lcIdx - 5)))
    Write-Host ("DIAG: context bytes=" + (($ctx.ToCharArray() | ForEach-Object { [int]$_ }) -join ','))
  }
  throw '설치기 함수 경계 불일치'
}
$parts = @($text.Substring(0, $idx), $text.Substring($idx + $marker.Length))
$harness = Join-Path $run 'signed-install-smoke.ps1'
$tail = @'
Load-Config
if ($WaveVersion -cne $ReleaseVersion -or $env:WAVE_TERMINAL_TAG -notmatch ('^v' + [regex]::Escape($ReleaseVersion) + '(?:-[0-9A-Za-z.-]+)?$') -or $WaveWinSha256 -cne $env:WAVE_TERMINAL_SHA256) { throw '요청 자산과 커밋된 Windows 핀 불일치' }
Run-S03
Run-S04
if ($StepObserved.installer_exit -ne 0 -or -not $StepObserved.cys -or -not $StepObserved.cysd) { throw '설치 관측값 불일치' }
$firstObserved = $StepObserved
Run-S03
Run-S04
if ($StepObserved.installer_exit -ne 0 -or -not $StepObserved.cys -or -not $StepObserved.cysd) { throw '같은 판 재실행 관측값 불일치' }
$rerunObserved = $StepObserved
$links = @((Join-Path ([Environment]::GetFolderPath('Programs')) 'Wave Terminal.lnk'), (Join-Path ([Environment]::GetFolderPath('Programs')) 'Wave Terminal\Wave Terminal.lnk'))
if (-not (($links | Where-Object { Test-Path -LiteralPath $_ }).Count)) { throw '시작 메뉴 Wave Terminal 바로가기 없음' }
$desktopLink = Join-Path ([Environment]::GetFolderPath('Desktop')) 'Wave Terminal.lnk'
if (-not (Test-Path -LiteralPath $desktopLink)) { throw '바탕화면 Wave Terminal 바로가기 없음' }
$shell = New-Object -ComObject WScript.Shell
foreach ($link in @(($links | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1), $desktopLink)) {
  if ([IO.Path]::GetFullPath($shell.CreateShortcut($link).TargetPath) -ne [IO.Path]::GetFullPath((Join-Path $env:WAVE_HOME 'bin\cys-app.exe'))) { throw "바로가기 대상 불일치: $link" }
}
[ordered]@{ status = 'completed'; scope = 'S03/S04 Windows runner smoke'; terminal_version = $ReleaseVersion; release_tag = $env:WAVE_TERMINAL_TAG; repository = $env:WAVE_TERMINAL_REPO; asset = $ReleaseAssetName; sha256 = $ReleaseExpectedSha256; observed = $firstObserved; same_version_rerun = $rerunObserved; exclusions = @('S02 실로그인 미검증','실기기 미검증','10단계 전량 PASS 아님') } | ConvertTo-Json -Depth 10 | Set-Content -LiteralPath (Join-Path $PSScriptRoot 'windows-smoke-evidence.json') -Encoding utf8NoBOM
'@
($parts[0] + "`n" + $tail) | Set-Content -LiteralPath $harness -Encoding utf8NoBOM
& pwsh -NoProfile -NonInteractive -File $harness
if ($LASTEXITCODE -ne 0) { throw '서명 검증 또는 실제 NSIS 설치 실패' }
Copy-Item (Join-Path $run 'windows-smoke-evidence.json') -Destination (Join-Path $source 'windows-smoke-evidence.json')
Write-Host 'PASS: GitHub Windows 러너 S03/S04 스모크. 실기기 미검증.'
