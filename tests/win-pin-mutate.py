#!/usr/bin/env python3
"""Exercise the actual release checker, including a positive measured fixture."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
with tempfile.TemporaryDirectory(dir=ROOT, prefix='.pin-mutate-') as td:
    directory = Path(td)
    artifact = directory/'wave-terminal-1.2.3-windows-x64-setup.exe'
    data = b'fixture, not an installer\n'
    digest = hashlib.sha256(data).hexdigest()
    installer = directory/'steps.json'
    baseline = json.dumps({'release':{'version':'1.2.3','bytes':{'windows_x64':len(data)},'sha256':{'windows_x64':digest},'asset_name':{'windows_x64':artifact.name}}})
    manifest = directory/'SHA256SUMS'
    manifest_text = f'{digest}  {artifact.name}\n'
    cases = [
        ('baseline', baseline, data, manifest_text, True, ''),
        ('version', baseline.replace('1.2.3', '1.2.4'), data, manifest_text, False, 'exact asset'),
        ('bytes', baseline.replace(str(len(data)), str(len(data)+1)), data, manifest_text, False, 'bytes mismatch'),
        ('sha256', baseline.replace(digest, '0'*64), data, manifest_text, False, 'SHA256 mismatch'),
        ('duplicate', baseline.replace('"version":', '"version":"1.2.3","version":'), data, manifest_text, False, 'duplicate JSON key'),
        ('computed-pin', baseline.replace(str(len(data)), '"12 + 12"'), data, manifest_text, False, 'invalid bytes'),
        ('filename-version', baseline.replace(artifact.name, 'wave-terminal-9.9.9-windows-x64-setup.exe'), data, manifest_text, False, 'filename-version'),
        ('file-mutated', baseline, b'X'*len(data), manifest_text, False, 'SHA256 mismatch'),
        ('duplicate-sums', baseline, data, manifest_text*2, False, 'exact asset'),
        ('prefix-match', baseline, data, manifest_text.replace(artifact.name, artifact.name+'.other'), False, 'exact asset'),
        ('manifest-hash', baseline, data, manifest_text.replace(digest, '0'*64), False, 'SHA256 mismatch'),
        ('missing-asset', baseline, None, manifest_text, False, 'missing'),
        ('missing-sums', baseline, data, None, False, 'missing'),
    ]
    for name, source, payload, sums, accepted, reason in cases:
        installer.write_text(source)
        if payload is None:
            artifact.unlink(missing_ok=True)
        else:
            artifact.write_bytes(payload)
        if sums is None:
            manifest.unlink(missing_ok=True)
        else:
            manifest.write_text(sums)
        result = subprocess.run([sys.executable, str(ROOT/'tests/win-pin-check.py'), '--steps', str(installer), '--release-dir', str(directory)], capture_output=True, text=True)
        if (result.returncode == 0) != accepted or (not accepted and reason not in result.stderr):
            raise SystemExit(f'FAIL mutant {name}: {result.stdout}{result.stderr}')
        print(f'PASS: {name}')
