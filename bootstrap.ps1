[CmdletBinding()]
param(
  [switch]$Reinstall,
  [switch]$Resume,
  [switch]$DryRun
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
# PS 5.1: 진행 막대가 Invoke-WebRequest 큰 파일(앱 128MB)을 수십 배 느리게 해 멈춘 것처럼 보인다 · 구형 Win10 은 TLS1.2 를 켜야 GitHub 에 붙는다
$ProgressPreference = 'SilentlyContinue'
try { [Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12 } catch { }

$ScriptDir = if ($PSCommandPath) { Split-Path -Parent $PSCommandPath } else { $null }
$BundleUrl = if ($env:WAVE_INSTALL_ZIP_URL) { $env:WAVE_INSTALL_ZIP_URL } else { '__WAVE_INSTALL_ZIP_URL__' }
$BundleSha256 = if ($env:WAVE_INSTALL_ZIP_SHA256) { $env:WAVE_INSTALL_ZIP_SHA256 } else { '__WAVE_INSTALL_ZIP_SHA256__' }
$WaveHome = if ($env:WAVE_HOME) { $env:WAVE_HOME } else { Join-Path $env:USERPROFILE ".wave" }
$PackHome = Join-Path $env:USERPROFILE ".cys\pack"
$StepsFile = if ($ScriptDir) { Join-Path $ScriptDir "steps.json" } else { '' }
$StateTemplate = if ($ScriptDir) { Join-Path $ScriptDir "install-state.json" } else { '' }
$StateFile = Join-Path $WaveHome "install-state.json"
$LogFile = Join-Path $WaveHome "install.log"
$Config = $null
$State = $null
$StepObserved = [ordered]@{}
$StepStatus = "passed"

# 이 설치 도우미는 oogisoogi/jarvis-install(MIT)을 바탕으로 구현했습니다.
# 원작 cys-terminal: idoforgod (MIT). LICENSES/jarvis-install-MIT.txt 참조.
# 릴리스 핀 정본은 steps.json release 블록이다. Load-Config에서 검증해 채운다.
$WaveVersion = $null
$WaveWinBytes = $null
$WaveWinSha256 = $null
$WaveWinFile = $null
$InstallDoneFile = Join-Path $WaveHome 'install-done.txt'
$RerunDoneWindowSec = 600
$ProgressUrl = 'https://waveainetworks.com/api/progress'
$ProgressTimeoutSec = 3
# 진행 신호 시간 상한(맥과 같다): 호출 1회 벽시계 3초(DNS 포함) · 설치 1회 누적 15초(실패는 3초로 계산, 다 쓰면 이번 설치에서는 끈다).
$ProgressBudgetMs = 15000
$ProgressSpentMs = 0
$InstallId = ''
$ProgressWarned = $false
$CurrentStep = '1/10'
$DiagnosticWritten = $false
$AwakeningStartedAt = $null
# 설치 도움(R5): lib/install-help.ps1 이 설치팩에 있으면 불러온다. 첫 화면 고지 전에는 진행·도움 모두 보내지 않는다.
$HelpNoticeShown = $false
$HelpInteractive = $false
$LastJCode = 'J-UNK-00'
$HelpLib = if ($ScriptDir) { Join-Path (Join-Path $ScriptDir 'lib') 'install-help.ps1' } else { '' }
if ($HelpLib -and (Test-Path -LiteralPath $HelpLib -PathType Leaf)) { . $HelpLib }

function Say([string]$Message) { Write-Log $Message }

function Say-Step([object]$Step, [string]$Message) {
  $script:CurrentStep = '{0}/10' -f ([int]$Step.index + 1)
  Say "[$CurrentStep] $($Step.title) — $Message"
}

function Get-JCode([string]$Message) {
  foreach ($rule in $HelpRules) {
    if ($Message -match $rule.pattern) { return [string]$rule.code }
  }
  return 'J-UNK-00'
}

function Write-JCode([string]$Code) {
  $matches5 = [object[]]($HelpRules | Where-Object { $_.code -eq $Code })
  $rule = if ($matches5.Count -gt 0) { $matches5[0] } else { $null }
  if ($null -eq $rule) { $Code = 'J-UNK-00'; $rule = $HelpRules[-1] }
  $script:DiagnosticWritten = $true
  $script:LastJCode = $Code
  # Reporting must still run when local logging fails (disk/permission errors).
  try {
    Say "진단 코드: $Code — $($rule.symptom)"
    Say $rule.action1
    Say $rule.action2
    Say "도움말: https://github.com/greatson79/wave-install/blob/main/docs/help-codes.md#$($Code.ToLowerInvariant())"
  } catch { Write-Host "진단 코드: $Code — $($rule.symptom)" }
  Send-Progress $CurrentStep 'fail' $null $Code
}

function Get-WaveInstallId {
  if (-not $script:InstallId) {
    Assert-UserPath $WaveHome
    $idPath = Join-Path $WaveHome 'install-id.txt'
    $id = if (Test-Path -LiteralPath $idPath) { (Get-Content -LiteralPath $idPath -Raw).Trim() } else { '' }
    if ($id -notmatch '^[a-f0-9]{32}$') {
      $id = [guid]::NewGuid().ToString('N')
      Set-Content -LiteralPath $idPath -Value $id -Encoding ASCII
    }
    $script:InstallId = $id
  }
  return $script:InstallId
}

# 설치기 버전은 steps.json version(RC 때 정해짐)에서 읽는다. 고정 문자열을 두지 않는다.
function Get-InstallerVersion {
  $version = [string](Get-StateField $Config 'version')
  if ($version -cmatch '^[0-9A-Za-z._-]{1,20}$') { return $version }
  return 'unknown'
}

# 진행 POST 1회. Invoke-WebRequest -TimeoutSec 은 DNS 해석 시간을 덮지 못하므로 Task.Wait 로 전체 벽시계를 강제한다.
# 리다이렉트 금지 · 2xx 외 실패. 시간이 넘으면 요청을 취소하고 실패로 돌려준다(설치 상태와 무관).
function Invoke-ProgressPost([uri]$Uri, [byte[]]$Body, [int]$TimeoutMs) {
  Add-Type -AssemblyName System.Net.Http -ErrorAction SilentlyContinue
  $handler = New-Object System.Net.Http.HttpClientHandler
  $handler.AllowAutoRedirect = $false
  $client = New-Object System.Net.Http.HttpClient -ArgumentList $handler
  $cancel = New-Object System.Threading.CancellationTokenSource
  try {
    $content = New-Object System.Net.Http.ByteArrayContent -ArgumentList (,$Body)
    $content.Headers.ContentType = [System.Net.Http.Headers.MediaTypeHeaderValue]::Parse('application/json; charset=utf-8')
    $task = $client.PostAsync($Uri, $content, $cancel.Token)
    if (-not $task.Wait($TimeoutMs)) { $cancel.Cancel(); throw 'progress deadline exceeded' }
    $status = [int]$task.Result.StatusCode
    $task.Result.Dispose()
    if ($status -lt 200 -or $status -ge 300) { throw "progress status $status" }
  } finally { $client.Dispose(); $cancel.Dispose() }
}

function Send-Progress([string]$Step, [string]$Event, $Elapsed = $null, [string]$Detail = '') {
  if ($DryRun -or $env:WAVE_NO_PROGRESS -eq '1' -or -not $script:HelpNoticeShown) { return }
  if ($script:ProgressSpentMs -ge $ProgressBudgetMs) { return }
  $clock = [Diagnostics.Stopwatch]::StartNew()
  $failed = $false
  try {
    $url = if ($env:WAVE_PROGRESS_URL) { $env:WAVE_PROGRESS_URL } elseif ($env:WAVE_HELP_BASE_URL) { $env:WAVE_HELP_BASE_URL.TrimEnd('/') + '/api/progress' } else { $ProgressUrl }
    $uri = [uri]$url
    if ($uri.Scheme -ne 'https' -or $uri.AbsolutePath -ne '/api/progress') { throw 'invalid progress endpoint' }
    $null = Get-WaveInstallId
    $fields = [ordered]@{
      install_id = $InstallId
      installer_version = (Get-InstallerVersion)
      os = 'win'
      step = $Step
      event = $Event
      at = (Now-Utc)
    }
    if ($null -ne $Elapsed) { $fields.elapsed_s = [int]$Elapsed }
    # Only diagnostic codes leave the machine; never send raw exception text or accounts.
    if ($Detail -match '^J-[A-Z0-9]+-[0-9]{2}$') { $fields.detail = $Detail }
    $body = $fields | ConvertTo-Json -Compress
    if ([Text.Encoding]::UTF8.GetByteCount($body) -gt 8KB) { throw 'progress body too large' }
    $ProgressPreference = 'SilentlyContinue'
    [Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12
    Invoke-ProgressPost $uri ([Text.Encoding]::UTF8.GetBytes($body)) ($ProgressTimeoutSec * 1000)
  } catch {
    $failed = $true
    if (-not $script:ProgressWarned) {
      $script:ProgressWarned = $true
      try { Write-Log 'progress send failed (fail-open); 설치를 계속합니다.' } catch { }
    }
  }
  $used = $clock.ElapsedMilliseconds
  if ($failed -and $used -lt $ProgressTimeoutSec * 1000) { $used = $ProgressTimeoutSec * 1000 }
  $script:ProgressSpentMs += $used
  if ($script:ProgressSpentMs -ge $ProgressBudgetMs) {
    try { Write-Log "진행 신호 시간 예산($($ProgressBudgetMs / 1000)초)을 다 써서 이번 설치에서는 진행 신호를 보내지 않습니다. 설치는 계속합니다." } catch { }
  }
}

function Get-ArtifactHash([string]$Path) {
  try { return (Get-FileHash -LiteralPath $Path -Algorithm SHA256 -ErrorAction Stop).Hash.ToLowerInvariant() }
  catch { throw 'W-HASH-READ: 지문을 잴 수 없습니다' }
}

function Ensure-Pack {
  # 스크립트 파일로 실행 중이고 steps.json 이 있으면(설치팩 안·테스트) 받지 않는다. irm|iex 는 $ScriptDir 이 없어 받는다.
  if ($ScriptDir -and $StepsFile -and (Test-Path -LiteralPath $StepsFile -PathType Leaf)) { return }
  if ($BundleUrl -notmatch '^https://' -or $BundleSha256 -notmatch '^[a-fA-F0-9]{64}$') {
    throw '설치팩 ZIP URL·고정 SHA256 미확정'
  }
  $source = Join-Path $WaveHome 'src'
  Assert-UserPath $source
  New-Item -ItemType Directory -Force -Path $source | Out-Null
  $zipPath = Join-Path $source ('wave-install-' + [guid]::NewGuid().ToString('N') + '.zip')
  try {
    Invoke-WebRequest -UseBasicParsing -Uri $BundleUrl -OutFile $zipPath -ErrorAction Stop
    if ((Get-ArtifactHash $zipPath) -ne $BundleSha256.ToLowerInvariant()) { throw '설치팩 ZIP SHA256 불일치' }
    Add-Type -AssemblyName System.IO.Compression
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    $archive = [IO.Compression.ZipFile]::OpenRead($zipPath)
    try {
      $roots = @{}
      foreach ($entry in $archive.Entries) {
        $name = $entry.FullName.Replace('\', '/')
        if (-not $name -or $name.StartsWith('/') -or $name -match '(^|/)\.\.(/|$)|(^|/)\.(/|$)|:|//') { throw '설치팩 ZIP 위험 경로' }
        $roots[$name.Split('/')[0]] = $true
        if (($entry.ExternalAttributes -shr 16 -band 0xF000) -eq 0xA000) { throw '설치팩 ZIP symlink 거부' }
      }
      if ($roots.Count -ne 1) { throw '설치팩 ZIP 최상위 폴더는 하나여야 함' }
      $destination = Join-Path $source ('pack-' + [guid]::NewGuid().ToString('N'))
      [IO.Compression.ZipFile]::ExtractToDirectory($zipPath, $destination)
    } finally { $archive.Dispose() }
    $pack = Join-Path $destination (@($roots.Keys)[0])
    foreach ($required in @('bootstrap.ps1', 'steps.json', 'install-state.json')) {
      if (-not (Test-Path -LiteralPath (Join-Path $pack $required) -PathType Leaf)) { throw "설치팩 구성 누락: $required" }
    }
    if (-not (Test-Path -LiteralPath (Join-Path $pack 'wave-pack') -PathType Container)) { throw '설치팩 wave-pack 누락' }
    # -File 로 넘긴 인수는 전부 문자열이라 -Reinstall:False 는 switch 로 안 바뀐다(PS 5.1 실기 실패 2026-10-01) → 켜진 스위치만 넘긴다
    $relaunch = @()
    if ($Reinstall) { $relaunch += '-Reinstall' }
    if ($Resume) { $relaunch += '-Resume' }
    if ($DryRun) { $relaunch += '-DryRun' }
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File (Join-Path $pack 'bootstrap.ps1') @relaunch
    exit $LASTEXITCODE
  } finally { Remove-Item -LiteralPath $zipPath -Force -ErrorAction SilentlyContinue }
}

function Test-WebMark([string]$Path) {
  # Non-NTFS downloads have no ADS. No global SmartScreen/antivirus settings change.
  if (-not (Get-Command Get-Item).Parameters.ContainsKey('Stream')) { return $false }
  return [bool](Get-Item -LiteralPath $Path -Stream 'Zone.Identifier' -ErrorAction SilentlyContinue)
}

function Clear-WebMark([string]$Path, [string]$ExpectedSha256) {
  if ($DryRun) { return 'dry' }
  if ($ExpectedSha256 -notmatch '^[a-fA-F0-9]{64}$' -or (Get-ArtifactHash $Path) -ne $ExpectedSha256.ToLowerInvariant()) {
    throw 'SHA256 불일치: 웹 표식을 제거하지 않았습니다'
  }
  if (-not (Test-WebMark $Path)) { Write-Log 'motw: none'; return 'none' }
  try {
    Unblock-File -LiteralPath $Path -ErrorAction Stop
    Write-Log 'motw: removed after sha256 match'
    return 'removed'
  } catch {
    Write-Log 'motw: remove failed; 파일 검증은 통과했지만 웹 표식 제거는 실패했습니다.'
    return 'failed'
  }
}

function Test-StepComplete([string]$Id) {
  if ($Reinstall -or $Id -eq 'S09_COMPLETE') { return $false }
  $entry = $State.steps.$Id
  if ($entry.status -ne 'passed' -or $entry.exit_code -ne 0 -or $entry.error_id -or (Test-SyntheticBypass $entry)) { return $false }
  if ($entry.version -ne [string]$Config.release.version) { return $false }
  # Authentication, preflight, and measured verification are live checks on every run.
  if ($Id -in @('S00_PREFLIGHT', 'S01_CLAUDE_INSTALL', 'S02_CLAUDE_LOGIN', 'S05_DAEMON_REGISTER', 'S06_PACK_INSTALL', 'S07_INITIAL_FLEET', 'S08_VERIFY')) { return $false }
  if ($Id -eq 'S03_DOWNLOAD_VERIFY') {
    try {
      Release-Context
      return ((Test-Path -LiteralPath $ArtifactPath -PathType Leaf) -and
        (Get-Item -LiteralPath $ArtifactPath).Length -eq $WaveWinBytes -and
        (Get-ArtifactHash $ArtifactPath) -eq $WaveWinSha256 -and
        (Get-StateField $entry.observed 'authenticode_checked') -eq $true)
    } catch { return $false }
  }
  if ($Id -eq 'S04_INSTALL_LINK') {
    try {
      Release-Context
      $cys = Join-Path $WaveHome 'bin\cys.exe'
      $cysd = Join-Path $WaveHome 'bin\cysd.exe'
      if ((Get-StateField $entry.observed 'verified_installer_sha256') -ne $WaveWinSha256 -or
          (Get-ArtifactHash $cys) -ne (Get-StateField $entry.observed 'cli_sha256') -or
          (Get-ArtifactHash $cysd) -ne (Get-StateField $entry.observed 'daemon_sha256')) { return $false }
      $env:PATH = (Join-Path $WaveHome 'bin') + [IO.Path]::PathSeparator + $env:PATH
      return $true
    } catch { return $false }
  }
  return $true
}

function Save-InstallDone {
  Read-ReleasePins
  if ($State.status -ne 'complete' -or -not $State.required_steps_passed) {
    if (Test-Path -LiteralPath $InstallDoneFile) { Remove-Item -LiteralPath $InstallDoneFile -Force }
    return
  }
  $mark = [ordered]@{
    version = $WaveVersion; bytes = $WaveWinBytes; sha256 = $WaveWinSha256; asset_name = $WaveWinFile
    state_sha256 = (Get-ArtifactHash $StateFile)
    config_sha256 = (Get-ArtifactHash $StepsFile)
  }
  $mark | ConvertTo-Json | Set-Content -LiteralPath $InstallDoneFile -Encoding UTF8
}

function Test-RecentInstallDone {
  if ($Reinstall -or -not (Test-Path -LiteralPath $InstallDoneFile -PathType Leaf)) { return $false }
  try {
    Read-ReleasePins
    $age = ([DateTime]::UtcNow - (Get-Item -LiteralPath $InstallDoneFile).LastWriteTimeUtc).TotalSeconds
    if ($age -lt 0 -or $age -gt $RerunDoneWindowSec) { return $false }
    $mark = Get-Content -LiteralPath $InstallDoneFile -Raw -Encoding UTF8 | ConvertFrom-Json
    $previous = Get-Content -LiteralPath $StateFile -Raw -Encoding UTF8 | ConvertFrom-Json
    return ($previous.status -eq 'complete' -and $previous.required_steps_passed -eq $true -and
      $mark.version -ceq $WaveVersion -and $mark.bytes -eq $WaveWinBytes -and $mark.sha256 -ceq $WaveWinSha256 -and $mark.asset_name -ceq $WaveWinFile -and
      $mark.state_sha256 -ceq (Get-ArtifactHash $StateFile) -and $mark.config_sha256 -ceq (Get-ArtifactHash $StepsFile))
  } catch { return $false }
}

$HelpRulesJson = @'
[
  {
    "code": "J-AV-01",
    "symptom": "보안 제품이 실행을 차단함",
    "pattern": "(?i)virus|malware|바이러스|악성.*차단|defender|v3|알약|alyac|보안.*차단|격리",
    "action1": "백신 알림의 이름·대상 파일·조치를 확인하세요.",
    "action2": "해당 화면과 install.log를 담당자에게 전달하세요. 예외를 자동 등록하지 않습니다.",
    "case": "우리 오류 분류 회귀(보안 오류 주입); 실기 미관측",
    "os": "win",
    "sample": "Operation did not complete because the file contains a virus"
  },
  {
    "code": "J-AV-02",
    "symptom": "다운로드한 설치 파일이 사라짐",
    "pattern": "검증된 artifact 없음|받은 파일이 사라졌습니다",
    "action1": "백신 격리 기록에서 대상 파일을 확인하세요.",
    "action2": "같은 설치 명령으로 다시 받으세요.",
    "case": "우리 S04 artifact 누락 재현; 백신 원인 미확정",
    "os": "win",
    "sample": "검증된 artifact 없음"
  },
  {
    "code": "J-AV-03",
    "symptom": "이전 실행이 실행 중 상태로 중단됨",
    "pattern": "지난 실행이 끝을 알리지 않고 멈췄습니다",
    "action1": "창을 직접 닫았는지 확인하세요. 백신 기록도 확인하세요.",
    "action2": "같은 명령으로 완료 단계를 건너뛰고 이어가세요.",
    "case": "우리 running 상태 중단 회귀; 백신 원인 미확정",
    "os": "win",
    "sample": "지난 실행이 끝을 알리지 않고 멈췄습니다"
  },
  {
    "code": "J-DL-05",
    "symptom": "확정된 Windows 릴리스 정보가 없음",
    "pattern": "핀 미확정|릴리스 자리표시자|릴리스.*유효하지|릴리스.*HTTPS|asset 파일명|(?i:404|not found)",
    "action1": "배포 담당자에게 Windows 버전·바이트·SHA256 확정을 요청하세요.",
    "action2": "확정 자산이 게시된 뒤 다시 실행하세요.",
    "case": "초기 이식의 windows_x64=null·핀 미확정 재현(현재 핀 확정)",
    "os": "win",
    "sample": "Windows 릴리스 핀 미확정"
  },
  {
    "code": "J-NET-01",
    "symptom": "이름 해석 또는 네트워크 연결 실패",
    "pattern": "(?i)name.*resolv|network.*unreachable|인터넷 연결 없음",
    "action1": "인터넷 연결과 DNS 설정을 확인하세요.",
    "action2": "연결을 복구한 뒤 같은 설치 명령을 실행하세요.",
    "case": "우리 네트워크 오류 주입 회귀; 실기 미관측",
    "os": "win",
    "sample": "Network is unreachable"
  },
  {
    "code": "J-NET-02",
    "symptom": "설치 설정 서버에서 응답을 받지 못함",
    "pattern": "W-CONFIG-NET",
    "action1": "설치 설정 URL과 서버 상태를 확인하세요.",
    "action2": "잠시 뒤 같은 설치 명령을 다시 실행하세요.",
    "case": "우리 Load-Config 요청 실패 회귀; 실기 미관측",
    "os": "win",
    "sample": "W-CONFIG-NET: steps.json 요청 실패"
  },
  {
    "code": "J-NET-03",
    "symptom": "릴리스 서버에서 응답을 받지 못함",
    "pattern": "W-DOWNLOAD-NET|(?i:timed out|timeout|connection.*reset)",
    "action1": "릴리스 서버 연결과 프록시 설정을 확인하세요.",
    "action2": "잠시 뒤 다시 실행하세요. 진행 보고 실패는 설치를 막지 않습니다.",
    "case": "우리 S03 다운로드 실패 회귀; 실기 미관측",
    "os": "win",
    "sample": "W-DOWNLOAD-NET: 릴리스 요청 실패"
  },
  {
    "code": "J-RM-01",
    "symptom": "파일이 사용 중이라 설치 작업 실패",
    "pattern": "(?i)being used by another process|sharing violation|파일.*사용 중",
    "action1": "열려 있는 Wave Terminal 창을 닫으세요.",
    "action2": "같은 설치 명령을 다시 실행하세요.",
    "case": "우리 파일 잠금 오류 주입 회귀; 실기 미관측",
    "os": "win",
    "sample": "The file is being used by another process"
  },
  {
    "code": "J-PATH-01",
    "symptom": "필요한 명령 또는 설치 결과 경로가 없음",
    "pattern": "명령 없음|셸 경로 불일치|cys/cysd 경로가 없음|cysd 없음",
    "action1": "새 PowerShell 창에서 명령과 사용자 설치 경로를 확인하세요.",
    "action2": "claude 또는 minisign이 없으면 해당 도구 설치를 완료하세요.",
    "case": "우리 S04 설치 결과 누락 회귀 및 S01 명령 검사",
    "os": "win",
    "sample": "claude 명령 없음"
  },
  {
    "code": "J-LOGIN-01",
    "symptom": "Claude 인증 상태 확인 실패",
    "pattern": "Claude 로그인 상태 확인 실패",
    "action1": "claude auth login으로 브라우저 승인을 마치세요.",
    "action2": "같은 설치 명령을 다시 실행하세요. 토큰은 보내지 마세요.",
    "case": "우리 S02 비정상 종료 회귀; 실제 계정 로그인 미검증",
    "os": "win",
    "sample": "Claude 로그인 상태 확인 실패"
  },
  {
    "code": "J-LOGIN-02",
    "symptom": "인증 코드가 거부됨",
    "pattern": "(?i)invalid.*(?:authorization|authentication).*code|로그인 코드.*거부",
    "action1": "새 로그인 흐름에서 발급된 코드를 사용하세요.",
    "action2": "계속 실패하면 오류 코드만 담당자에게 알려 주세요.",
    "case": "우리 인증 오류 주입 회귀; 현 S02는 코드 입력을 수집하지 않음",
    "os": "win",
    "sample": "Invalid authentication code"
  },
  {
    "code": "J-HOME-01",
    "symptom": "허용되지 않는 작업 폴더",
    "pattern": "사용자 프로필 밖 경로|W-HOME",
    "action1": "WAVE_HOME을 해제하고 사용자 프로필 안 기본 경로로 다시 실행하세요.",
    "action2": "기존 사용자 파일은 삭제하지 마세요.",
    "case": "우리 Assert-UserPath 경계 검사 회귀",
    "os": "win",
    "sample": "사용자 프로필 밖 경로는 허용하지 않음"
  },
  {
    "code": "J-PERM-02",
    "symptom": "사용자 작업의 접근이 거부됨",
    "pattern": "(?i)액세스가 거부|access is denied",
    "action1": "관리자 권한 없이 되는 사용자별 등록 방식으로 다시 시도하세요.",
    "action2": "선택 단계는 오류를 기록하고 계속합니다. 필수 단계의 오류가 계속되면 install.log를 담당자에게 전달하세요.",
    "case": "2026-10-01 Windows 실기 S05 schtasks 접근 거부 보고 및 한국어·영문 오류 주입 회귀",
    "os": "win",
    "sample": "오류: 액세스가 거부되었습니다."
  },
  {
    "code": "J-PERM-01",
    "symptom": "파일 또는 폴더 접근 권한 부족",
    "pattern": "(?i)access.*denied|unauthorized|권한.*없|permission.*denied",
    "action1": "사용자 프로필 폴더에 쓰기 권한이 있는지 확인하세요.",
    "action2": "관리 컴퓨터라면 담당자에게 문의하세요.",
    "case": "우리 파일 쓰기 권한 오류 주입 회귀; 실기 미관측",
    "os": "win",
    "sample": "Access to the path is denied"
  },
  {
    "code": "J-DISK-01",
    "symptom": "설치 공간 부족",
    "pattern": "(?i)디스크 여유 공간 부족|disk.*full|not enough.*space",
    "action1": "설치 드라이브에서 steps.json의 min_free_bytes 이상 확보하세요.",
    "action2": "같은 설치 명령을 다시 실행하세요.",
    "case": "우리 S00 디스크 부족 조건 회귀; 실기 미관측",
    "os": "win",
    "sample": "디스크 여유 공간 부족"
  },
  {
    "code": "J-VER-01",
    "symptom": "필수 도구 버전 또는 플랫폼이 맞지 않음",
    "pattern": "Claude Code.*(?:이상 필요|semver|버전|미정)|지원하지 않는 Windows|Windows가 아님|W-CYSD-PE",
    "action1": "Claude Code는 claude update로 갱신하세요.",
    "action2": "Windows x64와 지원 PowerShell에서 다시 실행하세요.",
    "case": "우리 S01 버전 경계·S04 PE-x64 회귀",
    "os": "win",
    "sample": "중단: Claude Code 2.1.278 이상 필요"
  },
  {
    "code": "J-DL-03",
    "symptom": "파일 지문 측정 실패",
    "pattern": "W-HASH-READ",
    "action1": "파일을 읽을 수 있는지 확인하고 다시 받으세요.",
    "action2": "계속되면 install.log와 오류 코드를 전달하세요.",
    "case": "우리 해시 읽기 실패 주입 회귀; 실기 미관측",
    "os": "win",
    "sample": "W-HASH-READ: 지문을 잴 수 없습니다"
  },
  {
    "code": "J-DL-04",
    "symptom": "릴리스 핀·크기·지문·서명 불일치",
    "pattern": "SHA256 불일치|바이트 불일치|핀 불일치|Authenticode 검증 실패|W-NSIS-ASSET",
    "action1": "검증되지 않은 파일은 실행하지 말고 같은 명령으로 다시 받으세요.",
    "action2": "반복되면 배포 담당자에게 핀과 릴리스 대조를 요청하세요.",
    "case": "우리 S04 변조 회귀·win-pin-mutate 검체",
    "os": "win",
    "sample": "W-ARTIFACT-CHANGED: 설치 직전 SHA256 불일치"
  },
  {
    "code": "J-PS32-01",
    "symptom": "32비트 PowerShell로 실행됨",
    "pattern": "32비트 PowerShell",
    "action1": "시작 메뉴에서 x86이 붙지 않은 Windows PowerShell을 여세요.",
    "action2": "같은 설치 명령을 다시 실행하세요.",
    "case": "우리 32비트 프로세스 분류 회귀; 실기 미관측",
    "os": "win",
    "sample": "32비트 PowerShell에서는 실행할 수 없습니다"
  },
  {
    "code": "J-UNK-00",
    "symptom": "분류하지 못한 설치 실패",
    "pattern": "(?s).*",
    "action1": "install-state.json의 오류 ID와 install.log를 확인하세요.",
    "action2": "민감한 값을 가린 뒤 담당자에게 오류 코드를 알려 주세요.",
    "case": "우리 S04 비정상 NSIS 종료 등 미분류 회귀",
    "os": "win",
    "sample": "W-NSIS-EXIT: 설치기 종료값 7"
  }
]
'@
# Windows PowerShell 5.1's ConvertFrom-Json can hand back an object that member-enumerates
# instead of a real element array; a bare @() wrap does not always force true array-ness on
# 5.1 the way it does on 7+. [object[]] is a type-level cast that does.
$HelpRules = [object[]]($HelpRulesJson | ConvertFrom-Json)

function Now-Utc {
  return [DateTime]::UtcNow.ToString("yyyy-MM-ddTHH:mm:ssZ")
}

function Write-Log([string]$Message) {
  $line = "[$(Now-Utc)] $Message"
  Write-Host $line
  Assert-UserPath $LogFile
  if (Test-Path (Split-Path -Parent $LogFile)) { Add-Content -LiteralPath $LogFile -Value $line -Encoding UTF8 }
}

function Assert-UserPath([string]$Path) {
  $full = [IO.Path]::GetFullPath($Path)
  $profileRoot = [IO.Path]::GetFullPath($env:USERPROFILE)
  if (-not ($full.Equals($profileRoot, [StringComparison]::OrdinalIgnoreCase) -or $full.StartsWith($profileRoot + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase))) {
    throw "사용자 프로필 밖 경로는 허용하지 않음: $Path"
  }
}

function Get-ConfigValue([string]$Path) {
  $value = $Config
  foreach ($part in $Path.Split('.')) { $value = $value.$part }
  return $value
}

function Load-Config {
  Ensure-Pack
  if (-not (Test-Path -LiteralPath $StepsFile)) {
    $url = if ($env:WAVE_INSTALL_STEPS_URL) { $env:WAVE_INSTALL_STEPS_URL } else { "https://raw.githubusercontent.com/greatson79/wave-install/main/steps.json" }
    if ($url -like "__*__") { throw "steps.json URL이 S5 전 배포 자리표시자 상태임" }
    if (-not ($url -like "https://*")) { throw "steps.json은 HTTPS URL이어야 함" }
    New-Item -ItemType Directory -Force -Path (Join-Path $WaveHome "config") | Out-Null
    $StepsFile = Join-Path $WaveHome "config\steps.json"
    try { Invoke-WebRequest -UseBasicParsing -Uri $url -OutFile $StepsFile } catch { throw "W-CONFIG-NET: $($_.Exception.Message)" }
    $script:StepsFile = $StepsFile
  }
  $script:Config = Get-Content -LiteralPath $StepsFile -Raw -Encoding UTF8 | ConvertFrom-Json
  Read-ReleasePins
}

function Read-ReleasePins {
  $release = Get-StateField $Config 'release'
  $version = Get-StateField $release 'version'
  $bytes = Get-StateField (Get-StateField $release 'bytes') 'windows_x64'
  $digest = Get-StateField (Get-StateField $release 'sha256') 'windows_x64'
  $asset = Get-StateField (Get-StateField $release 'asset_name') 'windows_x64'
  if ($version -isnot [string] -or $version -cnotmatch '^\d+\.\d+\.\d+$' -or
      -not (Test-ByteCount $bytes) -or $bytes -le 0 -or
      $digest -isnot [string] -or $digest -cnotmatch '^[a-f0-9]{64}$' -or
      $asset -isnot [string] -or $asset -cnotmatch '^[A-Za-z0-9][A-Za-z0-9._-]*\.exe$' -or $asset.Contains('..')) {
    throw 'Windows 릴리스 핀 미확정: steps.json release version/bytes/sha256/asset_name'
  }
  $script:WaveVersion = $version
  $script:WaveWinBytes = $bytes
  $script:WaveWinSha256 = $digest
  $script:WaveWinFile = $asset
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
  if (-not (Test-Path -LiteralPath $LogFile)) { New-Item -ItemType File -Path $LogFile | Out-Null }
}

function Save-State {
  $State | ConvertTo-Json -Depth 20 | Set-Content -LiteralPath $StateFile -Encoding UTF8
}

function Update-Step([string]$Id, [string]$Status, [int]$ExitCode, [string]$ErrorId, [object]$Observed) {
  if ($Status -eq "passed" -and $ErrorId) { throw "passed와 error_id를 함께 기록할 수 없음" }
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
  Read-ReleasePins
  if (-not [Environment]::Is64BitProcess) { throw '32비트 PowerShell에서는 실행할 수 없습니다' }
  $arch = $env:PROCESSOR_ARCHITECTURE.ToLowerInvariant()
  $platform = if ($arch -eq "amd64") { "windows_x64" } else { throw "지원하지 않는 Windows 아키텍처: $arch" }
  if ($WaveVersion -notmatch '^\d+\.\d+\.\d+$' -or $WaveWinBytes -le 0 -or $WaveWinSha256 -cnotmatch '^[a-f0-9]{64}$') { throw 'Windows 릴리스 핀 미확정' }
  $script:ReleasePlatform = $platform
  $script:ReleaseVersion = [string](Get-ConfigValue "release.version")
  $script:ReleaseAssetName = [string](Get-ConfigValue "release.asset_name.$platform")
  $script:ReleaseAssetUrl = [string](Get-ConfigValue "release.asset_url.$platform")
  $script:ReleaseExpectedSha256 = [string](Get-ConfigValue "release.sha256.$platform")
  $script:ReleaseSumsUrl = [string](Get-ConfigValue "release.windows_sha256sums_url")
  $script:ReleasePublisherSubject = [string](Get-ConfigValue 'release.windows_publisher_subject')
  foreach ($value in @($ReleaseVersion, $ReleaseAssetName, $ReleaseAssetUrl, $ReleaseExpectedSha256, $ReleaseSumsUrl)) {
    if ($value -like "__*__") { throw "S2 릴리스 자리표시자 잔존" }
  }
  if (-not ($ReleaseAssetUrl -like "https://*")) { throw "릴리스 asset URL은 HTTPS여야 함" }
  if ($ReleaseExpectedSha256 -notmatch "^[0-9a-f]{64}$") { throw "S2 SHA256 값이 유효하지 않음" }
  if ($ReleaseVersion -cne $WaveVersion -or $ReleaseAssetName -cne $WaveWinFile -or $ReleaseExpectedSha256 -cne $WaveWinSha256) { throw 'Windows 릴리스 핀 불일치' }
  foreach ($url in @($ReleaseSumsUrl)) {
    if ($url -notlike 'https://*') { throw '릴리스 검증 URL은 HTTPS여야 함' }
  }
  $script:ArtifactPath = Join-Path (Join-Path $WaveHome "downloads") $ReleaseAssetName
}

function Run-S00 {
  if (-not [Environment]::Is64BitProcess) { throw '32비트 PowerShell에서는 실행할 수 없습니다' }
  if ($env:OS -ne "Windows_NT") { throw "Windows가 아님" }
  $drive = Get-PSDrive -Name ([IO.Path]::GetPathRoot($WaveHome).TrimEnd('\').TrimEnd(':'))
  $min = [int64](Get-ConfigValue "tooling.min_free_bytes")
  if ($drive.Free -lt $min) { throw "디스크 여유 공간 부족" }
  New-Item -ItemType Directory -Force -Path $WaveHome | Out-Null
  $probe = Join-Path $WaveHome (".write-probe." + $PID)
  [IO.File]::WriteAllText($probe, "probe")
  Remove-Item -LiteralPath $probe -Force
  $script:StepObserved = [ordered]@{ os = "windows"; powershell = $PSVersionTable.PSVersion.ToString(); free_bytes = $drive.Free; user_path = $true }
}

function Run-S01 {
  if (-not (Get-Command claude -ErrorAction SilentlyContinue)) {
    $installer = Join-Path $WaveHome 'src\claude-install.ps1'
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $installer) | Out-Null
    Invoke-WebRequest -UseBasicParsing -Uri 'https://claude.ai/install.ps1' -OutFile $installer -ErrorAction Stop
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $installer
    if ($LASTEXITCODE -ne 0) { throw 'Claude Code 공식 설치 실패' }
    $env:PATH = (Join-Path $env:USERPROFILE '.local\bin') + [IO.Path]::PathSeparator + $env:PATH
    if (-not (Get-Command claude -ErrorAction SilentlyContinue)) { throw 'Claude Code 설치 후 명령 없음' }
  }
  $pin = [string](Get-ConfigValue "tooling.claude_code_version")
  if ($pin -like "__*__") { throw "Claude Code 버전 핀이 아직 정해지지 않음" }
  $minimum = [string](Get-ConfigValue "tooling.claude_code_min_version")
  if (-not $minimum -or $minimum -like "__*__") { throw "Claude Code 최소 버전 미정" }
  $version = (& claude --version 2>$null | Out-String).Trim()
  if ($LASTEXITCODE -ne 0) { throw "Claude Code 버전 조회 실패" }
  $tooling = Join-Path $WaveHome "tooling"
  New-Item -ItemType Directory -Force -Path $tooling | Out-Null
  Set-Content -LiteralPath (Join-Path $tooling "claude.version") -Value $version -Encoding UTF8
  # 최소값은 정식 X.Y.Z 릴리스. 빌드 메타데이터는 비교하지 않는다.
  $core = '(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)'
  $actual = [regex]::Match($version, '\A' + $core + '(?:-([0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?(?: \(Claude Code\))?\z')
  $floor = [regex]::Match($minimum, '\A' + $core + '\z')
  if (-not $actual.Success -or -not $floor.Success) { throw "Claude Code semver 형식 확인 불가" }
  $pre = $actual.Groups[4].Value
  foreach ($part in $pre.Split('.')) {
    if ($part -cmatch '^0[0-9]+$') { throw "Claude Code semver 형식 확인 불가" }
  }
  $comparison = 0
  for ($i = 1; $i -le 3; $i++) {
    $a = $actual.Groups[$i].Value
    $b = $floor.Groups[$i].Value
    $comparison = $a.Length.CompareTo($b.Length)
    if ($comparison -eq 0) { $comparison = [string]::CompareOrdinal($a, $b) }
    if ($comparison -ne 0) { break }
  }
  if ($comparison -lt 0 -or ($comparison -eq 0 -and $pre)) {
    & claude update
    if ($LASTEXITCODE -ne 0) { throw 'Claude Code 업데이트 실패' }
    $version = (& claude --version 2>$null | Out-String).Trim()
    $actual = [regex]::Match($version, '\A' + $core + '(?:-([0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?(?: \(Claude Code\))?\z')
    if (-not $actual.Success -or [version]($actual.Groups[1].Value + '.' + $actual.Groups[2].Value + '.' + $actual.Groups[3].Value) -lt [version]$minimum -or $actual.Groups[4].Value) {
      throw "중단: claude update 후에도 $minimum 미만입니다($version). PowerShell에서 claude update를 직접 실행한 뒤 다시 시도하세요."
    }
    Set-Content -LiteralPath (Join-Path $tooling 'claude.version') -Value $version -Encoding UTF8
  }
  $script:StepObserved = [ordered]@{ claude_version = $version }
}

function Run-S02 {
  & claude auth status *> $null
  if ($LASTEXITCODE -ne 0) {
    & claude auth login
    if ($LASTEXITCODE -ne 0) { throw 'Claude 로그인 실패' }
    & claude auth status *> $null
    if ($LASTEXITCODE -ne 0) { throw 'Claude 로그인 재확인 실패' }
  }
  $auth = Join-Path $WaveHome "auth"
  New-Item -ItemType Directory -Force -Path $auth | Out-Null
  New-Item -ItemType File -Force -Path (Join-Path $auth "claude-authenticated") | Out-Null
  $script:StepObserved = [ordered]@{ authenticated = $true; account_recorded = $false }
}

function Run-S03 {
  Release-Context
  $downloads = Join-Path $WaveHome "downloads"
  New-Item -ItemType Directory -Force -Path $downloads | Out-Null
  $sums = Join-Path $downloads "SHA256SUMS"
  try {
    Invoke-WebRequest -UseBasicParsing -Uri $ReleaseAssetUrl -OutFile $ArtifactPath
    Invoke-WebRequest -UseBasicParsing -Uri $ReleaseSumsUrl -OutFile $sums
  } catch {
    if ($_.Exception.Message -match '(?i)virus|malware|defender|v3|알약|alyac|격리|보안.*차단') {
      throw "백신 차단 감지: Defender·V3·알약 알림의 파일명과 격리 조치를 확인하세요. $($_.Exception.Message)"
    }
    throw "W-DOWNLOAD-NET: $($_.Exception.Message)"
  }
  $lines = @(Get-Content -LiteralPath $sums | Where-Object { $_ -cmatch ('^[a-fA-F0-9]{64} [ *]' + [Regex]::Escape($ReleaseAssetName) + '$') })
  if ($lines.Count -ne 1) { throw 'SHA256 불일치: 자산의 정확한 행이 하나여야 합니다' }
  $expected = ($lines[0] -split '\s+')[0]
  $actual = Get-ArtifactHash $ArtifactPath
  if ((Get-Item -LiteralPath $ArtifactPath).Length -ne $WaveWinBytes) { throw 'Windows 설치 파일 바이트 불일치' }
  if ($expected.ToLowerInvariant() -ne $actual -or $WaveWinSha256 -ne $actual) { throw "SHA256 불일치" }
  $signature = Get-AuthenticodeSignature -LiteralPath $ArtifactPath
  if ($signature.Status -eq 'NotSigned') {
    Say 'SmartScreen에서 미서명 앱 경고가 나오면 게시자·파일명을 확인하세요. SHA256 검증은 통과했습니다.'
  } elseif ($signature.Status -ne 'Valid' -or -not $signature.SignerCertificate -or
      -not $ReleasePublisherSubject -or $signature.SignerCertificate.Subject -cne $ReleasePublisherSubject) {
    throw 'Authenticode 검증 실패: 서명 상태 또는 발급자 불일치'
  }
  $script:StepObserved = [ordered]@{ platform = $ReleasePlatform; asset = $ReleaseAssetName; sha256 = $actual; authenticode_checked = $true; signature_status = [string]$signature.Status }
}

function Run-S04 {
  Release-Context
  if (-not (Test-Path -LiteralPath $ArtifactPath -PathType Leaf)) { throw "검증된 artifact 없음" }
  # Resume도 S03 뒤의 파일 변조를 놓치지 않는다. 공개 steps.json의 고정 해시와 다시 대조한다.
  $actual = (Get-FileHash -LiteralPath $ArtifactPath -Algorithm SHA256).Hash.ToLowerInvariant()
  if ($actual -ne $ReleaseExpectedSha256) { throw "W-ARTIFACT-CHANGED: 설치 직전 SHA256 불일치" }
  if ((Get-Item -LiteralPath $ArtifactPath).Length -ne $WaveWinBytes) { throw 'Windows 설치 파일 바이트 불일치' }
  if ($ArtifactPath -notlike "*-windows-x64-setup.exe") { throw "W-NSIS-ASSET: Windows NSIS 설치 파일이 아님" }
  $webMark = Clear-WebMark $ArtifactPath $ReleaseExpectedSha256
  $bin = Join-Path $WaveHome "bin"
  Assert-UserPath $bin
  New-Item -ItemType Directory -Force -Path $bin | Out-Null
  # NSIS /D는 공백이 있어도 따옴표 없이 마지막 인자여야 한다.
  # 정본: https://nsis.sourceforge.io/Docs/Chapter3.html#installerusage
  $process = Start-Process -FilePath $ArtifactPath -ArgumentList "/S /D=$bin" -Wait -PassThru
  if ($process.ExitCode -ne 0) { throw "W-NSIS-EXIT: 설치기 종료값 $($process.ExitCode)" }
  $cys = Join-Path $bin "cys.exe"
  $cysd = Join-Path $bin "cysd.exe"
  if (-not (Test-Path -LiteralPath $cys -PathType Leaf) -or -not (Test-Path -LiteralPath $cysd -PathType Leaf)) { throw "S2 설치 산출물의 cys/cysd 경로가 없음" }
  $cliVersion = (& $cys --version 2>&1 | Out-String).Trim()
  if ($LASTEXITCODE -ne 0 -or -not $cliVersion) { throw "cys 실행 확인 실패" }
  # cysd에는 --version 계약이 없다. 여기서 실행하면 데몬이 기동되어 설치기가 대기한다.
  # 서명·고정 해시가 검증된 NSIS의 설치 결과를 정적 검사하고 실제 기동은 러너의 별도 스모크로 검증한다.
  $daemonFile = [IO.File]::OpenRead($cysd)
  try {
    $reader = [IO.BinaryReader]::new($daemonFile)
    if ($daemonFile.Length -lt 256 -or $reader.ReadUInt16() -ne 0x5A4D) { throw "W-CYSD-PE: 데몬 실행파일 헤더 오류" }
    $daemonFile.Position = 60
    $offset = $reader.ReadUInt32()
    if ($offset -gt ($daemonFile.Length - 6)) { throw "W-CYSD-PE: 헤더 범위 오류" }
    $daemonFile.Position = $offset
    if ($reader.ReadUInt32() -ne 0x00004550 -or $reader.ReadUInt16() -ne 0x8664) { throw "W-CYSD-PE: Windows x64 데몬이 아님" }
  } finally { $daemonFile.Dispose() }
  $daemonSha = (Get-FileHash -LiteralPath $cysd -Algorithm SHA256).Hash.ToLowerInvariant()
  # 이 설치 프로세스와 이어서 기동하는 자식에만 적용한다. 사용자 전역 PATH 변경으로 과장하지 않는다.
  $env:PATH = $bin + [IO.Path]::PathSeparator + $env:PATH
  $resolved = Get-Command cys.exe -CommandType Application -ErrorAction Stop | Select-Object -First 1
  if ([IO.Path]::GetFullPath($resolved.Source) -ne [IO.Path]::GetFullPath($cys)) { throw "cys 셸 경로 불일치" }
  $script:StepObserved = [ordered]@{ cys = $true; cys_version_observed = $cliVersion; cysd = $true; shell_link = $true; shell_scope = "process"; install_dir = $bin; installer_exit = $process.ExitCode; verified_installer_sha256 = $actual; web_mark = $webMark; cli_sha256 = (Get-ArtifactHash $cys); daemon_sha256 = $daemonSha; daemon_verification = "PE-x64-and-observed-SHA256"; daemon_started = $false; admin_required = $false }
}

# 앱 CLI 계약을 사용한다. 설치 흐름 기반: oogisoogi/jarvis-install (MIT).
function Test-DaemonReady {
  $cys = Join-Path $WaveHome 'bin\cys.exe'
  for ($attempt = 0; $attempt -lt 5; $attempt++) {
    try {
      $ping = Invoke-BoundedCheck $cys @('ping') "daemon-ping-$attempt" 3000
      if (-not $ping.timed_out -and $ping.exit_code -eq 0 -and $ping.stdout.Trim() -eq 'pong') { return $true }
    } catch { Write-Log $_.Exception.Message }
    Start-Sleep -Milliseconds 500
  }
  return $false
}

function Start-WaveApp {
  $app = Join-Path $WaveHome 'bin\cys-app.exe'
  if (-not (Test-Path -LiteralPath $app -PathType Leaf)) { throw 'cys-app.exe 없음' }
  Start-Process -FilePath $app | Out-Null
}

function Run-S05 {
  $cys = Join-Path $WaveHome 'bin\cys.exe'
  $registered = $false
  try {
    $install = Invoke-BoundedCheck $cys @('daemon', 'install') 'daemon-install' 30000
    $registered = (-not $install.timed_out -and $install.exit_code -eq 0)
    if (-not $registered) { Write-Log "daemon install 미완료: $($install.stderr)" }
  } catch { Write-Log "daemon install 실패: $($_.Exception.Message)" }
  $ready = Test-DaemonReady
  $fallback = $false
  if (-not $ready) {
    $fallback = $true
    try { Start-Process -FilePath (Join-Path $WaveHome 'bin\cysd.exe') | Out-Null } catch { Write-Log $_.Exception.Message }
    $ready = Test-DaemonReady
    if (-not $ready) {
      try { Start-WaveApp } catch { Write-Log $_.Exception.Message }
      $ready = Test-DaemonReady
    }
  }
  $script:StepObserved = [ordered]@{ registered = $registered; daemon_ready = $ready; direct_fallback = $fallback; registration = 'cys daemon install' }
  if (-not $registered -or -not $ready) { $script:StepStatus = 'skipped_with_reason' }
}

function Run-S06 {
  $priorPackDir = $env:CYS_PACK_DIR
  try {
  $env:CYS_PACK_DIR = $PackHome
  foreach ($candidate in @($PackHome, (Join-Path $PackHome 'directives'))) {
    if (Test-Path -LiteralPath $candidate) {
      if (((Get-Item -LiteralPath $candidate -Force).Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) { throw '팩/지침 경로의 reparse point 거부' }
    }
  }
  $cys = Join-Path $WaveHome 'bin\cys.exe'
  $legacy = Join-Path $ScriptDir 'wave-pack\directives'
  $backup = Join-Path $WaveHome ('backups\legacy-directives-' + [guid]::NewGuid().ToString('N'))
  $moved = @()
  # 배포 스텁과 내용이 정확히 같은 파일만 이동한다. 사용자 수정본은 보존한다.
  foreach ($stub in @(Get-ChildItem -LiteralPath $legacy -File -ErrorAction Stop)) {
    $target = Join-Path $PackHome ('directives\' + $stub.Name)
    if ((Test-Path -LiteralPath $target) -and (((Get-Item -LiteralPath $target -Force).Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0)) { throw '지침 reparse point 거부' }
    if ((Test-Path -LiteralPath $target -PathType Leaf) -and (Get-ArtifactHash $target) -eq (Get-ArtifactHash $stub.FullName)) {
      New-Item -ItemType Directory -Force -Path $backup | Out-Null
      Move-Item -LiteralPath $target -Destination (Join-Path $backup $stub.Name)
      if (Test-Path -LiteralPath ($target + '.new')) {
        Move-Item -LiteralPath ($target + '.new') -Destination (Join-Path $backup ($stub.Name + '.new'))
      }
      $moved += $stub.Name
    }
  }
  $result = Invoke-BoundedCheck $cys @('init-pack') 'init-pack' 120000
  if ($result.timed_out -or $result.exit_code -ne 0) { throw "init-pack 실패: $($result.stderr)" }
  $manifestResult = Invoke-BoundedCheck $cys @('pack-manifest') 'pack-manifest' 30000
  if ($manifestResult.timed_out -or $manifestResult.exit_code -ne 0) { throw '앱 원본 pack-manifest 조회 실패' }
  $manifest = $manifestResult.stdout | ConvertFrom-Json
  $directives = @($manifest.files.PSObject.Properties | Where-Object { $_.Name -like 'directives/*' })
  if ($directives.Count -eq 0) { throw '앱 manifest 지침 목록 없음' }
  $mismatches = @()
  foreach ($file in $directives) {
    if ($file.Name -match '(^|/)\.\.(/|$)|:|\\' -or $file.Value -notmatch '^[a-fA-F0-9]{64}$') { throw '앱 manifest 지침 경로/지문 오류' }
    $target = Join-Path $PackHome $file.Name
    if (-not (Test-Path -LiteralPath $target -PathType Leaf) -or (Get-ArtifactHash $target) -ne $file.Value.ToLowerInvariant()) { $mismatches += $file.Name }
  }
  # preflight-product-profile.json 은 앱이 한 번만 심는 사용자 소유 파일이다(없을 때만 쓰고 덮지 않음). 사용자가
  # 고치거나 되돌린 상태는 정상이므로 그 병치본(.new)은 설치를 막지 않고 두 파일 모두 손대지 않는다. 그 밖의 .new 는 병합 대기다.
  $seedOnceNew = Join-Path $PackHome 'preflight-product-profile.json.new'
  $pending = @(Get-ChildItem -LiteralPath $PackHome -Filter '*.new' -Recurse -File -ErrorAction Stop | Where-Object { $_.FullName -ne $seedOnceNew })
  $script:StepObserved = [ordered]@{ pack_installed = $true; legacy_backed_up = $moved; directive_count = $directives.Count; directive_mismatches = $mismatches; new_files = $pending.Count; directive_bytes_match = ($mismatches.Count -eq 0) }
  if ($mismatches.Count -or $pending.Count) { throw "원본 지침 대조 실패: mismatch=$($mismatches.Count), .new=$($pending.Count); 사용자 파일은 보존했습니다" }
  } finally { $env:CYS_PACK_DIR = $priorPackDir }
}

function Get-LiveFleet([int]$TimeoutMs = 5000) {
  if ($TimeoutMs -le 0) { throw '각성 확인 시간 초과' }
  $result = Invoke-BoundedCheck (Join-Path $WaveHome 'bin\cys.exe') @('status', '--json') 'fleet-status' $TimeoutMs
  if ($result.timed_out -or $result.exit_code -ne 0) { throw '초기 편성 상태 조회 실패' }
  return ($result.stdout | ConvertFrom-Json)
}

function Test-AwakenedFleet([object]$Status) {
  $live = @($Status.surfaces | Where-Object { $_.exited -eq $false -and $_.agent_alive -eq $true })
  $master = @($live | Where-Object { $_.role -eq 'master' -and $_.directive_verified -eq $true -and $null -ne $_.awakened_at })
  $children = @($live | Where-Object { $_.role -like 'worker*' -and $_.directive_verified -eq $true -and $null -ne $_.awakened_at })
  $cso = @($live | Where-Object { $_.role -eq 'cso' -and $_.directive_verified -eq $true -and $null -ne $_.awakened_at })
  if ($master.Count -lt 1 -or $children.Count -lt 1 -or $cso.Count -lt 1) { return $false }
  $markerPath = Join-Path $env:USERPROFILE '.cys\.master-bootstrapped'
  if (-not (Test-Path -LiteralPath $markerPath -PathType Leaf)) { return $false }
  if ($null -ne $script:AwakeningStartedAt -and (Get-Item -LiteralPath $markerPath -Force).LastWriteTimeUtc -lt $script:AwakeningStartedAt) { return $false }
  try { $marker = Get-Content -LiteralPath $markerPath -Raw | ConvertFrom-Json } catch { return $false }
  return ($marker.orchestra_check -eq 'exit 0' -and @($master.surface_ref) -contains $marker.surface_ref)
}

function Get-AwakeningBudgetMs([long]$ElapsedMs, [int]$LimitMs = 5000) {
  $remaining = 420000L - $ElapsedMs
  if ($remaining -le 0) { return 0 }
  return [int][Math]::Min($LimitMs, $remaining)
}

function Run-S07 {
  $clock = [Diagnostics.Stopwatch]::StartNew()
  Start-WaveApp
  $status = Get-LiveFleet (Get-AwakeningBudgetMs $clock.ElapsedMilliseconds)
  if (-not (Test-AwakenedFleet $status)) {
    $masters = @($status.surfaces | Where-Object { $_.role -eq 'master' -and $_.exited -eq $false })
    if ($masters.Count -eq 0) {
      $script:AwakeningStartedAt = [DateTime]::UtcNow
      # oogisoogi/jarvis-install write_wake_file/step_wake (MIT): 프롬프트는 UTF-8 파일로 전달.
      $wakePath = Join-Path $WaveHome 'wake-master.ps1'
      $wakeBody = @'
$ErrorActionPreference = 'Stop'
& claude "너는 마스터다`n설치된 팩의 마스터 부트 절차를 수행해 주세요. CSO와 작업 워커를 각각 한 좌석씩 소환해 마스터를 포함한 세 좌석의 각성을 확인해 주세요. 리뷰어는 기다리지 마세요."
exit $LASTEXITCODE
'@
      Set-Content -LiteralPath $wakePath -Value $wakeBody -Encoding UTF8
      $command = 'powershell.exe -NoProfile -ExecutionPolicy Bypass -File "' + $wakePath + '"'
      $quotedCommand = '"' + $command.Replace('"', '\"') + '"'
      $created = Invoke-BoundedCheck (Join-Path $WaveHome 'bin\cys.exe') @('new-surface', '--role', 'master', '--cmd', $quotedCommand) 'master-create' (Get-AwakeningBudgetMs $clock.ElapsedMilliseconds 15000)
      if ($created.timed_out -or $created.exit_code -ne 0) { throw '마스터 좌석 생성 실패' }
    }
  }
  while ((Get-AwakeningBudgetMs $clock.ElapsedMilliseconds) -gt 0) {
    $status = Get-LiveFleet (Get-AwakeningBudgetMs $clock.ElapsedMilliseconds)
    if ((Get-AwakeningBudgetMs $clock.ElapsedMilliseconds) -le 0) { break }
    if (Test-AwakenedFleet $status) {
      $script:StepObserved = [ordered]@{ fleet_started = $true; master_awakened = $true; child_alive = $true; cso_alive = $true; seats = 3; roles = @('master','cso','worker'); source = 'cys status --json' }
      return
    }
    $sleepMs = Get-AwakeningBudgetMs $clock.ElapsedMilliseconds
    if ($sleepMs -gt 0) { Start-Sleep -Milliseconds $sleepMs }
  }
  $script:StepObserved = [ordered]@{ fleet_started = $false; master_awakened = $false; source = 'cys status --json'; reason = 'awakening_timeout' }
  throw '마스터·CSO·워커 각성 확인 420초 시간 초과'
}

function Get-StateField([object]$Object, [string]$Name) {
  if ($null -eq $Object) { return $null }
  if ($Object -is [Collections.IDictionary]) { return $Object[$Name] }
  $property = $Object.PSObject.Properties[$Name]
  if ($null -ne $property) { return $property.Value }
  return $null
}

function Test-ByteCount([object]$Value) {
  return (($Value -is [int] -or $Value -is [long]) -and $Value -ge 0)
}

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

function Invoke-BoundedCheck([string]$FilePath, [string[]]$Arguments, [string]$Name, [int]$TimeoutMs = 30000) {
  if ($TimeoutMs -le 0) { throw '명령 실행 제한시간 소진' }
  $checkClock = [Diagnostics.Stopwatch]::StartNew()
  $verify = Join-Path $WaveHome 'verify'
  New-Item -ItemType Directory -Force -Path $verify | Out-Null
  $stdoutPath = Join-Path $verify ($Name + '.stdout.log')
  $stderrPath = Join-Path $verify ($Name + '.stderr.log')
  $process = Start-Process -FilePath $FilePath -ArgumentList $Arguments -NoNewWindow -PassThru -RedirectStandardOutput $stdoutPath -RedirectStandardError $stderrPath
  $exitCode = $null
  $killError = $null
  try {
    $null = $process.Handle
    $finished = $process.WaitForExit([int][Math]::Max(0, $TimeoutMs - $checkClock.ElapsedMilliseconds))
    if ($finished) {
      $exitCode = $process.ExitCode
    } else {
      try { if (-not $process.HasExited) { $process.Kill() } }
      catch { if (-not $process.HasExited) { $killError = $_.Exception.Message } }
    }
    # Keep the final wait bounded: descendants may retain redirected handles.
    $cleanupMs = [int][Math]::Min(1000, [Math]::Max(0, $TimeoutMs - $checkClock.ElapsedMilliseconds))
    if (-not $process.WaitForExit($cleanupMs) -and -not $killError) { $killError = 'Client exit was not confirmed within 1000ms' }
  } finally { $process.Dispose() }
  # Read errors propagate to Run-S08's unmeasured boundary, never an empty success.
  $stdout = Read-SharedCheckLog $stdoutPath
  $stderr = Read-SharedCheckLog $stderrPath
  return [pscustomobject]@{ timed_out = (-not $finished); timeout_ms = $TimeoutMs; exit_code = $exitCode; stdout = $stdout; stderr = $stderr; kill_error = $killError }
}

function Set-S08Timeout([string]$Command, [int]$TimeoutMs, [string]$KillError = '') {
  $script:StepStatus = 'unmeasured'
  $script:StepObserved = [ordered]@{ reason = 'timeout'; timed_out_command = $Command; timeout_ms = $TimeoutMs; identify_exit = $null; seats = $null; original_match = $null; new_file_count = $null; kill_error = $KillError }
  Say "S08 $Command 시간 제한 ${TimeoutMs}ms 초과 — unmeasured로 기록하고 S09로 진행합니다."
}

function Set-S08CallFailure([string]$Command, $ExitCode, [string]$Detail) {
  $script:StepStatus = 'unmeasured'
  $script:StepObserved = [ordered]@{ reason = 'call_failed'; command = $Command; command_exit = $ExitCode; detail = $Detail; identify_exit = $null; seats = $null; original_match = $null; new_file_count = $null }
  Say "S08 $Command 확인 실패 — unmeasured로 기록하고 S09로 진행합니다: $Detail"
}

function Test-OriginalInjection {
  foreach ($directory in @($PackHome, (Join-Path $PackHome 'directives'))) {
    if ((Get-Item -LiteralPath $directory -Force -ErrorAction Stop).Attributes -band [IO.FileAttributes]::ReparsePoint) { throw 'G3 linked pack refused' }
  }
  $result = Invoke-BoundedCheck (Join-Path $WaveHome 'bin\cys.exe') @('pack-manifest') 'g3-pack-manifest' 30000
  if ($result.timed_out -or $result.exit_code -ne 0) { throw 'G3 앱 원본 manifest 조회 실패' }
  $manifest = $result.stdout | ConvertFrom-Json
  $files = Get-StateField $manifest 'files'
  foreach ($role in @('MASTER','CSO','WORKER')) {
    if ($null -eq (Get-StateField $files ('directives/'+$role+'_DIRECTIVE.md'))) { throw 'G3 manifest missing required directives' }
  }
  $verified = [ordered]@{}
  foreach ($entry in $files.PSObject.Properties) {
    $rel = $entry.Name
    if (-not ($rel.StartsWith('directives/') -and $rel.EndsWith('.md'))) { continue }
    if ($rel.Split('/') -contains '..' -or $rel.Contains('\')) { throw 'G3 invalid directive path' }
    $target = Join-Path $PackHome $rel
    $file = Get-Item -LiteralPath $target -Force -ErrorAction Stop
    if ($file.PSIsContainer -or ($file.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0 -or $file.Length -le 0 -or (Get-ArtifactHash $target) -cne $entry.Value) { throw "G3 installed original mismatch: $rel" }
    $verified[$rel] = [ordered]@{ pack_sha256 = $entry.Value; pack_bytes = $file.Length }
  }
  # S06 과 같은 예외: 사용자 소유 제품 프로필의 병치본만 제외한다.
  $seedOnceNew = Join-Path $PackHome 'preflight-product-profile.json.new'
  $pending = @(Get-ChildItem -LiteralPath $PackHome -Filter '*.new' -Recurse -Force -ErrorAction Stop | Where-Object { $_.FullName -ne $seedOnceNew })
  if ($pending.Count -ne 0) { throw "G3 병합 대기 .new 파일 $($pending.Count)건" }
  return [ordered]@{ original_match = $true; new_file_count = 0; roles = $verified; injected_bytes = $null; injection_reason = 'RC 러너 G3_inject.json 판정'; source = 'app-manifest+installed-pack' }
}

function Run-S08 {
  $cys = Join-Path $WaveHome 'bin\cys.exe'
  try { $identify = Invoke-BoundedCheck $cys @('identify') 'identify' 30000 }
  catch { Set-S08CallFailure 'cys identify' $null $_.Exception.Message; return }
  if ($identify.timed_out) { Set-S08Timeout 'cys identify' $identify.timeout_ms $identify.kill_error; return }
  if ($identify.exit_code -ne 0) { Set-S08CallFailure 'cys identify' $identify.exit_code $identify.stderr; return }
  try { $result = Invoke-BoundedCheck $cys @('status', '--json') 'fleet-status' 5000 }
  catch { Set-S08CallFailure 'cys status --json' $null $_.Exception.Message; return }
  if ($result.timed_out) { Set-S08Timeout 'cys status --json' $result.timeout_ms $result.kill_error; return }
  if ($result.exit_code -ne 0) { Set-S08CallFailure 'cys status --json' $result.exit_code $result.stderr; return }
  try {
    $status = $result.stdout | ConvertFrom-Json
    $verify = Join-Path $WaveHome 'verify'
    New-Item -ItemType Directory -Force -Path $verify | Out-Null
    Set-Content -LiteralPath (Join-Path $verify 'status.json') -Value ($status | ConvertTo-Json -Depth 20) -Encoding UTF8
    if (-not (Test-AwakenedFleet $status)) { throw '마스터·CSO·worker 각성 증거 없음' }
  } catch { Set-S08CallFailure 'cys status --json' $null $_.Exception.Message; return }
  try { $evidence = Test-OriginalInjection }
  catch {
    $script:StepObserved = [ordered]@{ original_match = $false; new_file_count = $null; source = 'app-manifest+installed-pack'; reason = $_.Exception.Message }
    throw
  }
  $script:StepObserved = $evidence
  $script:StepObserved['identify_exit'] = 0
  $script:StepObserved['fleet_verified'] = $true
}

function Test-SyntheticBypass([object]$Value) {
  if ($null -eq $Value) { return $false }
  if ($Value -is [string]) { return $Value -ceq "TEST_SYNTHETIC_BYPASS" }
  if ($Value -is [Collections.IDictionary]) {
    if ($Value["TEST_SYNTHETIC_BYPASS"]) { return $true }
    foreach ($item in $Value.Values) { if (Test-SyntheticBypass $item) { return $true } }
  } elseif ($Value -is [System.Management.Automation.PSCustomObject]) {
    if (Get-StateField $Value "TEST_SYNTHETIC_BYPASS") { return $true }
    foreach ($property in $Value.PSObject.Properties) { if (Test-SyntheticBypass $property.Value) { return $true } }
  } elseif ($Value -is [Collections.IEnumerable]) {
    foreach ($item in $Value) { if (Test-SyntheticBypass $item) { return $true } }
  }
  return $false
}

function Summarize-State([bool]$Final) {
  $exceptions = @()
  foreach ($property in $State.PSObject.Properties) {
    if ($property.Name -in @("steps", "exceptions")) { continue }
    if (($property.Name -eq "TEST_SYNTHETIC_BYPASS" -and $property.Value) -or (Test-SyntheticBypass $property.Value)) {
      $exceptions += [ordered]@{ step_id = $null; reason = "TEST_SYNTHETIC_BYPASS" }
      break
    }
  }
  foreach ($step in $Config.steps) {
    if (-not $Final -and $step.index -ge 9) { continue }
    $entry = Get-StateField $State.steps $step.id
    $reasons = @()
    if ($null -eq $entry) { $reasons += "missing_step" } else {
      if (Get-StateField $entry "error_id") {
        $reasons += "error_id"
        if ((Get-StateField $entry "status") -eq "passed") { $entry.status = "failed" }
      }
      $status = Get-StateField $entry "status"
      if ($status -ne "passed") { $reasons += "status:$status" }
      $exitCode = Get-StateField $entry "exit_code"
      if (-not (Test-ByteCount $exitCode) -or $exitCode -ne 0) { $reasons += "exit_code" }
      if (Test-SyntheticBypass $entry) { $reasons += "TEST_SYNTHETIC_BYPASS" }
      $observed = Get-StateField $entry "observed"
      $fleet = Get-StateField $observed "fleet_started"
      if ($step.id -eq "S07_INITIAL_FLEET" -and ($fleet -isnot [bool] -or -not $fleet)) { $reasons += "fleet_unmeasured" }
      if ($step.id -eq "S08_VERIFY") {
        $original = Get-StateField $observed 'original_match'
        $newCount = Get-StateField $observed 'new_file_count'
        if ($original -isnot [bool] -or -not $original) { $reasons += 'original_injection_unverified' }
        if (-not (Test-ByteCount $newCount) -or $newCount -ne 0) { $reasons += 'pending_new_unverified' }
      }
    }
    foreach ($reason in $reasons) { $exceptions += [ordered]@{ step_id = $step.id; reason = $reason } }
  }
  $State.required_steps_passed = $exceptions.Count -eq 0
  $State | Add-Member -NotePropertyName exceptions -NotePropertyValue @($exceptions) -Force
  $State.updated_at = Now-Utc
  if ($Final) {
    $State.status = if ($exceptions.Count) { "complete_with_exceptions" } else { "complete" }
    $State.current_step = $null
  }
  Save-State
}

function Mark-RequiredComplete {
  Summarize-State $false
}

function Run-S09 {
  $start = Join-Path $WaveHome "START-HERE.md"
  $message = if ($State.required_steps_passed) { "필수 단계 검증을 통과했습니다." } else { "설치 절차를 마무리했습니다. 예외·미검증 항목이 있으므로 전체 검증 완료가 아닙니다." }
  @("# Wave Terminal 시작하기", "", $message, "", "install-state.json의 required_steps_passed·exceptions와 install.log를 확인하세요. 주입 원본 대조 영수증이 없거나 병합 대기 파일이 있으면 검증 완료가 아닙니다.") | Set-Content -LiteralPath $start -Encoding UTF8
  if (-not (Test-Path -LiteralPath $start)) { throw "START-HERE 없음" }
  $script:StepObserved = [ordered]@{ required_steps_passed = $State.required_steps_passed; start_here = $true; silent_completion = $false }
}

function Invoke-Step([string]$Id, [scriptblock]$Action) {
  $script:StepObserved = [ordered]@{}
  $script:StepStatus = "passed"
  $script:DiagnosticWritten = $false
  try {
    Send-Progress $CurrentStep 'start'
    Update-Step $Id "running" 0 "" ([ordered]@{})
    & $Action
    Update-Step $Id $StepStatus 0 "" $StepObserved
    Send-Progress $CurrentStep 'end'
  } catch {
    $reason = $_.Exception.Message
    $position = $_.InvocationInfo.PositionMessage
    $code = Get-JCode $reason
    $script:StepObserved['j_code'] = $code
    $script:StepObserved['reason'] = $reason
    $script:StepObserved['position'] = $position
    try {
      Write-Log "[$Id] 실패 원문: $reason"
      if ($position) { Write-Log $position }
    } catch { Write-Host "[$Id] 실패 원문: $reason`n$position" }
    Write-JCode $code
    $step = $Config.steps | Where-Object { $_.id -eq $Id }
    $errorId = [string]$step.on_fail.error_id
    if ($step.optional -eq $true) {
      Update-Step $Id "skipped_with_reason" 1 $errorId $StepObserved
      Say "[$CurrentStep] 선택 단계 실패 — 이유를 기록하고 계속 진행합니다."
      return
    }
    Update-Step $Id "failed" 1 $errorId $StepObserved
    throw
  }
}

# 최종 막힘 도움 요청. 고지 전·lib 없음·WAVE_NO_PROGRESS=1 이면 아무것도 하지 않는다. 결과와 무관하게 종료값은 호출자가 정한다.
function Invoke-FinalHelp {
  if (-not $script:HelpNoticeShown -or -not (Get-Command Send-HelpRequest -ErrorAction SilentlyContinue)) { return }
  $tail = ''
  try { if (Test-Path -LiteralPath $LogFile) { $tail = @(Get-Content -LiteralPath $LogFile -Tail 40 -Encoding UTF8) -join "`n" } } catch { }
  $stateText = ''
  try { if (Test-Path -LiteralPath $StateFile) { $stateText = Get-Content -LiteralPath $StateFile -Raw -Encoding UTF8 } } catch { }
  $envReport = @('os=win', ('installer_version=' + (Get-InstallerVersion)), ('step=' + $CurrentStep),
    ('platform=' + [Environment]::OSVersion.VersionString), ('machine=' + $env:PROCESSOR_ARCHITECTURE),
    ('powershell=' + $PSVersionTable.PSVersion), 'install-state.json:', $stateText) -join "`n"
  $null = Send-HelpRequest -BaseUrl (Get-HelpBaseUrl) -InstallId (Get-WaveInstallId) -Version (Get-InstallerVersion) -Step $CurrentStep -Code $LastJCode -EnvReport $envReport -LogTail $tail -Interactive $HelpInteractive -Username ([string]$env:USERNAME)
}

function Complete-State {
  Summarize-State $true
  Save-InstallDone
}

trap {
  $failure = $_
  if (-not $DiagnosticWritten) { Write-JCode (Get-JCode $failure.Exception.Message) }
  try {
    Write-Log $failure.Exception.Message
    if ($failure.InvocationInfo.PositionMessage) { Write-Log $failure.InvocationInfo.PositionMessage }
  } catch { Write-Host $failure.Exception.Message; Write-Host $failure.InvocationInfo.PositionMessage }
  try { Invoke-FinalHelp } catch { }
  exit 1
}

Load-Config
if ($DryRun) {
  Write-Host "dry-run: $StepsFile / $StateFile / $LogFile"
  exit 0
}
Assert-UserPath $WaveHome
if (Test-RecentInstallDone) {
  Say '[10/10] 이미 끝나 있습니다 — 10분 이내 같은 릴리스 재실행입니다.'
  exit 0
}
if ($env:WAVE_NO_PROGRESS -ne '1' -and (Get-Command Show-HelpNotice -ErrorAction SilentlyContinue)) {
  $HelpInteractive = [Environment]::UserInteractive -and -not [Console]::IsInputRedirected -and -not [Console]::IsOutputRedirected -and -not ([Environment]::GetCommandLineArgs() -contains '-NonInteractive')
  Show-HelpNotice
}
Init-State
if (Test-Path -LiteralPath $InstallDoneFile) { Remove-Item -LiteralPath $InstallDoneFile -Force }
if (@($State.steps.PSObject.Properties | Where-Object { $_.Value.status -eq 'running' }).Count -gt 0) {
  Write-JCode 'J-AV-03'
  Say '완료한 단계는 건너뛰고 이어갑니다. 이전 중단 원인은 기록을 확인하세요.'
}
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
foreach ($step in ($Config.steps | Sort-Object index)) {
  $id = [string]$step.id
  if (Test-StepComplete $id) { Say-Step $step '이미 완료 — 건너뜀'; Send-Progress $CurrentStep 'end'; continue }
  if ($id -eq "S09_COMPLETE") { Mark-RequiredComplete }
  Say-Step $step '시작'
  Invoke-Step $id $actions[$id]
}
Complete-State
Say "[10/10] Wave Terminal 설치 상태 $($State.status) — START-HERE와 exceptions를 확인하세요."
