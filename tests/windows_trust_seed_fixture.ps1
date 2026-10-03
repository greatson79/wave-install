$ErrorActionPreference='Stop'
Set-StrictMode -Version Latest
$t=$null;$errors=$null
$ast=[System.Management.Automation.Language.Parser]::ParseFile((Join-Path $PWD 'bootstrap.ps1'),[ref]$t,[ref]$errors)
if($errors.Count){$errors|Out-String|Write-Host;exit 1}
$ast.FindAll({param($n) $n -is [System.Management.Automation.Language.FunctionDefinitionAst]},$false) | ForEach-Object {Invoke-Expression $_.Extent.Text}
$root=$env:TS_FIXTURE_HOME
$dir=Join-Path $root 'cys\claude'; $cfg=Join-Path $dir '.claude.json'; $journal=Join-Path $root 'wave\trust-seed.json'
$homeWin='C:\Users\first.last'; $dirs=@($homeWin,'C:/Users/first.last')
function Read-Cfg { Get-Content -LiteralPath $cfg -Raw -Encoding UTF8 | ConvertFrom-Json }

# fresh: 파일 생성 · 키 3칸(온보딩 + 홈 2꼴) · BOM 없음
if((Set-WaveClaudeTrust $dir $journal $true $dirs) -ne 'changed 3'){throw 'fresh count'}
$o=Read-Cfg
if(-not $o.hasCompletedOnboarding -or -not $o.projects.$homeWin.hasTrustDialogAccepted -or -not $o.projects.'C:/Users/first.last'.hasTrustDialogAccepted){throw 'fresh keys'}
$bytes=[IO.File]::ReadAllBytes($cfg); if($bytes[0] -eq 0xEF){throw 'BOM written'}
Write-Host 'PASS fresh'
# rerun: 바이트 불변
$h1=(Get-FileHash $cfg).Hash; $j1=(Get-FileHash $journal).Hash
if((Set-WaveClaudeTrust $dir $journal $true $dirs) -ne 'unchanged'){throw 'rerun changed'}
if((Get-FileHash $cfg).Hash -ne $h1 -or (Get-FileHash $journal).Hash -ne $j1){throw 'rerun bytes'}
Write-Host 'PASS rerun'
# rollback(만든 파일): 파일·기록 모두 사라진다
if((Undo-WaveClaudeTrust $journal) -ne 'rolled back 3'){throw 'rollback count'}
if((Test-Path $cfg) -or (Test-Path $journal)){throw 'rollback created file left'}
# preserve: 다른 키 보존 · false → true · 되돌리면 원래 값
$orig='{"oauthAccount":{"emailAddress":"x"},"hasCompletedOnboarding":false,"projects":{"D:/other":{"hasTrustDialogAccepted":false,"allowedTools":[]},"C:/Users/first.last":{"hasTrustDialogAccepted":false,"history":["a"]}}}'
[IO.File]::WriteAllText($cfg,$orig)
if((Set-WaveClaudeTrust $dir $journal $true $dirs) -ne 'changed 3'){throw 'preserve count'}
$o=Read-Cfg
if($o.oauthAccount.emailAddress -ne 'x' -or $o.projects.'D:/other'.hasTrustDialogAccepted -ne $false -or @($o.projects.'C:/Users/first.last'.history)[0] -ne 'a'){throw 'preserve other keys'}
if(-not $o.projects.'C:/Users/first.last'.hasTrustDialogAccepted -or -not $o.hasCompletedOnboarding){throw 'preserve raise'}
if(-not (Test-Path ($cfg+'.wave-bak'))){throw 'backup missing'}
Write-Host 'PASS preserve'
Undo-WaveClaudeTrust $journal | Out-Null
$o=Read-Cfg
if($o.hasCompletedOnboarding -ne $false -or $o.projects.'C:/Users/first.last'.hasTrustDialogAccepted -ne $false -or $o.projects.'D:/other'.hasTrustDialogAccepted -ne $false){throw 'rollback prior'}
if($null -ne $o.projects.PSObject.Properties[$homeWin]){throw 'rollback made entry left'}
Write-Host 'PASS rollback'
# unproven: 온보딩 키를 넣지 않는다
Remove-Item $cfg,($cfg+'.wave-bak') -Force
if((Set-WaveClaudeTrust $dir $journal $false $dirs) -ne 'changed 2'){throw 'unproven count'}
if($null -ne (Read-Cfg).PSObject.Properties['hasCompletedOnboarding']){throw 'unproven onboarding written'}
Write-Host 'PASS unproven'
# 관문 화면: 안내 1회 · read-screen 만 부르고 키는 보내지 않는다 · 확인 에코만 남은 화면은 관문 아님
$WaveHome=Join-Path $root 'wave'; $LogFile=Join-Path $WaveHome 'install.log'
function Assert-UserPath([string]$Path) { }
$script:Calls=@(); $script:Screen=$env:TS_ECHO
function Invoke-BoundedCheck($FilePath,$Arguments,$Name,$TimeoutMs){ $script:Calls+=($Arguments -join ' '); return [pscustomobject]@{timed_out=$false;exit_code=0;stdout=$script:Screen;stderr=''} }
$status=[pscustomobject]@{surfaces=@([pscustomobject]@{surface_ref='surface:5';role='master';exited=$false},[pscustomobject]@{surface_ref='surface:7';role='cso';exited=$false})}
Show-FirstRunGateNotice $status
if((Test-Path $LogFile) -and ((Get-Content $LogFile -Raw) -match '골라 주세요')){throw 'echo-only screen noticed'}
$script:Screen=$env:TS_TRUST
Show-FirstRunGateNotice $status; Show-FirstRunGateNotice $status
$n=([regex]::Matches((Get-Content $LogFile -Raw -Encoding UTF8),'골라 주세요')).Count
if($n -ne 1){throw "notice count $n"}
if(@($script:Calls | Where-Object { $_ -notmatch '^read-screen --surface surface:' }).Count){throw 'non read-screen call'}
Write-Host 'PASS gate notice'
