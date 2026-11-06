"""Run the built HTTP entry with both Windows shells and an old-BOM control."""
import functools
import hashlib
import http.server
import os
from pathlib import Path
import subprocess
import tempfile
import threading
import unittest
import zipfile


@unittest.skipUnless(os.name == 'nt' and os.environ.get('WAVE_BUILT_WIN_START'),
                     'requires Windows and the assembled WAVE_BUILT_WIN_START artifact')
class WinStartRuntimeTests(unittest.TestCase):
    def test_http_entry_both_shells_and_old_bom_control(self):
        built = Path(os.environ['WAVE_BUILT_WIN_START']).read_bytes()
        self.assertTrue(built.startswith(b'& {'), built[:8].hex(' '))
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            with zipfile.ZipFile(root / 'payload.zip', 'w') as archive:
                archive.writestr('payload.txt', 'fixture payload')
            stub = b"""$ErrorActionPreference = 'Stop'
Write-Host ('CHILD_PSModulePath=' + $env:PSModulePath)
$work = $env:WAVE_STUB_MARKER + '.work'
$null = New-Item -ItemType Directory -Path $work
try {
  $zip = Join-Path $work 'payload.zip'
  Invoke-WebRequest -UseBasicParsing -Uri ($env:WAVE_STUB_BASE + '/payload.zip') -OutFile $zip
  $hash = (Get-FileHash -Algorithm SHA256 -LiteralPath $zip).Hash
  if ($hash.Length -ne 64) { throw 'stub hash missing' }
  $out = Join-Path $work 'expanded'
  Expand-Archive -LiteralPath $zip -DestinationPath $out
  if ((Get-Content -Raw (Join-Path $out 'payload.txt')) -ne 'fixture payload') { throw 'stub expansion failed' }
  [IO.File]::WriteAllText($env:WAVE_STUB_MARKER, 'bootstrap reached')
  Write-Host 'PASS child Invoke-WebRequest, Get-FileHash, Expand-Archive'
} finally {
  Remove-Item -LiteralPath $work -Recurse -Force
}
exit 0
"""
            (root / 'bootstrap.ps1').write_bytes(stub)

            class Handler(http.server.SimpleHTTPRequestHandler):
                extensions_map = {'.ps1': 'text/plain; charset=utf-8'}

                def log_message(self, *args):
                    pass

            server = http.server.ThreadingHTTPServer(
                ('127.0.0.1', 0), functools.partial(Handler, directory=folder))
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                base = f'http://127.0.0.1:{server.server_port}'
                text = built.decode('ascii')
                # Only test pins change; the assembled executable body is preserved.
                import re
                text, urls = re.subn(r"(?<=-Uri ')[^']+(?=' -OutFile)", base + '/bootstrap.ps1', text)
                text, hashes = re.subn(r"(?<=-ne ')[0-9a-f]{64}(?=')", hashlib.sha256(stub).hexdigest(), text)
                self.assertEqual((urls, hashes), (1, 1))
                good = text.encode('ascii')
                (root / 'win-start.ps1').write_bytes(good)
                (root / 'old-bom.ps1').write_bytes(b'\xef\xbb\xbf' + good)
                for shell, negative in (('pwsh', False), ('powershell.exe', False), ('pwsh', True)):
                    with self.subTest(shell=shell, negative=negative):
                        marker = root / f'{shell}-{negative}.marker'
                        entry = 'old-bom.ps1' if negative else 'win-start.ps1'
                        # Continue lets the negative control inspect its failed background job.
                        command = f"""
$ErrorActionPreference = 'Continue'
Write-Host ('PARENT_PSModulePath=' + $env:PSModulePath)
irm '{base}/{entry}' | iex
$jobs = @(Get-Job)
Write-Host ('JOBS=' + $jobs.Count)
"""
                        if negative:
                            command += """
if ($jobs.Count -eq 0) { throw 'old BOM did not reproduce background job' }
$jobs | Wait-Job | Out-Null
$jobErrors = ($jobs | Receive-Job 2>&1 | Out-String)
Write-Host $jobErrors
if ($jobErrors -notmatch 'not recognized') { throw 'old BOM failed for an unrelated reason' }
if (Test-Path $env:WAVE_STUB_MARKER) { throw 'old BOM unexpectedly ran bootstrap' }
$jobs | Remove-Job -Force
Write-Host 'PASS old BOM reproduced: background job, bootstrap not reached'
exit 0
"""
                        else:
                            command += """
if ($jobs.Count -ne 0) { throw 'unexpected background job' }
if (-not (Test-Path $env:WAVE_STUB_MARKER)) { throw 'bootstrap marker missing' }
if ($LASTEXITCODE -ne 0) { throw 'bootstrap exit was not zero' }
Write-Host 'PASS bootstrap marker, exit 0, JOBS=0'
exit 0
"""
                        child_env = dict(os.environ, WAVE_STUB_MARKER=str(marker), WAVE_STUB_BASE=base)
                        if shell == 'powershell.exe':
                            # Model a directly opened PS5.1; PS7 and its bootstrap child keep their environment.
                            child_env.pop('PSMODULEPATH', None)
                        result = subprocess.run([shell, '-NoProfile', '-ExecutionPolicy', 'Bypass',
                                                 '-Command', command], capture_output=True, text=True,
                                                encoding='utf-8', errors='replace', timeout=60,
                                                env=child_env)
                        print(f'{shell} negative={negative}\n{result.stdout}\n{result.stderr}')
                        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                        self.assertEqual(marker.exists(), not negative)
                        if not negative:
                            self.assertEqual(marker.read_text(), 'bootstrap reached')
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=5)


if __name__ == '__main__':
    unittest.main(verbosity=2)
