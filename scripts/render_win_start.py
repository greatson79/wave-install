"""Render an ASCII short-line stub pinned to the final BOM bootstrap bytes."""
import argparse
import hashlib
from pathlib import Path
from urllib.parse import urlsplit

TEMPLATE = r'''& {
  $ErrorActionPreference = 'Stop'
  $ProgressPreference = 'SilentlyContinue'
  [Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12
  $d = Join-Path ([IO.Path]::GetTempPath()) ('wave-start-' + [guid]::NewGuid().ToString('N'))
  $null = New-Item -ItemType Directory -Path $d
  $f = Join-Path $d 'bootstrap.ps1'
  try {
    Invoke-WebRequest -UseBasicParsing -Uri '__URL__' -OutFile $f
    $actual = (Get-FileHash -Algorithm SHA256 -LiteralPath $f).Hash.ToLowerInvariant()
    if ($actual -ne '__SHA__') { throw 'BOOTSTRAP_SHA_MISMATCH' }
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $f
    if ($LASTEXITCODE -ne 0) { throw "Wave installer failed (exit $LASTEXITCODE)." }
  } finally {
    if (Test-Path -LiteralPath $f) { Remove-Item -LiteralPath $f -Force }
    if (Test-Path -LiteralPath $d) { Remove-Item -LiteralPath $d }
  }
}
'''


def render(content, url, *, fixture=False):
    parsed = urlsplit(url)
    loopback = fixture and parsed.scheme == 'http' and parsed.hostname == '127.0.0.1'
    if not parsed.netloc or (parsed.scheme != 'https' and not loopback):
        raise ValueError('HTTPS bootstrap URL required')
    if not url.isascii() or any(c in url for c in "'\r\n\x00"):
        raise ValueError('Unsafe bootstrap URL')
    if not content.startswith(b'\xef\xbb\xbf'):
        raise ValueError('Final bootstrap must include UTF-8 BOM')
    content[3:].decode('utf-8')
    digest = hashlib.sha256(content).hexdigest()
    return TEMPLATE.replace('__URL__', url).replace('__SHA__', digest).encode('ascii')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bootstrap', required=True, type=Path)
    parser.add_argument('--url', required=True)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    # Read only final release bytes. No network, no installer execution.
    args.output.write_bytes(render(args.bootstrap.read_bytes(), args.url))


if __name__ == '__main__':
    main()
