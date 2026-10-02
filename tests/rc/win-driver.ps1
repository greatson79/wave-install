# 윈도우 러너(관리자): 시험 인증서 신뢰 → https 서버 → 비관리자 새 계정으로 win-child.ps1 실행 → 증거 회수.
#  win-driver.ps1 -Mode main|upgrade -RcDir <조립 폴더> -Evidence <루트> -Repo <체크아웃> -Py <python.exe>
[CmdletBinding()] param([string]$Mode, [string]$RcDir, [string]$Evidence, [string]$Repo, [string]$Py)
$ErrorActionPreference = 'Stop'
$tls = Join-Path $env:RUNNER_TEMP 'tls'; New-Item -ItemType Directory -Force $tls | Out-Null
$ossl = 'C:\Program Files\Git\usr\bin\openssl.exe'
# PS 5.1 은 $ErrorActionPreference='Stop' 에서 네이티브 명령의 stderr(openssl 진행 점)를 NativeCommandError 로 올린다(8차 실측) → 종료코드로만 판정
function Native([scriptblock]$cmd) { $old = $ErrorActionPreference; $ErrorActionPreference = 'Continue'; & $cmd *> $null; $code = $LASTEXITCODE; $ErrorActionPreference = $old; if ($code -ne 0) { throw "native command failed ($code): $cmd" } }
Native { & $ossl req -x509 -newkey rsa:2048 -nodes -keyout "$tls\k.pem" -out "$tls\c.pem" -days 1 -subj /CN=127.0.0.1 -addext 'subjectAltName=IP:127.0.0.1' }
Native { & $ossl x509 -in "$tls\c.pem" -outform der -out "$tls\c.cer" }
Import-Certificate -FilePath "$tls\c.cer" -CertStoreLocation Cert:\LocalMachine\Root | Out-Null   # 러너 로컬 신뢰(폐기 대상 시험 인증서)
$srv = Start-Process $Py -ArgumentList @((Join-Path $Repo 'tests\rc\serve_https.py'), $RcDir, '8443', "$tls\c.pem", "$tls\k.pem") -PassThru -WindowStyle Hidden
Start-Sleep 3
(Invoke-WebRequest -UseBasicParsing 'https://127.0.0.1:8443/rc-release.json').StatusCode | Out-Host
$name = 'waverc' + (Get-Random -Minimum 10000 -Maximum 99999)
$pw = ConvertTo-SecureString ('Rc!' + [guid]::NewGuid().ToString('N') + 'a9') -AsPlainText -Force
$u = New-LocalUser -Name $name -Password $pw
Add-LocalGroupMember -Group (Get-LocalGroup -SID 'S-1-5-32-545') -Member $u
New-Item -ItemType Directory -Force $Evidence | Out-Null
foreach ($p in @($Evidence)) { Native { & icacls $p /grant "${name}:(OI)(CI)M" } }
foreach ($p in @($Repo, $RcDir, (Split-Path $Py))) { Native { & icacls $p /grant "${name}:(OI)(CI)RX" } }
$cred = New-Object Management.Automation.PSCredential("$env:COMPUTERNAME\$name", $pw)
$args2 = '-NoProfile -ExecutionPolicy Bypass -File "{0}" -Mode {1} -RcJson "{2}" -Evidence "{3}" -Repo "{4}" -Py "{5}"' -f (Join-Path $Repo 'tests\rc\win-child.ps1'), $Mode, (Join-Path $RcDir 'rc-release.json'), $Evidence, $Repo, $Py
$p = Start-Process "$env:SystemRoot\System32\WindowsPowerShell\v1.0\powershell.exe" -Credential $cred -LoadUserProfile -WorkingDirectory $Evidence -ArgumentList $args2 -PassThru
if (-not $p.WaitForExit(3000000)) { cmd /c "taskkill /PID $($p.Id) /T /F" | Out-Host }
Get-CimInstance Win32_Process | ForEach-Object { $o = Invoke-CimMethod -InputObject $_ -MethodName GetOwner -ErrorAction SilentlyContinue; if ($o -and $o.User -eq $name) { cmd /c "taskkill /PID $($_.ProcessId) /T /F" | Out-Null } }
Stop-Process -Id $srv.Id -Force -ErrorAction SilentlyContinue
"child exit: $($p.ExitCode)" | Out-Host
