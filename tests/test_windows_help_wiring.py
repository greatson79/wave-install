"""R5 Windows bootstrap wiring: notice gate before Send-Progress, final-failure help, fail-open exit code.

Runs the real bootstrap.ps1 main path under pwsh with Invoke-ProgressPost / Invoke-HelpHttp test doubles.
pwsh on macOS proves script logic only, not Windows PowerShell 5.1 networking.
"""
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
PWSH = os.environ.get('PWSH') or shutil.which('pwsh')

OVERRIDES = r'''
# 5.1 의 Add-Content 기본 인코딩은 ANSI 라 '·' 같은 글자가 파이썬의 utf-8 읽기를 깨뜨린다 → 항상 UTF-8(무 BOM)로 덧붙인다
function Add-RecLine([string]$Line) { [IO.File]::AppendAllText($env:REC, $Line + "`n", [Text.UTF8Encoding]::new($false)) }
function Ensure-Pack { }
function Run-S00 { Say 'ACTION-S00' }
function Run-S01 { throw 'boom alice@example.com C:\Users\alice\x' }
if ($env:REAL_TRANSPORT -eq '1' -and $env:WAVE_HELP_BASE_URL -notmatch '^https://127\.0\.0\.1:\d+$') { $env:WAVE_NO_PROGRESS = '1' }
if ($env:REAL_TRANSPORT -ne '1') {
function Invoke-ProgressPost {
  param($Uri, $Body, $TimeoutMs)
  Add-RecLine (@{ kind = 'progress'; timeout_ms = $TimeoutMs; body = [Text.Encoding]::UTF8.GetString($Body) } | ConvertTo-Json -Compress)
  if ($env:FAKE_DOWN -eq '1') { throw 'network down' }
}
function Invoke-HelpHttp([string]$Method, [string]$Path, $Body, [string]$Token, [int]$TimeoutSec) {
  Add-RecLine (@{ kind = 'help'; method = $Method; path = $Path; timeout = $TimeoutSec; body = ($Body | ConvertTo-Json -Compress -Depth 5) } | ConvertTo-Json -Compress)
  if ($env:FAKE_DOWN -eq '1') { throw 'help down' }
  return @{ status = 201; body = @{ id = ('c' * 32); client_token = ('b' * 64) } }
}
}
'''


@unittest.skipUnless(PWSH, 'PowerShell is required')
class WindowsHelpWiringTests(unittest.TestCase):
    def run_boot(self, **extra):
        tmp = tempfile.TemporaryDirectory(dir=ROOT, prefix='.r5-win-')
        self.addCleanup(tmp.cleanup)
        home = Path(tmp.name)
        for name in ('steps.json', 'install-state.json'):
            shutil.copyfile(ROOT / name, home / name)
        shutil.copytree(ROOT / 'lib', home / 'lib')
        # Safety net: in this test copy the production default endpoint points at a closed loopback port.
        ps_lib = home / 'lib/install-help.ps1'
        ps_lib.write_text(ps_lib.read_text(encoding='utf-8').replace('https://waveainetworks.com', 'https://127.0.0.1:9'), encoding='utf-8')
        source = (ROOT / 'bootstrap.ps1').read_text(encoding='utf-8-sig')
        source = source.replace('$ErrorActionPreference = "Stop"', '$ErrorActionPreference = "Stop"\n[Console]::OutputEncoding = [Text.UTF8Encoding]::new()')
        source = source.replace('https://waveainetworks.com', 'https://127.0.0.1:9')
        marker = '\nLoad-Config\nif ($DryRun)'
        self.assertEqual(source.count(marker), 1)
        (home / 'bootstrap.ps1').write_text(source.replace(marker, OVERRIDES + marker), encoding='utf-8-sig')
        rec = home / 'rec.jsonl'
        env = dict(os.environ, USERPROFILE=str(home), WAVE_HOME=str(home / 'wave'), REC=str(rec),
                   WAVE_NO_PROGRESS='0', USERNAME='alice')
        env.pop('WAVE_PROGRESS_URL', None); env.pop('WAVE_HELP_BASE_URL', None)
        env.update(extra)
        if env.get('REAL_TRANSPORT') == '1':  # real transport only ever aims at a loopback port with no listener
            self.assertRegex(env.get('WAVE_HELP_BASE_URL', ''), r'^https://127\.0\.0\.1:\d+$')
        result = subprocess.run([PWSH, '-NoProfile', '-NonInteractive', '-File', str(home / 'bootstrap.ps1')],
                                env=env, capture_output=True, text=True, encoding='utf-8', timeout=120,
                                stdin=subprocess.DEVNULL)
        records = [json.loads(x) for x in rec.read_text(encoding='utf-8-sig').splitlines()] if rec.exists() else []
        state = json.loads((home / 'wave/install-state.json').read_text(encoding='utf-8-sig'))
        return result, records, state

    def test_failure_sends_progress_after_notice_then_help_and_exits_1(self):
        result, records, state = self.run_boot()
        out = result.stdout + result.stderr
        self.assertEqual(result.returncode, 1, out)
        self.assertIn('30일', out)
        self.assertLess(out.index('30일'), out.index('ACTION-S00'))
        progress = [json.loads(r['body']) for r in records if r['kind'] == 'progress']
        self.assertEqual([(p['step'], p['event']) for p in progress], [('1/10', 'start'), ('1/10', 'end'), ('2/10', 'start'), ('2/10', 'fail')])
        # G8 R1: progress goes through Invoke-ProgressPost (wall-clock 3000ms; no-redirect is pinned in test_g8r1_regressions).
        self.assertTrue(all(r['timeout_ms'] == 3000 for r in records if r['kind'] == 'progress'))
        self.assertEqual(progress[0]['installer_version'], json.loads((ROOT / 'steps.json').read_text())['version'])
        self.assertRegex(progress[-1].get('detail', ''), r'^J-[A-Z0-9]{2,8}-\d{2,3}$')
        helps = [r for r in records if r['kind'] == 'help']
        self.assertEqual([(h['method'], h['path'], h['timeout']) for h in helps], [('POST', '/api/help', 20)])  # non-interactive: no polling
        payload = json.loads(helps[0]['body'])
        self.assertEqual((payload['os'], payload['step'], payload['notice_shown']), ('win', '2/10', True))
        self.assertEqual(payload['code'], progress[-1]['detail'])
        self.assertIn('boom', payload['log_tail'])
        for leak in ('alice', 'example.com'):
            self.assertNotIn(leak, helps[0]['body'])
        self.assertIn('접수번호: cccccccc', out)
        self.assertNotIn('b' * 64, out)
        self.assertEqual(state['steps']['S01_CLAUDE_INSTALL']['status'], 'failed')

    def test_server_down_keeps_exit_code_and_state(self):
        down, records, down_state = self.run_boot(FAKE_DOWN='1')
        off, off_records, off_state = self.run_boot(WAVE_NO_PROGRESS='1')
        self.assertEqual(down.returncode, 1, down.stdout + down.stderr)
        self.assertEqual(off.returncode, 1, off.stdout + off.stderr)
        self.assertTrue(records)
        self.assertEqual(off_records, [])
        self.assertNotIn('30일', off.stdout + off.stderr)
        strip = lambda s: {k: (v['status'], v['exit_code'], v['error_id']) for k, v in s['steps'].items()}
        self.assertEqual(strip(down_state), strip(off_state))
        self.assertEqual((down.stdout + down.stderr).count('progress send failed (fail-open)'), 1)
        self.assertNotIn('help down', down.stdout + down.stderr)

    def test_real_transport_against_dead_loopback_port_is_fail_open(self):
        with socket.socket() as sock:
            sock.bind(('127.0.0.1', 0)); port = sock.getsockname()[1]
        free = lambda: socket.socket().connect_ex(('127.0.0.1', port)) != 0
        self.assertTrue(free())
        result, records, state = self.run_boot(REAL_TRANSPORT='1', WAVE_HELP_BASE_URL=f'https://127.0.0.1:{port}')
        self.assertTrue(free())
        out = result.stdout + result.stderr
        self.assertEqual(result.returncode, 1, out)
        self.assertEqual(records, [])
        self.assertIn('도움 요청을 보내지 못했습니다', out)
        self.assertEqual(out.count('progress send failed (fail-open)'), 1)
        self.assertEqual(state['steps']['S01_CLAUDE_INSTALL']['status'], 'failed')


if __name__ == '__main__':
    unittest.main()
