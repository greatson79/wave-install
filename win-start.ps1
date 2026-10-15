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
    if ($code -eq 2) { $global:LASTEXITCODE = 2 } elseif ($code -ne 0) { throw "Wave installer failed (exit $code)." }
  } finally {
    if (Test-Path -LiteralPath $f) { Remove-Item -LiteralPath $f -Force }
    if (Test-Path -LiteralPath $d) { Remove-Item -LiteralPath $d }
  }
}
