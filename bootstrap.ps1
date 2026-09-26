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

# 이 설치 도우미는 oogisoogi/jarvis-install(MIT)을 바탕으로 구현했습니다.
# 원작 cys-terminal: idoforgod (MIT). LICENSES/jarvis-install-MIT.txt 참조.
# Windows 릴리스 판올림 때 바꾸는 핀 3값. s746 수정 draft 검체(2026-09-22).
$WaveVersion = '0.1.0'
$WaveWinBytes = 128814816
$WaveWinSha256 = '733a595c1270d62e9ca83e82cda143d8ec223985b857f648939541d20ba12fc3'
$WaveWinFile = "wave-terminal-${WaveVersion}-windows-x64-setup.exe"
$InstallDoneFile = Join-Path $WaveHome 'install-done.txt'
$RerunDoneWindowSec = 600
$ProgressUrl = 'https://waveainetworks.com/api/progress'
$ProgressTimeoutSec = 3
$InstallId = ''
$ProgressWarned = $false
$CurrentStep = '1/10'
$DiagnosticWritten = $false

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
  # Reporting must still run when local logging fails (disk/permission errors).
  try {
    Say "진단 코드: $Code — $($rule.symptom)"
    Say $rule.action1
    Say $rule.action2
    Say "도움말: https://github.com/greatson79/wave-install/blob/main/docs/help-codes.md#$($Code.ToLowerInvariant())"
  } catch { Write-Host "진단 코드: $Code — $($rule.symptom)" }
  Send-Progress $CurrentStep 'fail' $null $Code
}

function Send-Progress([string]$Step, [string]$Event, $Elapsed = $null, [string]$Detail = '') {
  if ($DryRun -or $env:WAVE_NO_PROGRESS -eq '1') { return }
  try {
    $url = if ($env:WAVE_PROGRESS_URL) { $env:WAVE_PROGRESS_URL } else { $ProgressUrl }
    $uri = [uri]$url
    if ($uri.Scheme -ne 'https' -or $uri.AbsolutePath -ne '/api/progress') { throw 'invalid progress endpoint' }
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
    $fields = [ordered]@{
      install_id = $InstallId
      installer_version = '0.1.3'
      os = 'win'
      step = $Step
      event = $Event
      at = (Now-Utc)
    }
    if ($null -ne $Elapsed) { $fields.elapsed_s = [int]$Elapsed }
    # Only diagnostic codes leave the machine; never send raw exception text or accounts.
    if ($Detail -match '^J-[A-Z0-9]+-[0-9]{2}$') { $fields.detail = $Detail }
    $body = $fields | ConvertTo-Json -Compress
    $ProgressPreference = 'SilentlyContinue'
    [Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12
    $null = Invoke-WebRequest -Uri $uri -Method POST -Body ([Text.Encoding]::UTF8.GetBytes($body)) -ContentType 'application/json; charset=utf-8' -UseBasicParsing -TimeoutSec $ProgressTimeoutSec -ErrorAction Stop
  } catch {
    if (-not $script:ProgressWarned) {
      $script:ProgressWarned = $true
      try { Write-Log 'progress send failed (fail-open); 설치를 계속합니다.' } catch { }
    }
  }
}

function Get-ArtifactHash([string]$Path) {
  try { return (Get-FileHash -LiteralPath $Path -Algorithm SHA256 -ErrorAction Stop).Hash.ToLowerInvariant() }
  catch { throw 'W-HASH-READ: 지문을 잴 수 없습니다' }
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
  if ($Id -in @('S00_PREFLIGHT', 'S01_CLAUDE_INSTALL', 'S02_CLAUDE_LOGIN', 'S08_VERIFY')) { return $false }
  if ($Id -eq 'S03_DOWNLOAD_VERIFY') {
    try {
      Release-Context
      return ((Test-Path -LiteralPath $ArtifactPath -PathType Leaf) -and
        (Get-Item -LiteralPath $ArtifactPath).Length -eq $WaveWinBytes -and
        (Get-ArtifactHash $ArtifactPath) -eq $WaveWinSha256 -and
        (Get-StateField $entry.observed 'minisig_verified') -eq $true)
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
  if ($State.status -ne 'complete' -or -not $State.required_steps_passed) {
    if (Test-Path -LiteralPath $InstallDoneFile) { Remove-Item -LiteralPath $InstallDoneFile -Force }
    return
  }
  $mark = [ordered]@{
    version = $WaveVersion; bytes = $WaveWinBytes; sha256 = $WaveWinSha256
    state_sha256 = (Get-ArtifactHash $StateFile)
    config_sha256 = (Get-ArtifactHash $StepsFile)
  }
  $mark | ConvertTo-Json | Set-Content -LiteralPath $InstallDoneFile -Encoding UTF8
}

function Test-RecentInstallDone {
  if ($Reinstall -or -not (Test-Path -LiteralPath $InstallDoneFile -PathType Leaf)) { return $false }
  try {
    $age = ([DateTime]::UtcNow - (Get-Item -LiteralPath $InstallDoneFile).LastWriteTimeUtc).TotalSeconds
    if ($age -lt 0 -or $age -gt $RerunDoneWindowSec) { return $false }
    $mark = Get-Content -LiteralPath $InstallDoneFile -Raw -Encoding UTF8 | ConvertFrom-Json
    $previous = Get-Content -LiteralPath $StateFile -Raw -Encoding UTF8 | ConvertFrom-Json
    return ($previous.status -eq 'complete' -and $previous.required_steps_passed -eq $true -and
      $mark.version -ceq $WaveVersion -and $mark.bytes -eq $WaveWinBytes -and $mark.sha256 -ceq $WaveWinSha256 -and
      $mark.state_sha256 -ceq (Get-ArtifactHash $StateFile) -and $mark.config_sha256 -ceq (Get-ArtifactHash $StepsFile))
  } catch { return $false }
}

$HelpRulesJson = @'
[
  {
    "code": "J-AV-01",
    "symptom": "보안 제품이 실행을 차단함",
    "pattern": "(?i)virus|malware|바이러스|악성.*차단",
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
    "pattern": "SHA256 불일치|바이트 불일치|핀 불일치|minisign 검증 실패|W-NSIS-ASSET",
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
  if (-not [Environment]::Is64BitProcess) { throw '32비트 PowerShell에서는 실행할 수 없습니다' }
  $arch = $env:PROCESSOR_ARCHITECTURE.ToLowerInvariant()
  $platform = if ($arch -eq "amd64") { "windows_x64" } else { throw "지원하지 않는 Windows 아키텍처: $arch" }
  if ($WaveVersion -notmatch '^\d+\.\d+\.\d+$' -or $WaveWinBytes -le 0 -or $WaveWinSha256 -cnotmatch '^[a-f0-9]{64}$') { throw 'Windows 릴리스 핀 미확정' }
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
  if ($ReleaseVersion -cne $WaveVersion -or $ReleaseAssetName -cne $WaveWinFile -or $ReleaseExpectedSha256 -cne $WaveWinSha256) { throw 'Windows 릴리스 핀 불일치' }
  foreach ($url in @($ReleaseSumsUrl, $ReleaseMinisigUrl)) {
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
  if (-not (Get-Command claude -ErrorAction SilentlyContinue)) { throw "claude 명령 없음" }
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
    throw "중단: Claude Code $minimum 이상 필요. claude update로 업그레이드한 뒤 다시 실행하세요."
  }
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
  try {
    Invoke-WebRequest -UseBasicParsing -Uri $ReleaseAssetUrl -OutFile $ArtifactPath
    Invoke-WebRequest -UseBasicParsing -Uri $ReleaseSumsUrl -OutFile $sums
    Invoke-WebRequest -UseBasicParsing -Uri $ReleaseMinisigUrl -OutFile $sig
  } catch { throw "W-DOWNLOAD-NET: $($_.Exception.Message)" }
  $lines = @(Get-Content -LiteralPath $sums | Where-Object { $_ -cmatch ('^[a-fA-F0-9]{64} [ *]' + [Regex]::Escape($ReleaseAssetName) + '$') })
  if ($lines.Count -ne 1) { throw 'SHA256 불일치: 자산의 정확한 행이 하나여야 합니다' }
  $expected = ($lines[0] -split '\s+')[0]
  $actual = Get-ArtifactHash $ArtifactPath
  if ((Get-Item -LiteralPath $ArtifactPath).Length -ne $WaveWinBytes) { throw 'Windows 설치 파일 바이트 불일치' }
  if ($expected.ToLowerInvariant() -ne $actual -or $WaveWinSha256 -ne $actual) { throw "SHA256 불일치" }
  & minisign -Vm $ArtifactPath -P $ReleasePublicKey -x $sig *> $null
  if ($LASTEXITCODE -ne 0) { throw "minisign 검증 실패" }
  $script:StepObserved = [ordered]@{ platform = $ReleasePlatform; asset = $ReleaseAssetName; sha256 = $actual; minisig_verified = $true }
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
  $script:StepObserved = [ordered]@{ seats = 2; roles = "master+dept"; fleet_started = $null }
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
  if ($doctor.identify_exit -ne 0 -or @($doctor.seats).Count -ne 2) { throw "identify·좌석 수 계약 불일치" }
  $limit = [int64](Get-ConfigValue "tooling.max_injected_bytes_per_seat")
  $measured = $true
  $max = 0
  foreach ($seat in $doctor.seats) {
    $value = Get-StateField $seat "injected_bytes"
    if (-not (Test-ByteCount $value)) { $measured = $false; continue }
    if ($value -gt $limit) { throw "좌석당 지침 주입량 초과" }
    if ($value -gt $max) { $max = $value }
  }
  $script:StepObserved = [ordered]@{ identify_exit = 0; seats = 2; injection_measured = $measured; max_injected_bytes = $(if ($measured) { $max } else { $null }) }
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
        $measured = Get-StateField $observed "injection_measured"
        $value = Get-StateField $observed "max_injected_bytes"
        if ($measured -isnot [bool] -or -not $measured -or -not (Test-ByteCount $value)) { $reasons += "injection_unmeasured" }
        elseif ($value -gt $Config.tooling.max_injected_bytes_per_seat) { $reasons += "injection_limit_exceeded" }
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
  @("# Wave Terminal 시작하기", "", $message, "", "install-state.json의 required_steps_passed·exceptions와 install.log를 확인하세요. 주입량 미측정은 0바이트 통과를 뜻하지 않습니다.") | Set-Content -LiteralPath $start -Encoding UTF8
  if (-not (Test-Path -LiteralPath $start)) { throw "START-HERE 없음" }
  $script:StepObserved = [ordered]@{ required_steps_passed = $State.required_steps_passed; start_here = $true; silent_completion = $false }
}

function Invoke-Step([string]$Id, [scriptblock]$Action) {
  $script:StepObserved = [ordered]@{}
  $script:StepStatus = "passed"
  $script:DiagnosticWritten = $false
  Send-Progress $CurrentStep 'start'
  Update-Step $Id "running" 0 "" ([ordered]@{})
  try {
    & $Action
    Update-Step $Id $StepStatus 0 "" $StepObserved
    Send-Progress $CurrentStep 'end'
  } catch {
    $code = Get-JCode $_.Exception.Message
    $script:StepObserved['j_code'] = $code
    Write-JCode $code
    $errorId = [string](($Config.steps | Where-Object { $_.id -eq $Id }).on_fail.error_id)
    Update-Step $Id "failed" 1 $errorId $StepObserved
    throw
  }
}

function Complete-State {
  Summarize-State $true
  Save-InstallDone
}

trap {
  if (-not $DiagnosticWritten) { Write-JCode (Get-JCode $_.Exception.Message) }
  Write-Host $_.Exception.Message
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
foreach ($step in $Config.steps) {
  $id = [string]$step.id
  if (Test-StepComplete $id) { Say-Step $step '이미 완료 — 건너뜀'; Send-Progress $CurrentStep 'end'; continue }
  if ($id -eq "S09_COMPLETE") { Mark-RequiredComplete }
  Say-Step $step '시작'
  Invoke-Step $id $actions[$id]
}
Complete-State
Say "[10/10] Wave Terminal 설치 상태 $($State.status) — START-HERE와 exceptions를 확인하세요."
