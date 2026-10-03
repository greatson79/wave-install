"""Exercise the literal irm URL | iex command in real Windows PowerShell 5.1."""
import hashlib
import json
import os
from pathlib import Path
import platform
import socket
import tempfile
import threading
import urllib.request

from serve_fixture import EXPECTED_SHA, PAYLOAD, FixtureServer
from windows_job import run_in_job, verify_timeout_tree


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def run():
    require(platform.system() == 'Windows', 'Windows required; pwsh is not a PS5.1 substitute')
    executable = Path(os.environ['SystemRoot']) / 'System32/WindowsPowerShell/v1.0/powershell.exe'
    require(executable.is_file(), 'Windows powershell.exe missing')
    tree_check = verify_timeout_tree()
    print('JOB_TIMEOUT_TREE=' + json.dumps(tree_check), flush=True)
    version = run_in_job([str(executable), '-NoProfile', '-Command',
        "if ($PSVersionTable.PSVersion.Major -ne 5 -or $PSVersionTable.PSVersion.Minor -ne 1) { exit 51 }; $PSVersionTable.PSVersion.ToString()"],
        timeout=30)
    require(version.returncode == 0, 'PS5.1 assertion failed: ' + repr(version.stdout))
    print('PARENT_PS51=' + version.stdout.decode('ascii').strip(), flush=True)
    require(hashlib.sha256(PAYLOAD).hexdigest() == EXPECTED_SHA, 'fixture pin drift')
    report = {'version': version.stdout.decode('ascii').strip(), 'job_timeout_tree': tree_check, 'cases': []}
    server = FixtureServer()
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with tempfile.TemporaryDirectory(prefix='wave-shortline-') as scratch:
            root = Path(scratch)
            env = os.environ.copy()
            # Native .NET temp directory and every installer-facing home are isolated.
            for key in ('HOME', 'USERPROFILE', 'TEMP', 'TMP', 'APPDATA', 'LOCALAPPDATA'):
                location = root / key
                location.mkdir()
                env[key] = str(location)
            # Both the command parent and the stub's unmodified powershell.exe child
            # resolve to Windows PowerShell, never a fixture/shim/pwsh executable.
            env['PATH'] = str(executable.parent) + os.pathsep + env['PATH']
            command = 'irm ' + server.base + '/win | iex'
            for mode in ('normal', 'corrupt', 'bootstrap404', 'interrupted', 'child7'):
                server.mode = mode
                server.requests.clear()
                if mode == 'corrupt':
                    with urllib.request.urlopen(urllib.request.Request(server.base + '/corrupt', data=b'', method='POST')) as response:
                        require(response.status == 200, 'corrupt switch failed')
                result = run_in_job([str(executable), '-NoProfile', '-Command', command],
                    cwd=root, env=env, timeout=60)
                # Markers are ASCII; console codepage never supplies the Unicode oracle.
                output = (result.stdout + result.stderr).decode('ascii', errors='backslashreplace')
                record = {'mode': mode, 'command': command, 'exit': result.returncode,
                          'requests': list(server.requests), 'output': output}
                report['cases'].append(record)
                print(json.dumps(record, ensure_ascii=True), flush=True)
                require(server.requests[:3] == ['/win', '/win-start.ps1', '/bootstrap.ps1'], mode + ': redirect/stub chain missing')
                if mode == 'normal':
                    require(result.returncode == 0, 'normal pipeline failed')
                    for marker in ('CHILD_PS51=5.1', 'BOM=EFBBBF', 'FILE_MODE=YES', 'UNICODE_OK', 'SHA_OK', 'FIXTURE_DONE'):
                        require(marker in output, 'missing marker: ' + marker)
                else:
                    require(result.returncode != 0, mode + ': failure did not reach caller')
                    require('FIXTURE_DONE' not in output, mode + ': completion marker leaked')
                    if mode == 'corrupt':
                        require('SHA_MISMATCH' in output, 'SHA rejection missing')
                        require('SHA_OK' not in output, 'corrupt digest accepted')
                    elif mode == 'child7':
                        require('CHILD_EXIT_7' in output and 'exit 7' in output, 'child exit 7 not propagated')
                    else:
                        if mode == 'interrupted':
                            require('BOOTSTRAP_SHA_MISMATCH' in output, 'partial bootstrap integrity rejection missing')
                        require('/payload' not in server.requests and 'CHILD_PS51=5.1' not in output,
                                mode + ': failed download executed bootstrap')
                for temp_key in ('TEMP', 'TMP'):
                    require(not list((root / temp_key).iterdir()), mode + ': ' + temp_key + ' temporary files leaked')
                record['assertions'] = 'PASS'
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
        with socket.socket() as check:
            report['port_closed'] = check.connect_ex(server.server_address) != 0
        report['thread_stopped'] = not thread.is_alive()
        Path('shortline-ps51-results.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    require(report['port_closed'] and report['thread_stopped'], 'fixture server leaked')
    print('SHORTLINE_PS51_PASS: normal, corrupt, bootstrap404, interrupted, child7', flush=True)


if __name__ == '__main__':
    run()
