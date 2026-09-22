[CmdletBinding()]
param(
  [switch]$Reinstall,
  [switch]$Resume,
  [switch]$DryRun
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$WaveHome = if ($env:WAVE_HOME) { $env:WAVE_HOME } else { Join-Path $env:USERPROFILE ".wave" }
$PackHome = Join-Path $env:USERPROFILE ".cys\pack"
$StepsFile = Join-Path $ScriptDir "steps.json"
$StateTemplate = Join-Path $ScriptDir "install-state.json"
$StateFile = Join-Path $WaveHome "install-state.json"
$LogFile = Join-Path $WaveHome "install.log"
$Config = $null
$State = $null
$StepObserved = [ordered]@{}
$StepStatus = "passed"

function Now-Utc {
  return [DateTime]::UtcNow.ToString("yyyy-MM-ddTHH:mm:ssZ")
}

function Write-Log([string]$Message) {
  $line = "[$(Now-Utc)] $Message"
  Write-Host $line
  if (Test-Path (Split-Path -Parent $LogFile)) { Add-Content -LiteralPath $LogFile -Value $line -Encoding UTF8 }
}

function Assert-UserPath([string]$Path) {
  $full = [IO.Path]::GetFullPath($Path)
  $home = [IO.Path]::GetFullPath($env:USERPROFILE)
  if (-not ($full.Equals($home, [StringComparison]::OrdinalIgnoreCase) -or $full.StartsWith($home + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase))) {
    throw "사용자 프로필 밖 경로는 허용하지 않음: $Path"
  }
}

function Get-ConfigValue([string]$Path) {
  $value = $Config
  foreach ($part in $Path.Split('.')) { $value = $value.$part }
  return $value
}

function Load-Config {
  if (-not (Test-Path -LiteralPath $StepsFile)) {
    $url = if ($env:WAVE_INSTALL_STEPS_URL) { $env:WAVE_INSTALL_STEPS_URL } else { "__S3_STEPS_URL__" }
    if ($url -like "__*__") { throw "steps.json URL이 S5 전 배포 자리표시자 상태임" }
    if (-not ($url -like "https://*")) { throw "steps.json은 HTTPS URL이어야 함" }
    New-Item -ItemType Directory -Force -Path (Join-Path $WaveHome "config") | Out-Null
    $StepsFile = Join-Path $WaveHome "config\steps.json"
    Invoke-WebRequest -UseBasicParsing -Uri $url -OutFile $StepsFile
  }
  $script:Config = Get-Content -LiteralPath $StepsFile -Raw -Encoding UTF8 | ConvertFrom-Json
}

function Init-State {
  Assert-UserPath $WaveHome
  New-Item -ItemType Directory -Force -Path $WaveHome | Out-Null
  if ($Reinstall -and (Test-Path -LiteralPath $StateFile)) {
    Copy-Item -LiteralPath $StateFile -Destination ($StateFile + ".bak." + [DateTime]::UtcNow.ToString("yyyyMMddTHHmmssZ"))
    Copy-Item -LiteralPath $StateTemplate -Destination $StateFile -Force
  } elseif (-not (Test-Path -LiteralPath $StateFile)) {
    Copy-Item -LiteralPath $StateTemplate -Destination $StateFile
  }
  $script:State = Get-Content -LiteralPath $StateFile -Raw -Encoding UTF8 | ConvertFrom-Json
  $State.paths.state = $StateFile
  $State.paths.log = $LogFile
  $State.paths.wave_home = $WaveHome
  $State.paths.pack = $PackHome
  $State | ConvertTo-Json -Depth 20 | Set-Content -LiteralPath $StateFile -Encoding UTF8
  New-Item -ItemType File -Force -Path $LogFile | Out-Null
}

function Save-State {
  $State | ConvertTo-Json -Depth 20 | Set-Content -LiteralPath $StateFile -Encoding UTF8
}

function Update-Step([string]$Id, [string]$Status, [int]$ExitCode, [string]$ErrorId, [object]$Observed) {
  $entry = $State.steps.$Id
  $now = Now-Utc
  if ($Status -eq "running" -and -not $entry.started_at) { $entry.started_at = $now }
  $entry.status = $Status
  $entry.exit_code = $ExitCode
  $entry.error_id = if ($ErrorId) { $ErrorId } else { $null }
  $entry.observed = $Observed
  $entry.checks = @("exit_code=$ExitCode")
  if ($Status -ne "running") { $entry.completed_at = $now }
  $entry.version = [string](Get-ConfigValue "release.version")
  $State.current_step = if ($Status -eq "running") { $Id } else { $State.current_step }
  $State.updated_at = $now
  if ($Status -eq "running") { $State.status = "running" }
  Save-State
}

function Release-Context {
  $arch = $env:PROCESSOR_ARCHITECTURE.ToLowerInvariant()
  $platform = if ($arch -eq "amd64") { "windows_x64" } else { throw "지원하지 않는 Windows 아키텍처: $arch" }
  $script:ReleasePlatform = $platform
  $script:ReleaseVersion = [string](Get-ConfigValue "release.version")
  $script:ReleaseAssetName = [string](Get-ConfigValue "release.asset_name.$platform")
  $script:ReleaseAssetUrl = [string](Get-ConfigValue "release.asset_url.$platform")
  $script:ReleaseExpectedSha256 = [string](Get-ConfigValue "release.sha256.$platform")
  $script:ReleaseSumsUrl = [string](Get-ConfigValue "release.sha256sums_url")
  $script:ReleaseMinisigUrl = [string](Get-ConfigValue "release.minisig_url.$platform")
  $script:ReleasePublicKey = [string](Get-ConfigValue "release.minisign_public_key")
  foreach ($value in @($ReleaseVersion, $ReleaseAssetName, $ReleaseAssetUrl, $ReleaseExpectedSha256, $ReleaseSumsUrl, $ReleaseMinisigUrl, $ReleasePublicKey)) {
    if ($value -like "__*__") { throw "S2 릴리스 자리표시자 잔존" }
  }
  if (-not ($ReleaseAssetUrl -like "https://*")) { throw "릴리스 asset URL은 HTTPS여야 함" }
  if ($ReleaseExpectedSha256 -notmatch "^[0-9a-f]{64}$") { throw "S2 SHA256 값이 유효하지 않음" }
  if ($ReleaseAssetName.Contains("\")) { throw "asset 파일명에 경로가 들어갈 수 없음" }
  $script:ArtifactPath = Join-Path (Join-Path $WaveHome "downloads") $ReleaseAssetName
}

function Run-S00 {
  if ($env:OS -ne "Windows_NT") { throw "Windows가 아님" }
  $drive = Get-PSDrive -Name C
  $min = [int64](Get-ConfigValue "tooling.min_free_bytes")
  if ($drive.Free -lt $min) { throw "디스크 여유 공간 부족" }
  New-Item -ItemType Directory -Force -Path $WaveHome | Out-Null
  $probe = Join-Path $WaveHome (".write-probe." + $PID)
  [IO.File]::WriteAllText($probe, "probe")
  Remove-Item -LiteralPath $probe -Force
  $script:StepObserved = [ordered]@{ os = "windows"; powershell = $PSVersionTable.PSVersion.ToString(); free_bytes = $drive.Free; user_path = $true }
}

function Run-S01 {
  if (-not (Get-Command claude -ErrorAction SilentlyContinue)) { throw "claude 명령 없음" }
  $pin = [string](Get-ConfigValue "tooling.claude_code_version")
  if ($pin -like "__*__") { throw "Claude Code 버전 핀이 아직 정해지지 않음" }
  $version = (& claude --version 2>$null | Out-String).Trim()
  if (-not $version.Contains($pin)) { throw "Claude Code 버전 핀 불일치" }
  $tooling = Join-Path $WaveHome "tooling"
  New-Item -ItemType Directory -Force -Path $tooling | Out-Null
  Set-Content -LiteralPath (Join-Path $tooling "claude.version") -Value $version -Encoding UTF8
  $script:StepObserved = [ordered]@{ claude_version = $version }
}

function Run-S02 {
  & claude auth status *> $null
  if ($LASTEXITCODE -ne 0) { throw "Claude 로그인 상태 확인 실패" }
  $auth = Join-Path $WaveHome "auth"
  New-Item -ItemType Directory -Force -Path $auth | Out-Null
  New-Item -ItemType File -Force -Path (Join-Path $auth "claude-authenticated") | Out-Null
  $script:StepObserved = [ordered]@{ authenticated = $true; account_recorded = $false }
}

function Run-S03 {
  if (-not (Get-Command minisign -ErrorAction SilentlyContinue)) { throw "minisign 명령 없음" }
  Release-Context
  $downloads = Join-Path $WaveHome "downloads"
  New-Item -ItemType Directory -Force -Path $downloads | Out-Null
  $sums = Join-Path $downloads "SHA256SUMS"
  $sig = $ArtifactPath + ".minisig"
  Invoke-WebRequest -UseBasicParsing -Uri $ReleaseAssetUrl -OutFile $ArtifactPath
  Invoke-WebRequest -UseBasicParsing -Uri $ReleaseSumsUrl -OutFile $sums
  Invoke-WebRequest -UseBasicParsing -Uri $ReleaseMinisigUrl -OutFile $sig
  $expectedLine = Get-Content -LiteralPath $sums | Where-Object { $_ -match [Regex]::Escape($ReleaseAssetName) } | Select-Object -First 1
  $expected = ($expectedLine -split '\s+')[0]
  $actual = (Get-FileHash -LiteralPath $ArtifactPath -Algorithm SHA256).Hash.ToLowerInvariant()
  if (-not $expected -or $expected.ToLowerInvariant() -ne $actual -or $ReleaseExpectedSha256 -ne $actual) { throw "SHA256 불일치" }
  & minisign -Vm $ArtifactPath -P $ReleasePublicKey -x $sig *> $null
  if ($LASTEXITCODE -ne 0) { throw "minisign 검증 실패" }
  $script:StepObserved = [ordered]@{ platform = $ReleasePlatform; asset = $ReleaseAssetName; sha256 = $actual; minisig_verified = $true }
}

function Run-S04 {
  Release-Context
  if (-not (Test-Path -LiteralPath $ArtifactPath)) { throw "검증된 artifact 없음" }
  $apps = Join-Path $WaveHome "apps"
  $bin = Join-Path $WaveHome "bin"
  New-Item -ItemType Directory -Force -Path $apps, $bin | Out-Null
  $app = Join-Path $apps "WaveTerminal.exe"
  Copy-Item -LiteralPath $ArtifactPath -Destination $app -Force
  $cys = Join-Path $bin "cys.exe"
  $cysd = Join-Path $bin "cysd.exe"
  if (-not (Test-Path -LiteralPath $cys) -or -not (Test-Path -LiteralPath $cysd)) { throw "S2 설치 산출물의 cys/cysd 경로가 없음" }
  & $cys --version *> $null
  if ($LASTEXITCODE -ne 0) { throw "cys 실행 확인 실패" }
  & $cysd --version *> $null
  if ($LASTEXITCODE -ne 0) { throw "cysd 실행 확인 실패" }
  $script:StepObserved = [ordered]@{ cys = $true; cysd = $true; shell_link = $true; admin_required = $false }
}

function Run-S05 {
  $daemon = Join-Path $WaveHome "daemon"
  New-Item -ItemType Directory -Force -Path $daemon | Out-Null
  $result = Join-Path $daemon "register-result"
  if ($env:WAVE_ENABLE_DAEMON -eq "0") {
    Set-Content -LiteralPath $result -Value "skipped_by_user" -Encoding UTF8
    $script:StepStatus = "skipped"
    $script:StepObserved = [ordered]@{ mode = "skipped"; registered = $false }
    return
  }
  $cysd = Join-Path $WaveHome "bin\cysd.exe"
  if (-not (Test-Path -LiteralPath $cysd)) { throw "cysd 없음" }
  & schtasks /Create /TN ("WaveTerminal-cysd-" + $env:USERNAME) /SC ONLOGON /TR $cysd /F *> $null
  if ($LASTEXITCODE -ne 0) { throw "사용자 데몬 등록 실패" }
  & schtasks /Query /TN ("WaveTerminal-cysd-" + $env:USERNAME) *> $null
  if ($LASTEXITCODE -ne 0) { throw "사용자 데몬 등록 확인 실패" }
  Set-Content -LiteralPath $result -Value "registered" -Encoding UTF8
  $script:StepObserved = [ordered]@{ mode = "default_on"; registered = $true; admin_required = $false }
}

function Run-S06 {
  $source = if ($env:WAVE_PACK_SOURCE) { $env:WAVE_PACK_SOURCE } else { Join-Path $ScriptDir "wave-pack" }
  if (-not (Test-Path -LiteralPath (Join-Path $source "manifest.json"))) { throw "S1 wave-pack 소스 없음" }
  if (-not (Test-Path -LiteralPath (Join-Path $source "SHA256SUMS"))) { throw "wave-pack SHA256SUMS 없음" }
  New-Item -ItemType Directory -Force -Path $PackHome | Out-Null
  Copy-Item -Path (Join-Path $source "*") -Destination $PackHome -Recurse -Force
  $waveBin = Join-Path $PackHome "bin\wave.ps1"
  if (-not (Test-Path -LiteralPath $waveBin)) { throw "wave.ps1 래퍼 없음" }
  New-Item -ItemType Directory -Force -Path (Join-Path $WaveHome "bin") | Out-Null
  Copy-Item -LiteralPath $waveBin -Destination (Join-Path $WaveHome "bin\wave.ps1") -Force
  $script:StepObserved = [ordered]@{ pack_installed = $true; manifest_present = $true; sha256_manifest_present = $true }
}

function Run-S07 {
  $roles = Join-Path $PackHome "roles.json"
  $wave = Join-Path $WaveHome "bin\wave.ps1"
  if (-not (Test-Path -LiteralPath $roles) -or -not (Test-Path -LiteralPath $wave)) { throw "roles.json 또는 wave CLI 없음" }
  $fleet = Join-Path $WaveHome "fleet"
  New-Item -ItemType Directory -Force -Path $fleet | Out-Null
  & powershell -NoProfile -ExecutionPolicy Bypass -File $wave fleet bootstrap --roles-file $roles *> (Join-Path $fleet "bootstrap.log")
  if ($LASTEXITCODE -ne 0) { throw "초기 편성 기동 실패" }
  & powershell -NoProfile -ExecutionPolicy Bypass -File $wave fleet status --json | Set-Content -LiteralPath (Join-Path $fleet "status.json") -Encoding UTF8
  $status = Get-Content -LiteralPath (Join-Path $fleet "status.json") -Raw | ConvertFrom-Json
  if (@($status.seats).Count -ne 2) { throw "초기 편성 좌석 수가 2가 아님" }
  New-Item -ItemType File -Force -Path (Join-Path $fleet "initial-fleet.ok") | Out-Null
  $script:StepObserved = [ordered]@{ seats = 2; roles = "master+dept" }
}

function Run-S08 {
  $cys = Join-Path $WaveHome "bin\cys.exe"
  $wave = Join-Path $WaveHome "bin\wave.ps1"
  $verify = Join-Path $WaveHome "verify"
  New-Item -ItemType Directory -Force -Path $verify | Out-Null
  & $cys identify *> $null
  if ($LASTEXITCODE -ne 0) { throw "cys identify 실패" }
  & powershell -NoProfile -ExecutionPolicy Bypass -File $wave doctor --json | Set-Content -LiteralPath (Join-Path $verify "doctor.json") -Encoding UTF8
  if ($LASTEXITCODE -ne 0) { throw "wave doctor 실패" }
  $doctor = Get-Content -LiteralPath (Join-Path $verify "doctor.json") -Raw | ConvertFrom-Json
  if ([int]$doctor.identify_exit -ne 0 -or @($doctor.seats).Count -ne 2) { throw "identify·좌석 수 계약 불일치" }
  $limit = [int64](Get-ConfigValue "tooling.max_injected_bytes_per_seat")
  $max = (@($doctor.seats) | ForEach-Object { [int64]$_.injected_bytes } | Measure-Object -Maximum).Maximum
  if ($max -gt $limit) { throw "좌석당 지침 주입량 초과" }
  $script:StepObserved = [ordered]@{ identify_exit = 0; seats = 2; max_injected_bytes = $max }
}

function Mark-RequiredComplete {
  foreach ($step in $Config.steps | Where-Object { $_.index -lt 9 }) {
    $status = [string]$State.steps.($step.id).status
    if ($status -notin @("passed", "skipped")) { throw "필수 단계 미통과: $($step.id)" }
  }
  $State.required_steps_passed = $true
  Save-State
}

function Run-S09 {
  if (-not [bool]$State.required_steps_passed) { throw "필수 단계 통과 상태가 아님" }
  $start = Join-Path $WaveHome "START-HERE.md"
  @("# Wave Terminal 시작하기", "", "설치기 실측 단계 S00–S09를 통과했습니다.", "", "문제가 있으면 ~/.wave/install.log와 install-state.json을 확인하세요. 토큰·계정값은 기록하지 않습니다.") | Set-Content -LiteralPath $start -Encoding UTF8
  if (-not (Test-Path -LiteralPath $start)) { throw "START-HERE 없음" }
  $script:StepObserved = [ordered]@{ required_steps_passed = $true; start_here = $true; silent_completion = $false }
}

function Invoke-Step([string]$Id, [scriptblock]$Action) {
  $script:StepObserved = [ordered]@{}
  $script:StepStatus = "passed"
  Update-Step $Id "running" 0 "" ([ordered]@{})
  try {
    & $Action
    Update-Step $Id $StepStatus 0 "" $StepObserved
  } catch {
    $errorId = [string](($Config.steps | Where-Object { $_.id -eq $Id }).on_fail.error_id)
    Update-Step $Id "failed" 1 $errorId $StepObserved
    throw
  }
}

function Complete-State {
  $State.status = "complete"
  $State.current_step = $null
  Save-State
}

Load-Config
if ($DryRun) {
  Write-Host "dry-run: $StepsFile / $StateFile / $LogFile"
  exit 0
}
Init-State
$actions = @{
  "S00_PREFLIGHT" = { Run-S00 }
  "S01_CLAUDE_INSTALL" = { Run-S01 }
  "S02_CLAUDE_LOGIN" = { Run-S02 }
  "S03_DOWNLOAD_VERIFY" = { Run-S03 }
  "S04_INSTALL_LINK" = { Run-S04 }
  "S05_DAEMON_REGISTER" = { Run-S05 }
  "S06_PACK_INSTALL" = { Run-S06 }
  "S07_INITIAL_FLEET" = { Run-S07 }
  "S08_VERIFY" = { Run-S08 }
  "S09_COMPLETE" = { Run-S09 }
}
foreach ($step in $Config.steps) {
  $id = [string]$step.id
  $current = [string]$State.steps.$id.status
  if ($Resume -and $current -in @("passed", "skipped")) { Write-Log "[$id] resume: 이미 $current — 건너뜀"; continue }
  if ($id -eq "S09_COMPLETE") { Mark-RequiredComplete }
  Write-Log "[$id] 시작"
  Invoke-Step $id $actions[$id]
}
Complete-State
Write-Log "[10/10] Wave Terminal 설치 상태 complete — START-HERE를 확인하세요."
