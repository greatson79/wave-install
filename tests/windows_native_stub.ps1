# Shared native test binaries; Framework csc works from both PS5.1 and PS7 hosts.
function New-NativeTestExecutable([string]$Path, [string]$Source) {
  New-Item -ItemType Directory -Force (Split-Path -Parent $Path) | Out-Null
  $sourcePath = $Path + '.cs'
  [IO.File]::WriteAllText($sourcePath, $Source)
  $compiler = Join-Path $env:SystemRoot 'Microsoft.NET/Framework64/v4.0.30319/csc.exe'
  & $compiler /nologo /target:exe ("/out:" + $Path) $sourcePath
  if ($LASTEXITCODE -ne 0) { throw 'native test executable compilation failed' }
}
