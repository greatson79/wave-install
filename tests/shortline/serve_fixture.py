"""Loopback-only, inert installer fixture. Never imports/runs the real installer."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import socket

PAYLOAD = b'wave-shortline-fixture-v1\n'
# Locked literal: never derive expected digest from the bytes served by a test.
EXPECTED_SHA = 'ebd458ac6147aeb7f085795283c6b088467c2a7c9b22cbffce253f0fe750b300'
BOM = b'\xef\xbb\xbf'


def stub(base):
    return (r'''& {
  $ErrorActionPreference = 'Stop'
  $ProgressPreference = 'SilentlyContinue'
  [Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12
  $d = Join-Path ([IO.Path]::GetTempPath()) ('wave-start-' + [guid]::NewGuid().ToString('N'))
  $null = New-Item -ItemType Directory -Path $d
  $f = Join-Path $d 'bootstrap.ps1'
  try {
    Invoke-WebRequest -UseBasicParsing -Uri '__BASE__/bootstrap.ps1' -OutFile $f
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $f
    if ($LASTEXITCODE -ne 0) { throw "Wave installer failed (exit $LASTEXITCODE)." }
  } finally {
    if (Test-Path -LiteralPath $f) { Remove-Item -LiteralPath $f -Force }
    if (Test-Path -LiteralPath $d) { Remove-Item -LiteralPath $d }
  }
}
'''.replace('__BASE__', base)).encode('ascii')


def bootstrap(base, child_exit=False):
    script = r'''$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
if ($PSVersionTable.PSVersion.Major -ne 5 -or $PSVersionTable.PSVersion.Minor -ne 1) { throw 'CHILD_PS51_REQUIRED' }
Write-Output 'CHILD_PS51=5.1'
if (-not $PSCommandPath -or -not (Test-Path -LiteralPath $PSCommandPath)) { throw 'FILE_MODE_MISSING' }
Write-Output 'FILE_MODE=YES'
$bytes = [IO.File]::ReadAllBytes($PSCommandPath)
if ($bytes.Length -lt 3 -or $bytes[0] -ne 239 -or $bytes[1] -ne 187 -or $bytes[2] -ne 191) { throw 'BOM_MISSING' }
Write-Output 'BOM=EFBBBF'
$korean = '한글 정상'
$expected = @(54620, 44544, 32, 51221, 49345)
if ($korean.Length -ne $expected.Count) { throw 'UNICODE_LENGTH' }
for ($i=0; $i -lt $expected.Count; $i++) {
  if ([int][char]$korean[$i] -ne $expected[$i]) { throw 'UNICODE_CODEPOINT' }
}
Write-Output 'UNICODE_OK'
$payload = Join-Path (Split-Path -Parent $PSCommandPath) 'payload.bin'
try {
  Invoke-WebRequest -UseBasicParsing -Uri '__BASE__/payload' -OutFile $payload
  $actual = (Get-FileHash -Algorithm SHA256 -LiteralPath $payload).Hash.ToLowerInvariant()
  if ($actual -ne '__SHA__') { throw 'SHA_MISMATCH' }
  Write-Output 'SHA_OK'
} finally {
  if (Test-Path -LiteralPath $payload) { Remove-Item -LiteralPath $payload -Force }
}
__ENDING__
'''
    script = script.replace('__BASE__', base).replace('__SHA__', EXPECTED_SHA)
    script = script.replace('__ENDING__', "Write-Output 'CHILD_EXIT_7'; exit 7" if child_exit else "Write-Output 'FIXTURE_DONE'")
    return BOM + script.encode('utf-8')


class FixtureServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self):
        super().__init__(('127.0.0.1', 0), Handler)
        self.mode = 'normal'
        self.requests = []
        self.base = 'http://127.0.0.1:%s' % self.server_address[1]


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_):
        pass

    def reply(self, body, code=200, content_type='application/octet-stream'):
        self.send_response(code)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        if self.path == '/corrupt':
            self.server.mode = 'corrupt'
            self.reply(b'corrupted')
        else:
            self.reply(b'not found', 404)

    def do_GET(self):
        self.server.requests.append(self.path)
        if self.path == '/health':
            self.reply(b'ready')
        elif self.path == '/win':
            self.send_response(307)
            self.send_header('Location', self.server.base + '/win-start.ps1')
            self.send_header('Content-Length', '0')
            self.end_headers()
        elif self.path == '/win-start.ps1':
            self.reply(stub(self.server.base), content_type='text/plain; charset=us-ascii')
        elif self.path == '/bootstrap.ps1':
            if self.server.mode == 'bootstrap404':
                self.reply(b'not found', 404)
            elif self.server.mode == 'interrupted':
                body = bootstrap(self.server.base)
                self.send_response(200)
                self.send_header('Content-Length', str(len(body)))
                self.end_headers()
                self.wfile.write(body[:8])
                self.wfile.flush()
                self.connection.shutdown(socket.SHUT_RDWR)
                self.connection.close()
                self.close_connection = True
            else:
                self.reply(bootstrap(self.server.base, self.server.mode == 'child7'))
        elif self.path == '/payload':
            self.reply(PAYLOAD + b'tampered' if self.server.mode == 'corrupt' else PAYLOAD)
        else:
            self.reply(b'not found', 404)
