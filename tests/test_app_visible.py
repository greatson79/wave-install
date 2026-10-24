import os
from pathlib import Path
import plistlib
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]


class AppVisibleTests(unittest.TestCase):
    def test_busy_old_app_waits_without_moving_it(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            old = home / '.wave/apps/Wave Terminal.app'
            old.mkdir(parents=True)
            lib = home / 'bootstrap-lib.sh'
            lib.write_text((ROOT / 'bootstrap.sh').read_text().rsplit('\nmain "$@"', 1)[0])
            command = 'source "$1"; wave_bundle_in_use() { return 0; }; set +e; wave_migrate_app "$HOME/Applications/Wave Terminal.app"; echo rc=$?'
            result = subprocess.run(['bash', '-c', command, 'test', str(lib)], env=dict(os.environ, HOME=tmp, WAVE_HOME=str(home / '.wave')), capture_output=True, text=True)
            self.assertIn('rc=2', result.stdout)
            self.assertIn('지금 열린 Wave Terminal', result.stderr)
            self.assertTrue(old.is_dir())
            self.assertFalse((home / 'Applications/Wave Terminal.app').exists())

    def test_old_app_moves_to_applications_and_shortcuts_are_only_added_once(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            old = home / '.wave/apps/Wave Terminal.app'
            (old / 'Contents/MacOS').mkdir(parents=True)
            (old / 'Contents/MacOS/cys').write_text('cys')
            (old / 'Contents/MacOS/cysd').write_text('cysd')
            (old / 'Contents/Info.plist').write_bytes(plistlib.dumps({'CFBundleIdentifier': 'com.waveainetworks.wave-terminal'}))
            (home / '.wave/bin').mkdir()
            (home / '.wave/bin/cysd').symlink_to(old / 'Contents/MacOS/cysd')
            (home / 'Desktop').mkdir()
            script = home / 'bootstrap-lib.sh'
            script.write_text((ROOT / 'bootstrap.sh').read_text().rsplit('\nmain "$@"', 1)[0])
            command = r'''
source "$1"
wave_bundle_in_use() { return 1; }
ditto() { cp -R "$1" "$2"; }
defaults() {
  if [[ "$1" == export ]]; then
    printf '%s' '<?xml version="1.0"?><plist version="1.0"><dict><key>persistent-apps</key><array/></dict></plist>'
  else
    printf 'write\n' >> "$HOME/dock-calls"
  fi
}
killall() { printf 'restart\n' >> "$HOME/dock-calls"; }
dest="$HOME/Applications/Wave Terminal.app"
wave_migrate_app "$dest"
wave_show_app "$dest"
[[ -d "$dest" && "$(readlink "$WAVE_HOME/apps/Wave Terminal.app")" == "$dest" ]]
[[ "$(readlink "$HOME/Desktop/Wave Terminal")" == "$dest" ]]
[[ "$(readlink "$WAVE_HOME/bin/cysd")" == "$WAVE_HOME/apps/Wave Terminal.app/Contents/MacOS/cysd" ]]
[[ -x "$WAVE_HOME/bin/cysd" || -f "$WAVE_HOME/bin/cysd" ]]
[[ -e "$WAVE_HOME/install/dock-pinned" && -e "$WAVE_HOME/install/desktop-shortcut" ]]
[[ "$(find "$WAVE_HOME/backups" -name cysd | wc -l | tr -d ' ')" == 1 ]]
[[ "$(wc -l < "$HOME/dock-calls" | tr -d ' ')" == 2 ]]
'''
            result = subprocess.run(['bash', '-c', command, 'test', str(script)], env=dict(os.environ, HOME=tmp, WAVE_HOME=str(home / '.wave')), capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_reinstall_message_starts_with_app_location(self):
        source = (ROOT / 'bootstrap.sh').read_text()
        self.assertEqual(source.count('fail_message "앱은 이미 설치돼 있습니다 — 응용 프로그램에서 Wave Terminal 을 여세요.'), 3)
        self.assertIn('앱은 이미 설치돼 있습니다 — 지금 열린 Wave Terminal 을 그대로 쓰시면 됩니다.', source)

    def test_windows_desktop_shortcut_uses_one_time_marker(self):
        source = (ROOT / 'bootstrap.ps1').read_text()
        shortcut = source.split('function Ensure-WaveShortcuts {', 1)[1].split('\nfunction ', 1)[0]
        self.assertIn("Join-Path $WaveHome 'install\\desktop-shortcut'", shortcut)
        self.assertIn('if (-not (Test-Path -LiteralPath $desktopMarker)) {', shortcut)
        self.assertIn('New-Item -ItemType File -Path $desktopMarker -Force', shortcut)

    def test_failed_copy_restores_previous_bundle(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            dest = home / 'Applications/Wave Terminal.app'
            backup = home / '.wave/backups/app-visible.1'
            dest.mkdir(parents=True)
            backup.mkdir(parents=True)
            (dest / 'broken').write_text('broken')
            (backup / 'Wave Terminal.app').mkdir()
            ((backup / 'Wave Terminal.app') / 'good').write_text('good')
            lib = home / 'bootstrap-lib.sh'
            lib.write_text((ROOT / 'bootstrap.sh').read_text().rsplit('\nmain "$@"', 1)[0])
            result = subprocess.run(['bash', '-c', 'source "$1"; wave_restore_app "$2" "$3"', 'test', str(lib), str(dest), str(backup)], env=dict(os.environ, HOME=tmp), capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue((dest / 'good').exists())
            self.assertTrue((backup / 'failed.app/broken').exists())

    def test_failed_shortcut_restores_old_app_and_allows_retry(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            old = home / '.wave/apps/Wave Terminal.app'
            old.mkdir(parents=True)
            (old / 'original').write_text('original')
            lib = home / 'bootstrap-lib.sh'
            lib.write_text((ROOT / 'bootstrap.sh').read_text().rsplit('\nmain "$@"', 1)[0])
            command = '''
source "$1"
wave_bundle_in_use() { return 1; }
ditto() { cp -R "$1" "$2"; }
wave_show_app() { ln -s "$1" "$WAVE_HOME/apps/Wave Terminal.app"; mkdir -p "$WAVE_HOME/install"; touch "$WAVE_HOME/install/desktop-shortcut"; ln -s "$1" "$HOME/Desktop/Wave Terminal"; return 1; }
wave_migrate_app "$HOME/Applications/Wave Terminal.app"
'''
            (home / 'Desktop').mkdir()
            result = subprocess.run(['bash', '-c', command, 'test', str(lib)], env=dict(os.environ, HOME=tmp, WAVE_HOME=str(home / '.wave')), capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertTrue((old / 'original').exists())
            self.assertFalse(old.is_symlink())
            self.assertFalse((home / 'Applications/Wave Terminal.app').exists())
            self.assertFalse((home / '.wave/install/desktop-shortcut').exists())
            self.assertFalse((home / 'Desktop/Wave Terminal').is_symlink())


if __name__ == '__main__':
    unittest.main()
