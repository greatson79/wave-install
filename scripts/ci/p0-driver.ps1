$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$root = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$out = Join-Path $root 'ci-evidence\p0'
New-Item -ItemType Directory -Force $out | Out-Null
$setup = @(Get-ChildItem (Join-Path $root 'p0-input') -Filter '*setup.exe' -Recurse)
if ($setup.Count -ne 1) { throw 'Expected exactly one pinned setup.exe' }
Get-FileHash $setup[0].FullName -Algorithm SHA256 | ConvertTo-Json | Set-Content (Join-Path $out 'setup-sha256.json') -Encoding UTF8
@{ repository='greatson79/wave-terminal'; run_id=36884497676; commit='d7b354d74af04cfaed3aa9ef8f926d825091085b'; artifact_id=11174272542 } | ConvertTo-Json | Set-Content (Join-Path $out 'source.json') -Encoding UTF8
$name = 'wavep0' + (Get-Random -Minimum 10000 -Maximum 99999)
$pass = ConvertTo-SecureString ('P0!' + [guid]::NewGuid().ToString('N') + 'Aa9') -AsPlainText -Force
$user = New-LocalUser -Name $name -Password $pass
Add-LocalGroupMember -Group (Get-LocalGroup -SID 'S-1-5-32-545') -Member $user
if (@(Get-LocalGroupMember (Get-LocalGroup -SID 'S-1-5-32-544') | Where-Object SID -eq $user.SID).Count) { throw 'User belongs to Administrators' }
& icacls $out /grant "${name}:(OI)(CI)M" | Out-Null
if ($LASTEXITCODE -ne 0) { throw 'Evidence ACL failed' }
$cred = New-Object Management.Automation.PSCredential("$env:COMPUTERNAME\$name",$pass)
$argsLine = '-NoProfile -ExecutionPolicy Bypass -File "{0}" -Setup "{1}" -Evidence "{2}"' -f (Join-Path $PSScriptRoot 'p0-child.ps1'),$setup[0].FullName,$out
$p = Start-Process "$env:SystemRoot\System32\WindowsPowerShell\v1.0\powershell.exe" -Credential $cred -LoadUserProfile -WorkingDirectory $out -ArgumentList $argsLine -PassThru
$finished = $p.WaitForExit(900000)
@{ finished=$finished; exit_code=$(if($finished){$p.ExitCode}else{$null}); user=$name; scope='Hosted runner, fresh standard-user profile and OS-only PATH; preinstalled tools remain on disk' } | ConvertTo-Json | Set-Content (Join-Path $out 'driver.json') -Encoding UTF8
# A started execution without its terminal record means interrupted/unmeasured;
# stdout/stderr are streamed to disk from process start and remain recoverable.
# Only processes owned by this run's unique disposable user are retired.
Get-CimInstance Win32_Process | ForEach-Object {
  $owner = Invoke-CimMethod -InputObject $_ -MethodName GetOwner -ErrorAction SilentlyContinue
  if ($owner -and $owner.User -eq $name -and $owner.Domain -eq $env:COMPUTERNAME) {
    & taskkill /PID $_.ProcessId /T /F 2>&1 | Out-File (Join-Path $out 'cleanup.log') -Append
  }
}
$childResult = Join-Path $out 'child-result.json'
if (-not $finished -or -not (Test-Path $childResult)) { throw 'Measurement child completion evidence missing' }
if ((Get-Content $childResult -Raw | ConvertFrom-Json).exit_code -ne 0) { throw 'Measurement child failed' }
