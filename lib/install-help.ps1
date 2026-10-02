# W5 최소판 설계 §② 가림 8규칙 + API 계약 §3 평문 제어문자 제거.
# 순수 문자열 변환만 제공한다. 호출자가 현재 로그인 이름을 Username에 전달한다.
function ConvertTo-HelpSafeText([AllowEmptyString()][string]$Text, [AllowEmptyString()][string]$Username = '') {
  if ($null -eq $Text) { return '' }
  # 먼저 제어문자를 제거해 토큰 중간에 끼운 ESC 등으로 가림을 우회하지 못하게 한다.
  $safe = [regex]::Replace($Text, '\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)', '')
  $safe = [regex]::Replace($safe, '\x1b\[[0-?]*[ -/]*[@-~]', '')
  $safe = [regex]::Replace($safe, '[\x00-\x08\x0b-\x1f\x7f]', '')
  # lib/install_help.py RULES 와 같은 규칙·같은 순서(동등성 시험). 벤더 접두 토큰은 앞에 단어 문자가 붙어 있어도 잡는다.
  $safe = [regex]::Replace($safe, '[A-Za-z0-9._%+-]{1,64}@[A-Za-z0-9-]{1,63}(\.[A-Za-z0-9-]{1,63})*\.[A-Za-z]{2,63}', '<EMAIL>')
  $safe = [regex]::Replace($safe, '(?i)\bBearer\s+[A-Za-z0-9._~+/=-]+', '<TOKEN>')
  $safe = [regex]::Replace($safe, '(?<![A-Za-z0-9])sk-[A-Za-z0-9_-]{8,}|sk-[A-Za-z0-9_-]{20,}', '<TOKEN>')
  $safe = [regex]::Replace($safe, '(?:gh[pousr]_|github_pat_)[A-Za-z0-9_]{20,}', '<TOKEN>')
  $safe = [regex]::Replace($safe, 'AIza[0-9A-Za-z_-]{35}', '<TOKEN>')
  $safe = [regex]::Replace($safe, 'xox[abprs]-[0-9A-Za-z-]{10,}', '<TOKEN>')
  $safe = [regex]::Replace($safe, 'npm_[A-Za-z0-9]{36}', '<TOKEN>')
  $safe = [regex]::Replace($safe, '(?:AKIA|ASIA)[0-9A-Z]{16}', '<TOKEN>')
  $safe = [regex]::Replace($safe, 'eyJ[A-Za-z0-9_-]{5,}\.[A-Za-z0-9_-]{5,}\.[A-Za-z0-9_-]{5,}', '<TOKEN>')
  $safe = [regex]::Replace($safe, '(?i)((?<![A-Za-z0-9])[A-Za-z0-9_]*(?:KEY|TOKEN|SECRET|PASSWORD|PASSWD)["'']?\s*[=:]\s*["'']?)[^\s"'',;}]+', '${1}<SECRET>')
  $safe = [regex]::Replace($safe, '\b[A-Za-z0-9_-]{20,}#[A-Za-z0-9_-]{8,}\b', '<LOGIN_CODE>')
  $safe = [regex]::Replace($safe, '(?im)(Paste code here if prompted\s*>)[^\n]*', '${1} <LOGIN_CODE>')
  if (-not [string]::IsNullOrEmpty($Username)) {
    $safe = [regex]::Replace($safe, ('(?<!\w)' + [regex]::Escape($Username) + '(?!\w)'), '<USER>', [Text.RegularExpressions.RegexOptions]::IgnoreCase)
  }
  # 프로필 폴더는 공백을 포함하고 로그인 이름과 다를 수 있다: 다음 구분자까지를 먼저 가린다.
  $safe = [regex]::Replace($safe, '(?i)[A-Za-z]:[\\/]+Users[\\/]+[^\\/\n"''|:*?]{1,64}?(?=[\\/])', 'C:\Users\<USER>')
  $safe = [regex]::Replace($safe, '(?i)[A-Za-z]:[\\/]+Users[\\/]+[^\\/\s]+', 'C:\Users\<USER>')
  $safe = [regex]::Replace($safe, '/(?:Users|home)/[^/\n"''|:*?]{1,64}?(?=/)', '/Users/<USER>')
  $safe = [regex]::Replace($safe, '/(?:Users|home)/[^/\s]+', '/Users/<USER>')
  $safe = [regex]::Replace($safe, '(?im)((?:USERNAME\s*=|whoami\s*:)\s*)[^\n]*', '${1}<USER>')
  return $safe
}

# ---- R5 install-help client (API 계약 v1 §2-4, §5-1) — lib/install_help_client.py 와 같은 계약 ----
# fail-open: 모든 오류를 삼키고 호출자의 설치 상태·계속 진행·종료값을 바꾸지 않는다.
# 첫 화면 고지(Show-HelpNotice) 전에는 아무것도 보내지 않는다. 받은 처방 글은 표시만 하고 실행하지 않는다.
# client_token 은 이 함수의 지역 변수에만 둔다(로그·파일·화면 출력 금지).
$script:HelpLibDir = $PSScriptRoot
$script:HelpNoticeShown = $false
$script:HelpDefaultBaseUrl = 'https://waveainetworks.com'

function Show-HelpNotice {
  $path = Join-Path $script:HelpLibDir 'help-notice.txt'
  if (-not (Test-Path -LiteralPath $path -PathType Leaf)) { return }
  Write-Host ((Get-Content -LiteralPath $path -Raw -Encoding UTF8).TrimEnd())
  $script:HelpNoticeShown = $true
}

function Get-HelpBaseUrl {
  if ($env:WAVE_HELP_BASE_URL) { return $env:WAVE_HELP_BASE_URL }
  return $script:HelpDefaultBaseUrl
}

function Limit-HelpBytes([AllowEmptyString()][string]$Text, [int]$Max, [switch]$Tail) {
  $encoding = [Text.UTF8Encoding]::new($false)
  $bytes = $encoding.GetBytes([string]$Text)
  if ($bytes.Length -le $Max) { return [string]$Text }
  if ($Tail) {
    $start = $bytes.Length - $Max
    while ($start -lt $bytes.Length -and ($bytes[$start] -band 0xC0) -eq 0x80) { $start++ }
    return $encoding.GetString($bytes, $start, $bytes.Length - $start)
  }
  $end = $Max
  $lead = $end - 1
  while ($lead -gt 0 -and ($bytes[$lead] -band 0xC0) -eq 0x80) { $lead-- }
  $need = if ($bytes[$lead] -ge 0xF0) { 4 } elseif ($bytes[$lead] -ge 0xE0) { 3 } elseif ($bytes[$lead] -ge 0xC0) { 2 } else { 1 }
  if ($lead + $need -gt $end) { $end = $lead }
  return $encoding.GetString($bytes, 0, $end)
}

function ConvertTo-HelpDisplayText([AllowEmptyString()][string]$Text) {
  $safe = [regex]::Replace([string]$Text, '\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)', '')
  $safe = [regex]::Replace($safe, '\x1b\[[0-?]*[ -/]*[@-~]', '')
  $safe = [regex]::Replace($safe, '[\x00-\x08\x0b-\x1f\x7f]', '')
  if ($safe.Length -gt 4096) { $safe = $safe.Substring(0, 4096) }
  return $safe
}

function New-HelpPayload([string]$InstallId, [string]$Version, [string]$Step, [string]$Code, [AllowEmptyString()][string]$EnvReport, [AllowEmptyString()][string]$LogTail, [AllowEmptyString()][string]$Username) {
  # 순서 고정: 전체를 먼저 가리고 그다음 줄·바이트로 자른다(잘린 경로·토큰 조각은 가림 규칙이 못 알아본다).
  $lines = [System.Collections.Generic.List[string]]::new()
  foreach ($line in ((ConvertTo-HelpSafeText $LogTail $Username) -split "`n")) { $lines.Add($line) }
  if ($lines.Count -gt 0 -and $lines[$lines.Count - 1] -eq '') { $lines.RemoveAt($lines.Count - 1) }
  $keep = [Math]::Min(40, $lines.Count)
  $tail = ($lines.GetRange($lines.Count - $keep, $keep)) -join "`n"
  return [ordered]@{
    install_id = $InstallId
    os = 'win'
    installer_version = $(if ($Version -cmatch '^[0-9A-Za-z._-]{1,20}$') { $Version } else { 'unknown' })
    step = $(if ($Step -match '^\d{1,2}/\d{1,2}$') { $Step } else { '1/10' })
    code = $(if ($Code -cmatch '^J-[A-Z0-9]{2,8}-\d{2,3}$') { $Code } else { 'J-UNK-00' })
    notice_shown = $true
    env_report = Limit-HelpBytes (ConvertTo-HelpSafeText $EnvReport $Username) (96 * 1024)
    log_tail = Limit-HelpBytes $tail (128 * 1024) -Tail
  }
}

# 실제 전송: 리다이렉트 금지 · 시간 제한 · 응답 256KB 상한. 테스트는 이 함수를 대역으로 덮어쓴다.
function Invoke-HelpHttp([string]$Method, [string]$Path, $Body, [string]$Token, [int]$TimeoutSec) {
  $request = [System.Net.HttpWebRequest]::Create((Get-HelpBaseUrl).TrimEnd('/') + $Path)
  $request.Method = $Method
  $request.AllowAutoRedirect = $false
  $request.Timeout = $TimeoutSec * 1000
  $request.ReadWriteTimeout = $TimeoutSec * 1000
  $request.ContentType = 'application/json'
  if ($Token) { $request.Headers.Add('x-help-client', $Token) }
  if ($null -ne $Body) {
    $bytes = [Text.Encoding]::UTF8.GetBytes(($Body | ConvertTo-Json -Depth 5 -Compress))
    $request.ContentLength = $bytes.Length
    $stream = $request.GetRequestStream()
    try { $stream.Write($bytes, 0, $bytes.Length) } finally { $stream.Dispose() }
  }
  try { $response = $request.GetResponse() }
  catch [System.Net.WebException] {
    if ($null -eq $_.Exception.Response) { throw }
    $response = $_.Exception.Response
  }
  try {
    $status = [int]$response.StatusCode
    $reader = $response.GetResponseStream()
    $buffer = New-Object byte[] (256 * 1024 + 1)
    $total = 0
    while ($total -lt $buffer.Length) {
      $read = $reader.Read($buffer, $total, $buffer.Length - $total)
      if ($read -le 0) { break }
      $total += $read
    }
    if ($total -gt 256 * 1024) { throw 'response too large' }
    $text = [Text.Encoding]::UTF8.GetString($buffer, 0, $total)
    $parsed = $null
    if ($text.Trim()) { try { $parsed = $text | ConvertFrom-Json } catch { $parsed = $null } }
    return @{ status = $status; body = $parsed }
  } finally { $response.Close() }
}

function Start-HelpSleep([int]$Seconds) { Start-Sleep -Seconds $Seconds }
function Get-HelpClock { return [DateTime]::UtcNow.Ticks / 10000000 }
function Write-HelpLine([string]$Line) { Write-Host $Line }

function Invoke-HelpCall([string]$Method, [string]$Path, $Body, [string]$Token, [int]$TimeoutSec) {
  try { return Invoke-HelpHttp $Method $Path $Body $Token $TimeoutSec } catch { return @{ status = $null; body = $null } }
}

function Get-HelpField($Object, [string]$Name) {
  if ($null -eq $Object) { return $null }
  if ($Object -is [System.Collections.IDictionary]) { return $Object[$Name] }
  $property = $Object.PSObject.Properties[$Name]
  if ($null -eq $property) { return $null }
  return $property.Value
}

function Send-HelpRequest([string]$BaseUrl, [string]$InstallId, [string]$Version, [string]$Step, [string]$Code, [AllowEmptyString()][string]$EnvReport, [AllowEmptyString()][string]$LogTail, [bool]$Interactive, [AllowEmptyString()][string]$Username) {
  try {
    if (-not $script:HelpNoticeShown -or $env:WAVE_NO_PROGRESS -eq '1') { return $null }
    if ($BaseUrl -notlike 'https://*' -or $InstallId -cnotmatch '^[0-9a-f]{32}$') { return $null }
    $payload = New-HelpPayload $InstallId $Version $Step $Code $EnvReport $LogTail $Username
    if ([Text.Encoding]::UTF8.GetByteCount(($payload | ConvertTo-Json -Compress)) -gt 4MB) { return $null }
    $previousBase = $env:WAVE_HELP_BASE_URL
    $env:WAVE_HELP_BASE_URL = $BaseUrl
    try {
      $reply = Invoke-HelpCall 'POST' '/api/help' $payload '' 20
      if ($reply.status -eq 503) {
        Start-HelpSleep 60
        $reply = Invoke-HelpCall 'POST' '/api/help' $payload '' 20
      }
      $rid = Get-HelpField $reply.body 'id'
      $token = Get-HelpField $reply.body 'client_token'
      if ($reply.status -ne 201 -or $rid -isnot [string] -or $token -isnot [string] -or $rid -cnotmatch '^[0-9a-f]{32}$' -or $token -cnotmatch '^[0-9a-f]{64}$') {
        Write-HelpLine '도움 요청을 보내지 못했습니다. 설치 결과와 종료 상태는 바뀌지 않습니다.'
        return $null
      }
      Write-HelpLine ('도움 요청을 접수했습니다. 접수번호: ' + $rid.Substring(0, 8))
      if (-not $Interactive) {
        Write-HelpLine '이 창은 기다리지 않고 끝납니다. 담당자에게 접수번호를 알려 주세요.'
        return $rid
      }
      Write-HelpLine '담당자 답을 이 창에 표시합니다(최대 2시간). 끝내려면 Ctrl+C를 누르세요. 받은 글은 실행하지 않습니다.'
      try {
        $deadline = (Get-HelpClock) + 7200
        $lastSeq = 0
        $first = $true
        while ($true) {
          if (-not $first) {
            if ((Get-HelpClock) + 20 -gt $deadline) { break }
            Start-HelpSleep 20
          }
          $first = $false
          $poll = Invoke-HelpCall 'GET' ('/api/help/' + $rid) $null $token 20
          if ($poll.status -eq 404 -or $poll.status -eq 410) { break }
          $messages = Get-HelpField $poll.body 'messages'
          if ($poll.status -ne 200 -or $null -eq $messages) { continue }
          $fresh = @($messages | Where-Object {
              (Get-HelpField $_ 'kind') -ceq 'text' -and ((Get-HelpField $_ 'seq') -is [int] -or (Get-HelpField $_ 'seq') -is [long]) -and (Get-HelpField $_ 'seq') -gt $lastSeq
            } | Sort-Object { [long](Get-HelpField $_ 'seq') })
          foreach ($message in $fresh) {
            $lastSeq = [long](Get-HelpField $message 'seq')
            Write-HelpLine (ConvertTo-HelpDisplayText ([string](Get-HelpField $message 'body')))
          }
        }
      } finally {
        $null = Invoke-HelpCall 'POST' ('/api/help/' + $rid + '/close') @{} $token 20
      }
      return $rid
    } finally { $env:WAVE_HELP_BASE_URL = $previousBase }
  } catch { return $null }
}
