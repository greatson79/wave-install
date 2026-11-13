#!/usr/bin/env python3
"""Gate A: executable launch commands and ASCII entry contract (source or asset)."""
import argparse
import json
import os
from pathlib import Path
import re
import shutil
import subprocess


def check(root):
    failures = []
    shell = os.environ.get('PWSH') or shutil.which('powershell') or shutil.which('pwsh')
    if not shell:
        return ['PowerShell parser required']
    parser = r'''
[Console]::OutputEncoding = [Text.UTF8Encoding]::new()
$tokens = $null; $errors = $null
$ast = [Management.Automation.Language.Parser]::ParseFile($env:WAVE_GATE_BOOTSTRAP, [ref]$tokens, [ref]$errors)
if ($errors.Count) { throw ($errors | Out-String) }
$commands = @($ast.FindAll({param($n) $n -is [Management.Automation.Language.CommandAst]}, $true) | ForEach-Object {
  $parent = $_.Parent
  while ($null -ne $parent -and $parent -isnot [Management.Automation.Language.FunctionDefinitionAst]) { $parent = $parent.Parent }
  @{ text = $_.Extent.Text; name = $_.GetCommandName(); helper = $(if ($parent) { $parent.Name } else { '' }) }
})
ConvertTo-Json -InputObject $commands -Compress
'''
    result = subprocess.run([shell, '-NoProfile', '-NonInteractive', '-Command', parser],
                            env=dict(os.environ, WAVE_GATE_BOOTSTRAP=str((root / 'bootstrap.ps1').resolve())),
                            capture_output=True, text=True, encoding='utf-8', timeout=30)
    if result.returncode:
        return ['PowerShell parse failed: ' + result.stderr.strip()]
    commands = json.loads(result.stdout.lstrip('\ufeff'))
    launches = [c for c in commands if (c['name'] or '').lower() == 'start-process']
    if len(launches) != 3 or any(not re.match(r'Start-Process -FilePath "\$env:SystemRoot\\System32\\cmd.exe" -ArgumentList ', c['text'], re.I) for c in launches):
        failures.append('all three Start-Process calls must launch the cmd helpers')
    for helper in ('Invoke-NsisSetup', 'Start-WaveDetached', 'Invoke-BoundedCheck'):
        if len([c for c in launches if c['helper'] == helper]) != 1:
            failures.append(helper + ': missing executable cmd launch')
    if any(re.match(r'&\s+\$(?:ArtifactPath|Setup|FilePath|cys|cysd|app)\b', c['text'], re.I) for c in commands):
        failures.append('direct executable invocation')
    entry = (root / 'win-start.ps1').read_bytes()
    if entry.startswith(b'\xef\xbb\xbf') or not entry.startswith(b'& {') or not entry.isascii():
        failures.append('win-start must be ASCII, BOM-free, and begin & {')
    return failures


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('root', type=Path)
    args = parser.parse_args()
    errors = check(args.root)
    print(('FAIL: ' + '; '.join(errors)) if errors else 'PASS: cmd helpers and ASCII entry')
    raise SystemExit(bool(errors))
