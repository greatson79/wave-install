# Shared native test binaries; Framework csc works from both PS5.1 and PS7 hosts.
function New-NativeTestExecutable([string]$Path, [string]$Source) {
  New-Item -ItemType Directory -Force (Split-Path -Parent $Path) | Out-Null
  $sourcePath = $Path + '.cs'
  [IO.File]::WriteAllText($sourcePath, $Source)
  $compiler = Join-Path $env:SystemRoot 'Microsoft.NET/Framework64/v4.0.30319/csc.exe'
  & $compiler /nologo /target:exe ("/out:" + $Path) $sourcePath
  if ($LASTEXITCODE -ne 0) { throw 'native test executable compilation failed' }
}

function New-ClaudeAuthStub([string]$ProfilePath) {
  New-NativeTestExecutable (Join-Path $ProfilePath '.local/bin/claude.exe') 'public class ClaudeAuthFixture { public static int Main(string[] args) { return args.Length == 2 && args[0] == "auth" && args[1] == "status" ? 0 : 91; } }'
}
