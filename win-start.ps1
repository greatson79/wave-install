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
      if ($code -eq 1) {
        $hasFailure = $false
        $failureText = -join ([char[]](49892,54056,32,50896,47928))
        if (Test-Path -LiteralPath $log) {
          foreach ($line in (Get-Content -LiteralPath $log -Encoding UTF8)) {
            if ($line -match '\[\d+/10\]') { $hasFailure = $false }
            if ($line.Contains($failureText)) { $hasFailure = $true }
          }
        }
        if (-not $hasFailure) { Write-Host (-join ([char[]](50504,47017,32,83,97,102,101,32,84,114,97,110,115,97,99,116,105,111,110,40,65,83,84,120,41,183,86,51,183,50508,50557,58,32,51089,50629,32,54364,49884,51460,50640,49436,32,39,51333,47308,39,47564,51004,47196,45716,32,48512,51313,54624,32,49688,32,51080,49845,45768,45796,59,32,49444,52824,54616,45716,32,46041,50504,32,54644,45817,32,48372,50504,32,54532,47196,44536,47016,51032,32,50696,50808,32,46321,47197,32,46608,45716,32,51104,49884,32,51228,44144,32,54980,32,44057,51008,32,47749,47161,51012,32,45796,49884,32,49892,54665,54616,49464,50836,59,32,49444,52824,44032,32,45149,45208,47732,32,45796,49884,32,53020,44144,45208,32,49444,52824,54616,49464,50836,46))) }
      }
    }
    if ($code -eq 2) { $global:LASTEXITCODE = 2 } elseif ($code -ne 0) { throw "Wave installer failed (exit $code)." }
  } finally {
    if (Test-Path -LiteralPath $f) { Remove-Item -LiteralPath $f -Force }
    if (Test-Path -LiteralPath $d) { Remove-Item -LiteralPath $d }
  }
}
