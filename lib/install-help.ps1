# W5 최소판 설계 §② 가림 8규칙 + API 계약 §3 평문 제어문자 제거.
# 순수 문자열 변환만 제공한다. 호출자가 현재 로그인 이름을 Username에 전달한다.
function ConvertTo-HelpSafeText([AllowEmptyString()][string]$Text, [AllowEmptyString()][string]$Username = '') {
  if ($null -eq $Text) { return '' }
  # 먼저 제어문자를 제거해 토큰 중간에 끼운 ESC 등으로 가림을 우회하지 못하게 한다.
  $safe = [regex]::Replace($Text, '\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)', '')
  $safe = [regex]::Replace($safe, '\x1b\[[0-?]*[ -/]*[@-~]', '')
  $safe = [regex]::Replace($safe, '[\x00-\x08\x0b-\x1f\x7f]', '')
  $safe = [regex]::Replace($safe, '[A-Za-z0-9._%+-]{1,64}@[A-Za-z0-9-]{1,63}(\.[A-Za-z0-9-]{1,63})*\.[A-Za-z]{2,63}', '<EMAIL>')
  $safe = [regex]::Replace($safe, '(?i)\bBearer\s+[A-Za-z0-9._~+/=-]+', '<TOKEN>')
  $safe = [regex]::Replace($safe, '\bsk-[A-Za-z0-9_-]{8,}', '<TOKEN>')
  $safe = [regex]::Replace($safe, '\b(?:gh[pousr]_|github_pat_)[A-Za-z0-9_]{20,}', '<TOKEN>')
  $safe = [regex]::Replace($safe, '\b[A-Za-z0-9_-]{20,}#[A-Za-z0-9_-]{8,}\b', '<LOGIN_CODE>')
  $safe = [regex]::Replace($safe, '(?im)(Paste code here if prompted\s*>)[^\n]*', '${1} <LOGIN_CODE>')
  if (-not [string]::IsNullOrEmpty($Username)) {
    $safe = [regex]::Replace($safe, ('(?<!\w)' + [regex]::Escape($Username) + '(?!\w)'), '<USER>', [Text.RegularExpressions.RegexOptions]::IgnoreCase)
  }
  $safe = [regex]::Replace($safe, '(?i)[A-Za-z]:[\\/]+Users[\\/]+[^\\/\s]+', 'C:\Users\<USER>')
  $safe = [regex]::Replace($safe, '/(?:Users|home)/[^/\s]+', '/Users/<USER>')
  $safe = [regex]::Replace($safe, '(?im)((?:USERNAME\s*=|whoami\s*:)\s*)[^\n]*', '${1}<USER>')
  return $safe
}
