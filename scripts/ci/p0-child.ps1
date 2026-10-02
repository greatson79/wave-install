param([string]$Setup,[string]$Evidence)
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
Start-Transcript (Join-Path $Evidence 'child.log') | Out-Null
try {
  $id = [Security.Principal.WindowsIdentity]::GetCurrent()
  $principal = New-Object Security.Principal.WindowsPrincipal($id)
  if ($principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator) -or @($id.Groups | Where-Object Value -eq 'S-1-5-32-544').Count) { throw 'Admin token prohibited' }
  $profile = (Get-ItemProperty "HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion\ProfileList\$($id.User.Value)").ProfileImagePath
  $env:USERPROFILE=$profile
  $env:LOCALAPPDATA=Join-Path $profile 'AppData\Local'
  $env:APPDATA=Join-Path $profile 'AppData\Roaming'
  $env:TEMP=Join-Path $env:LOCALAPPDATA 'Temp'
  $env:TMP=$env:TEMP
  New-Item -ItemType Directory -Force $env:TEMP | Out-Null
  Get-ChildItem Env: | Where-Object Name -match '^(CYS_|AITERM_|JAVIS_|WAVE_|CLAUDE_|ANTHROPIC_|OPENAI_|GH_|GITHUB_|PYTHON|VIRTUAL_ENV|CONDA|HOME$)' | ForEach-Object { Remove-Item "Env:$($_.Name)" }
  $env:PATH="$env:SystemRoot\System32;$env:SystemRoot;$env:SystemRoot\System32\WindowsPowerShell\v1.0"
  $nonce=[guid]::NewGuid().ToString('N')
  New-Item 'HKCU:\Software\WaveP0' -Force | Out-Null
  New-ItemProperty 'HKCU:\Software\WaveP0' -Name probe -Value $nonce -Force | Out-Null
  if ((Get-ItemProperty "Registry::HKEY_USERS\$($id.User.Value)\Software\WaveP0").probe -cne $nonce) { throw 'HKCU identity mismatch' }
  @{ identity=$id.Name; sid=$id.User.Value; administrator=$false; profile=$profile; hkcu_verified=$true; os_path=$env:PATH } | ConvertTo-Json | Set-Content (Join-Path $Evidence 'identity.json') -Encoding UTF8
  $before=@{}
  foreach($tool in @('python3','bash','git','node','uv')) { $before[$tool]=@(Get-Command $tool -CommandType Application -All -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Source) }
  $before | ConvertTo-Json -Depth 5 | Set-Content (Join-Path $Evidence 'runtime-before.json') -Encoding UTF8
  $dir=Join-Path $profile 'WaveP0App'
  $install=Start-Process $Setup -ArgumentList ('/S /D=' + $dir) -PassThru
  $finished=$install.WaitForExit(180000)
  @{ finished=$finished; exit_code=$(if($finished){$install.ExitCode}else{$null}); install_dir=$dir } | ConvertTo-Json | Set-Content (Join-Path $Evidence 'install.json') -Encoding UTF8
  if (-not $finished -or $install.ExitCode -ne 0) { throw 'NSIS install failed or timed out' }
  Get-ChildItem $dir -Recurse -File | Select-Object FullName,Length | ConvertTo-Json -Depth 4 | Set-Content (Join-Path $Evidence 'installed-inventory.json') -Encoding UTF8
  $python=Join-Path $dir 'runtime\python\python3.exe'
  if (-not(Test-Path $python)) { throw 'Bundled Python missing; remaining measurements unavailable' }
  & $python (Join-Path $PSScriptRoot 'p0-measure.py') --app $dir --evidence $Evidence
  if ($LASTEXITCODE -ne 0) { throw 'Measurement script failed' }
  @{ exit_code=0; source='child explicit completion marker' } | ConvertTo-Json | Set-Content (Join-Path $Evidence 'child-result.json') -Encoding UTF8
} finally { Stop-Transcript | Out-Null }
