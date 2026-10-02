param([Parameter(Mandatory = $true)][string]$ScenarioFile)
# R5 PowerShell help-client fixture: scripted fake transport, recorded sleeps/clock/output. No network.
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [Text.UTF8Encoding]::new()
. (Join-Path $PSScriptRoot '../lib/install-help.ps1')
$data = Get-Content -LiteralPath $ScenarioFile -Raw -Encoding UTF8 | ConvertFrom-Json

$script:queue = @(); $script:qi = 0; $script:calls = @(); $script:sleeps = @(); $script:out = @(); $script:tick = 0
function Invoke-HelpHttp([string]$Method, [string]$Path, $Body, [string]$Token, [int]$TimeoutSec) {
  $script:calls += , ([ordered]@{ method = $Method; path = $Path; payload = $Body; token = $(if ($Token) { $Token } else { $null }); timeout = $TimeoutSec })
  $next = $script:queue[$script:qi]; $script:qi++
  if ($next -is [string] -and $next -eq 'raise') { throw 'down C:\Users\alice' }
  return @{ status = [int]$next[0]; body = $next[1] }
}
function Start-HelpSleep([int]$Seconds) { $script:sleeps += $Seconds; $script:tick += $Seconds }
function Get-HelpClock { return $script:tick }
function Write-HelpLine([string]$Line) { $script:out += $Line }

function Reset-Fixture($Responses) {
  $script:queue = @($Responses); $script:qi = 0; $script:calls = @(); $script:sleeps = @(); $script:out = @(); $script:tick = 0
}

$gate = [ordered]@{}
# 1) Nothing leaves before the first-screen notice.
$script:HelpNoticeShown = $false
Reset-Fixture @(, @(201, @{}))
$null = Send-HelpRequest -BaseUrl 'https://example.test' -InstallId ('a' * 32) -Version '9.9.9' -Step '1/10' -Code 'J-UNK-00' -EnvReport 'e' -LogTail 'l' -Interactive $true -Username 'alice'
$gate.no_call_before_notice = ($script:calls.Count -eq 0)

$noticeText = (Show-HelpNotice 6>&1 | Out-String)
if (-not $script:HelpNoticeShown) { throw 'notice did not arm sending' }

# 2) WAVE_NO_PROGRESS=1 blocks help as well as progress.
$env:WAVE_NO_PROGRESS = '1'
Reset-Fixture @(, @(201, @{}))
$null = Send-HelpRequest -BaseUrl 'https://example.test' -InstallId ('a' * 32) -Version '9.9.9' -Step '1/10' -Code 'J-UNK-00' -EnvReport 'e' -LogTail 'l' -Interactive $true -Username 'alice'
$gate.no_progress_blocks_help = ($script:calls.Count -eq 0)
$env:WAVE_NO_PROGRESS = '0'

# 3) http base URL is refused without a call.
Reset-Fixture @(, @(201, @{}))
$null = Send-HelpRequest -BaseUrl 'http://example.test' -InstallId ('a' * 32) -Version '9.9.9' -Step '1/10' -Code 'J-UNK-00' -EnvReport 'e' -LogTail 'l' -Interactive $true -Username 'alice'
if ($script:calls.Count -ne 0) { throw 'non-https base accepted' }

$results = [ordered]@{}
foreach ($property in $data.scenarios.PSObject.Properties) {
  $scenario = $property.Value
  Reset-Fixture $scenario.responses
  $null = Send-HelpRequest -BaseUrl 'https://example.test' -InstallId ('a' * 32) -Version '9.9.9' -Step '3/10' -Code 'J-NET-01' -EnvReport $data.env -LogTail $data.log -Interactive ([bool]$scenario.interactive) -Username 'alice'
  $results[$property.Name] = [ordered]@{ calls = @($script:calls); sleeps = @($script:sleeps); output = @($script:out) }
}
$json = [ordered]@{ gate = $gate; notice = $noticeText; results = $results } | ConvertTo-Json -Depth 10 -Compress
Write-Output ('RESULT:' + $json)
