$ErrorActionPreference='Stop'
Set-StrictMode -Version Latest
$t=$null;$errors=$null
$ast=[System.Management.Automation.Language.Parser]::ParseFile((Join-Path $PWD 'bootstrap.ps1'),[ref]$t,[ref]$errors)
if($errors.Count){$errors|Out-String|Write-Host;exit 1}
$ast.FindAll({param($n) $n -is [System.Management.Automation.Language.FunctionDefinitionAst]},$false) | ForEach-Object {Invoke-Expression $_.Extent.Text}
$root=$env:TS_FIXTURE_HOME
$dir=Join-Path (Join-Path $root 'cys') 'claude'; $cfg=Join-Path $dir '.claude.json'; $sf=Join-Path $dir 'settings.json'; $journal=Join-Path (Join-Path $root 'wave') 'trust-seed.tsv'
$homeWin='C:\Users\first.last'; $homeFwd='C:/Users/first.last'; $work='C:\Users\first.last\.wave'
$LogFile=Join-Path $root 'install.log'
function Assert-UserPath([string]$Path) { }
function Read-Cfg { Get-Content -LiteralPath $cfg -Raw -Encoding UTF8 | ConvertFrom-Json }
# 설정 폴더가 없으면 건너뛴다(원작 Get-ProfileTargets — 있는 것만)
if((Set-WaveClaudeTrust $dir $journal $work $homeWin) -ne 'skip' -or (Test-Path $dir)){throw 'skip'}
Write-Host 'PASS skip'
New-Item -ItemType Directory -Force -Path $dir | Out-Null
# fresh: 온보딩 · 큰 화면 99 · 작업폴더 2꼴 · 홈 2꼴 · settings remoteControlAtStartup=true · BOM 없음
if((Set-WaveClaudeTrust $dir $journal $work $homeWin) -ne 'ok'){throw 'fresh result'}
$o=Read-Cfg
if(-not $o.hasCompletedOnboarding -or $o.fullscreenUpsellSeenCount -ne 99){throw 'fresh top keys'}
foreach($k in @($homeWin,$homeFwd,$work,'C:/Users/first.last/.wave')){ if(-not $o.projects.$k.hasTrustDialogAccepted){throw "fresh trust $k"} }
if((Get-Content $sf -Raw | ConvertFrom-Json).remoteControlAtStartup -ne $true){throw 'fresh remoteControl'}
$bytes=[IO.File]::ReadAllBytes($cfg); if($bytes[0] -eq 0xEF){throw 'BOM written'}
if(@((Get-Content $journal -Raw) -split "`r?`n" | Where-Object { $_ }).Count -ne 3){throw 'fresh journal rows'}
Write-Host 'PASS fresh'
# rerun: 바이트 불변
$h1=(Get-FileHash $cfg).Hash; $j1=(Get-FileHash $journal).Hash; $s1=(Get-FileHash $sf).Hash
Set-WaveClaudeTrust $dir $journal $work $homeWin | Out-Null
if((Get-FileHash $journal).Hash -ne $j1 -or (Get-FileHash $sf).Hash -ne $s1){throw 'rerun bytes'}
if((Get-Content $LogFile -Raw -Encoding UTF8) -notmatch '홈 폴더 신뢰 설정이 이미 있어'){throw 'rerun notice'}
Write-Host 'PASS rerun'
# rollback: 우리 홈 키·작업폴더 칸·remoteControl 제거(온보딩·99 는 원작처럼 남는다)
Undo-WaveClaudeTrust $dir $journal $work | Out-Null
$o=Read-Cfg
if(@($o.projects.PSObject.Properties).Count -ne 0 -or -not $o.hasCompletedOnboarding){throw 'rollback cfg'}
if($null -ne (Get-Content $sf -Raw | ConvertFrom-Json).PSObject.Properties['remoteControlAtStartup']){throw 'rollback settings'}
if(Test-Path $journal){throw 'journal left'}
Write-Host 'PASS rollback'
# preserve: 다른 키 보존 · 홈 false 는 그대로 · 백업 사본 · 되돌리면 settings false 복원
Remove-Item $cfg,$sf -Force
$orig='{"oauthAccount":{"emailAddress":"x"},"hasCompletedOnboarding":false,"projects":{"D:/other":{"hasTrustDialogAccepted":false,"allowedTools":[]},"C:/Users/first.last":{"hasTrustDialogAccepted":false,"history":["a"]}}}'
[IO.File]::WriteAllText($cfg,$orig); [IO.File]::WriteAllText($sf,'{"remoteControlAtStartup":false}')
Remove-Item ($cfg+'.bak-wave'),($sf+'.bak-wave') -Force -ErrorAction SilentlyContinue
if((Set-WaveClaudeTrust $dir $journal $work $homeWin) -ne 'ok'){throw 'preserve result'}
$o=Read-Cfg
if($o.oauthAccount.emailAddress -ne 'x' -or $o.projects.'D:/other'.hasTrustDialogAccepted -ne $false -or @($o.projects.$homeFwd.history)[0] -ne 'a'){throw 'preserve other keys'}
if($o.projects.$homeFwd.hasTrustDialogAccepted -ne $false -or -not $o.projects.$homeWin.hasTrustDialogAccepted -or -not $o.hasCompletedOnboarding){throw 'preserve home rule'}
$bk=Get-Content ($cfg+'.bak-wave') -Raw; if($bk -ne $orig){throw "backup missing [$bk]"}
Undo-WaveClaudeTrust $dir $journal $work | Out-Null
$o=Read-Cfg
if($o.projects.$homeFwd.hasTrustDialogAccepted -ne $false -or $null -ne $o.projects.PSObject.Properties[$homeWin]){throw 'rollback home'}
if((Get-Content $sf -Raw | ConvertFrom-Json).remoteControlAtStartup -ne $false){throw 'rollback settings prior'}
Write-Host 'PASS preserve'
# 기록 실패: 홈 키를 넣지 않고 J-PERM-01 로 멈춘다
Remove-Item $cfg,$sf -Force; New-Item -ItemType Directory -Force -Path $journal | Out-Null
$WaveHome=Join-Path $root 'wave'; $env:CYS_ACCOUNT_DIR=$dir; $env:USERPROFILE=$homeWin
$threw=$false; try { Seed-WaveClaudeTrust } catch { $threw=($_.Exception.Message -match '^J-PERM-01') }
if(-not $threw){throw 'journal failure not stopped'}
if($null -ne (Read-Cfg).projects.PSObject.Properties[$homeWin]){throw 'home key without journal'}
Remove-Item $journal -Force
Write-Host 'PASS journal'
# 관문 화면: 안내 1회 · read-screen 만 부르고 키는 보내지 않는다 · 확인 에코만 남은 화면은 관문 아님
Remove-Item $LogFile -Force
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
