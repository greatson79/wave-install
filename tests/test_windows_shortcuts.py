"""Execute the real shortcut helper with injected folders and a file-backed COM stub."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
PWSH = os.environ.get('PWSH') or shutil.which('pwsh')


class WindowsShortcuts(unittest.TestCase):
    def run_shortcuts(self, existing=None, marker=False, missing_app=False, save_fails=False):
        self.assertTrue(PWSH, 'PWSH is required')
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            wave = root / 'wave'
            programs = root / 'Programs'
            desktop = root / 'Desktop'
            for directory in (wave / 'bin', programs, desktop):
                directory.mkdir(parents=True)
            target = wave / 'bin/wave-app.exe'
            if not missing_app:
                target.touch()
            # The old forwarder may coexist with the canonical GUI in real installs.
            (wave / 'bin/cys-app.exe').touch()
            links = {'flat': programs / 'Wave Terminal.lnk',
                     'nested': programs / 'Wave Terminal/Wave Terminal.lnk',
                     'desktop': desktop / 'Wave Terminal.lnk'}
            for name, executable in (existing or {}).items():
                links[name].parent.mkdir(parents=True, exist_ok=True)
                links[name].write_text(str(wave / 'bin' / executable))
            if marker:
                (wave / 'install').mkdir()
                (wave / 'install/desktop-shortcut').touch()
            source = (ROOT / 'bootstrap.ps1').read_text(encoding='utf-8-sig')
            helper = 'function Ensure-WaveShortcuts {' + source.split(
                'function Ensure-WaveShortcuts {', 1)[1].split('\nfunction ', 1)[0]
            helper = helper.replace("[Environment]::GetFolderPath('Programs')", '$env:TEST_PROGRAMS')
            helper = helper.replace("[Environment]::GetFolderPath('Desktop')", '$env:TEST_DESKTOP')
            harness = r'''
$ErrorActionPreference = 'Stop'
$WaveHome = $env:WAVE_HOME
$env:OS = 'Windows_NT'
$script:Saves = 0
$script:ShortcutReads = @()
function New-Object {
  param($ComObject)
  if ($ComObject -ne 'WScript.Shell') { throw 'unexpected COM request' }
  $shell = [pscustomobject]@{}
  $shell | Add-Member ScriptMethod CreateShortcut {
    param($path)
    $target = if (Test-Path -LiteralPath $path) { [IO.File]::ReadAllText($path) } else { '' }
    $script:ShortcutReads += @{path=$path; target=$target; normalized_target=$(if ($target) { [IO.Path]::GetFullPath($target) } else { '' })}
    $shortcut = [pscustomobject]@{Path=$path; TargetPath=$target}
    $shortcut | Add-Member ScriptMethod Save {
      $script:Saves++
      if ($env:TEST_SAVE_FAILS -ne '1') { [IO.File]::WriteAllText($this.Path, $this.TargetPath) }
    }
    return $shortcut
  }
  return $shell
}
'''
            script = root / 'harness.ps1'
            script.write_text(harness + helper + r'''
try {
  Ensure-WaveShortcuts
  @{error=''; saves=$script:Saves} | ConvertTo-Json -Compress
} catch {
  @{error=$_.Exception.Message; saves=$script:Saves; shortcut_reads=$script:ShortcutReads} | ConvertTo-Json -Compress -Depth 5
}
''', encoding='utf-8-sig')
            env = dict(os.environ, HOME=tmp, USERPROFILE=tmp, WAVE_HOME=str(wave),
                       TEST_PROGRAMS=str(programs), TEST_DESKTOP=str(desktop),
                       TEST_SAVE_FAILS='1' if save_fails else '0')
            result = subprocess.run([PWSH, '-NoProfile', '-NonInteractive', '-File', str(script)],
                                    env=env, capture_output=True, text=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            outcome = json.loads(result.stdout)
            if missing_app or save_fails:
                self.assertIn('실행 파일이 없습니다' if missing_app else '바로가기 대상이 다릅니다', outcome['error'])
                return
            self.assertEqual(outcome['error'], '', result.stdout + '\ninjected_root=' + str(root) + '\nexpected_target=' + str(target))
            expected = set(existing or {}) | ({'nested'} if 'nested' in (existing or {}) else {'flat'})
            if not marker:
                expected.add('desktop')
            for name in expected:
                original = (existing or {}).get(name)
                wanted = wave / 'bin/cys-app.exe' if original == 'cys-app.exe' else target
                self.assertEqual(links[name].read_text(), str(wanted), name)
            if marker and 'desktop' not in expected:
                self.assertFalse(links['desktop'].exists(), 'preserve learner-removed Desktop shortcut')
            return outcome['saves']

    def test_existing_canonical_links_are_kept(self):
        for location in ('flat', 'nested'):
            with self.subTest(location=location):
                self.assertEqual(self.run_shortcuts({location: 'wave-app.exe', 'desktop': 'wave-app.exe'}), 0)

    def test_old_forwarder_links_are_accepted(self):
        for location in ('flat', 'nested'):
            with self.subTest(location=location):
                self.assertEqual(self.run_shortcuts({location: 'cys-app.exe', 'desktop': 'cys-app.exe'}), 0)

    def test_other_targets_are_repaired(self):
        self.assertEqual(self.run_shortcuts({'flat': 'other.exe', 'desktop': 'other.exe'}), 2)

    def test_absent_links_are_created(self):
        self.assertEqual(self.run_shortcuts(), 2)

    def test_both_start_menu_links_are_repaired(self):
        self.assertEqual(self.run_shortcuts({'flat': 'cys-app.exe', 'nested': 'other.exe'}, marker=True), 1)

    def test_existing_desktop_is_repaired_despite_marker(self):
        self.assertEqual(self.run_shortcuts({'flat': 'wave-app.exe', 'desktop': 'other.exe'}, marker=True), 1)

    def test_marker_preserves_absent_desktop(self):
        self.assertEqual(self.run_shortcuts({'flat': 'wave-app.exe'}, marker=True), 0)

    def test_missing_canonical_executable_still_fails(self):
        self.run_shortcuts(missing_app=True)

    def test_unsaved_shortcut_still_fails_postcheck(self):
        self.run_shortcuts({'flat': 'other.exe'}, save_fails=True)


if __name__ == '__main__':
    unittest.main()
