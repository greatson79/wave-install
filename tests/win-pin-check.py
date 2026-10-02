#!/usr/bin/env python3
"""Read release pins from steps.json; compare version/name/bytes/hash to release."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import sys
import tempfile
import urllib.request

ROOT = Path(__file__).resolve().parents[1]


def pins(path):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError('duplicate JSON key: ' + key)
            result[key] = value
        return result
    release = json.loads(path.read_text(encoding='utf-8-sig'), object_pairs_hook=unique)['release']
    version = release['version']
    size = release['bytes']['windows_x64']
    digest = release['sha256']['windows_x64']
    name = release['asset_name']['windows_x64']
    if not isinstance(version,str) or not re.fullmatch(r'[0-9]+\.[0-9]+\.[0-9]+', version):
        raise ValueError('unresolved version')
    if type(size) is not int or size <= 0:
        raise ValueError('invalid bytes')
    if not isinstance(digest,str) or not re.fullmatch('[a-f0-9]{64}', digest):
        raise ValueError('invalid SHA256')
    if name != f'wave-terminal-{version}-windows-x64-setup.exe':
        raise ValueError('filename-version mismatch')
    return dict(WaveVersion=version,WaveWinBytes=size,WaveWinSha256=digest,WaveWinFile=name)


def verify(values, directory):
    name = values['WaveWinFile']
    sums = directory/'SHA256SUMS'
    if not sums.is_file() or sums.is_symlink():
        raise ValueError('SHA256SUMS: missing or nonregular file')
    matches = []
    for line in sums.read_text(encoding='utf-8-sig').splitlines():
        match = re.fullmatch(r'([0-9a-fA-F]{64}) [ *](.+)', line)
        if match and match[2] == name:
            matches.append(match[1].lower())
    if len(matches) != 1:
        raise ValueError('manifest: exact asset row must occur once')
    asset = directory/name
    if asset.is_symlink() or not asset.is_file():
        raise ValueError('asset: missing or nonregular file')
    if asset.stat().st_size != values['WaveWinBytes']:
        raise ValueError('bytes mismatch')
    digest = hashlib.sha256()
    with asset.open('rb') as handle:
        for chunk in iter(lambda: handle.read(1024*1024), b''):
            digest.update(chunk)
    if digest.hexdigest() != values['WaveWinSha256'] or digest.hexdigest() != matches[0]:
        raise ValueError('SHA256 mismatch')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--steps', type=Path, default=ROOT/'steps.json')
    parser.add_argument('--release-dir', type=Path, help='local release layout; no claim of public release verification')
    args = parser.parse_args()
    values = pins(args.steps)
    if args.release_dir:
        verify(values, args.release_dir)
        print('PASS: local release/fixture pin matches (not public release evidence)')
    else:
        base = 'https://github.com/greatson79/wave-terminal/releases/download/v' + values['WaveVersion'] + '/'
        with tempfile.TemporaryDirectory(dir=ROOT, prefix='.pin-release-') as td:
            directory = Path(td)
            for name in ('SHA256SUMS', values['WaveWinFile']):
                request = urllib.request.Request(base + name, headers={'User-Agent': 'wave-install-pin-check'})
                with urllib.request.urlopen(request, timeout=60) as response, (directory/name).open('wb') as target:
                    if response.status != 200:
                        raise ValueError(f'{name}: HTTP {response.status}')
                    while True:
                        chunk = response.read(1024*1024)
                        if not chunk:
                            break
                        target.write(chunk)
            verify(values, directory)
        print('PASS: published Windows release pin matches ' + base)

if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        print(f'FAIL: {exc}', file=sys.stderr)
        sys.exit(1)
