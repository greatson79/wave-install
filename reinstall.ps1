[CmdletBinding()]
param([switch]$List)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path

if ($List) {
  @(
    "reinstall.ps1 계획(기본은 실행하지 않음):",
    "1. 사용자 프로필 아래 install-state.json을 타임스탬프 백업",
    "2. 기존 pack·로그는 보존",
    "3. bootstrap.ps1 -Reinstall로 S00부터 재검증",
    "4. S09에서 필수 단계 실측 후에만 complete 기록"
  ) | Write-Host
  exit 0
}

& (Join-Path $ScriptDir "bootstrap.ps1") -Reinstall
