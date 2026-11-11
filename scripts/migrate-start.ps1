& {
  $ErrorActionPreference = 'Stop'
  $ProgressPreference = 'SilentlyContinue'
  [Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12
  $url = if ($env:WAVE_MIGRATE_PS1_URL) { $env:WAVE_MIGRATE_PS1_URL } else { 'https://waveainetworks.com/migrate.ps1' }
  $d = Join-Path ([IO.Path]::GetTempPath()) ('wave-migrate-' + [guid]::NewGuid().ToString('N'))
  $null = New-Item -ItemType Directory -Path $d
  $f = Join-Path $d 'migrate.ps1'
  try {
    $uri = [uri]$url
    if ($uri.IsFile) { [IO.File]::Copy($uri.LocalPath, $f) }
    else { Invoke-WebRequest -UseBasicParsing -Uri $url -OutFile $f }
    $actual = (Get-FileHash -Algorithm SHA256 -LiteralPath $f).Hash.ToLowerInvariant()
    if ($actual -ne '__WAVE_MIGRATE_PS1_SHA256__') { throw 'MIGRATE_SHA_MISMATCH' }
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $f -DryRun
    if ($LASTEXITCODE -ne 0) { throw "Migration preview failed (exit $LASTEXITCODE)." }
    $answer = if (Test-Path Env:WAVE_MIGRATE_ANSWER) { $env:WAVE_MIGRATE_ANSWER }
              else { Read-Host (-join ([char[]](50734,44600,44620,50836,63,32,40,89,47,78,41))) }
    if ($answer -ceq 'Y' -or $answer -ceq 'y') {
      & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $f
      if ($LASTEXITCODE -ne 0) { throw "Migration failed (exit $LASTEXITCODE)." }
    } else { Write-Host (-join ([char[]](50500,47924,44163,46020,32,48320,44221,54616,51648,32,50506,50520,49845,45768,45796,46))) }
    $global:LASTEXITCODE = 0
  } finally {
    if (Test-Path -LiteralPath $f) { Remove-Item -LiteralPath $f -Force }
    if (Test-Path -LiteralPath $d) { Remove-Item -LiteralPath $d }
  }
}
