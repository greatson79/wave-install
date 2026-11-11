& {
  $ErrorActionPreference = 'Stop'
  $ProgressPreference = 'SilentlyContinue'
  [Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12
  $d = Join-Path ([IO.Path]::GetTempPath()) ('wave-start-' + [guid]::NewGuid().ToString('N'))
  $null = New-Item -ItemType Directory -Path $d
  $f = Join-Path $d 'bootstrap.ps1'
  try {
    Invoke-WebRequest -UseBasicParsing -Uri '__WAVE_BOOTSTRAP_URL__' -OutFile $f
    $actual = (Get-FileHash -Algorithm SHA256 -LiteralPath $f).Hash.ToLowerInvariant()
    if ($actual -ne '__WAVE_BOOTSTRAP_SHA256__') { throw 'BOOTSTRAP_SHA_MISMATCH' }
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $f
    $code = $LASTEXITCODE
    if ($code -ne 0 -and $code -ne 2) {
      # The installer can die without printing (e.g. killed mid-step), so always show where it stopped.
      $home2 = if ($env:WAVE_HOME) { $env:WAVE_HOME } else { Join-Path $env:USERPROFILE '.wave' }
      $log = Join-Path $home2 'install.log'
      if (Test-Path -LiteralPath $log) {
        Write-Host '--- last lines of install.log (show this to your instructor) ---'
        Get-Content -LiteralPath $log -Tail 15 -Encoding UTF8 | ForEach-Object { Write-Host $_ }
        Write-Host "--- full log: $log ---"
      }
    }
    if ($code -eq 2) { $global:LASTEXITCODE = 2 } elseif ($code -ne 0) { throw "Wave installer failed (exit $code)." }
  } finally {
    if (Test-Path -LiteralPath $f) { Remove-Item -LiteralPath $f -Force }
    if (Test-Path -LiteralPath $d) { Remove-Item -LiteralPath $d }
  }
}
