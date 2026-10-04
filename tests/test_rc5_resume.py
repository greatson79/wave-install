"""S04 이어받기: 임시 HOME의 실제 서명 앱/파일 해시로 검증한다."""
import json, os, plistlib, shutil, subprocess, tempfile, time, unittest
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]

class MacResume(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='rc5-resume-')
        self.home = Path(self.tmp.name); self.wave = self.home/'wave'
        self.wave.mkdir(); self.steps = self.home/'steps.json'
        self.config = json.loads((ROOT/'steps.json').read_text())
        self.steps.write_text(json.dumps(self.config))
        state = json.loads((ROOT/'install-state.json').read_text())
        state['status'] = 'failed'
        state['steps']['S04_INSTALL_LINK'].update(status='passed', exit_code=0, version=self.config['release']['version'])
        (self.wave/'install-state.json').write_text(json.dumps(state))
        (self.wave/'attempt-started').write_text(str(int(time.time())-10))
        self.lib = self.home/'bootstrap.sh'
        self.lib.write_text((ROOT/'bootstrap.sh').read_text().rsplit('\nmain "$@"',1)[0])
    def tearDown(self): self.tmp.cleanup()
    def run_sh(self, code):
        return subprocess.run(['bash','-c','source "$1"; STEPS_FILE="$2"; '+code,'test',str(self.lib),str(self.steps)],
                              env=dict(os.environ,HOME=str(self.home),WAVE_HOME=str(self.wave)),capture_output=True,text=True)
    def test_no_argument_resume_enables_step_skipping(self):
        r = self.run_sh('attempt_start; echo RESUME=$RESUME')
        self.assertEqual(r.returncode,0,r.stderr); self.assertIn('RESUME=1',r.stdout)
    def signed_app(self):
        app = self.wave/'apps/Wave Terminal.app'; binary = app/'Contents/MacOS'; binary.mkdir(parents=True)
        (app/'Contents/Info.plist').write_bytes(plistlib.dumps({'CFBundleExecutable':'cys','CFBundleIdentifier':'test.wave.resume','CFBundlePackageType':'APPL'}))
        for name in ('cys','cysd'): shutil.copy('/bin/echo',binary/name)
        subprocess.run(['codesign','--force','--deep','--sign','-',str(app)],check=True,capture_output=True)
        r = subprocess.run(['codesign','-dvvv',str(app)],capture_output=True,text=True,check=True)
        pin = next(line.split('=',1)[1] for line in r.stderr.splitlines() if line.startswith('CDHash='))
        for platform in ('macos_arm64','macos_x64'): self.config['release']['cdhash'][platform] = pin
        self.steps.write_text(json.dumps(self.config))
        (self.wave/'bin').mkdir()
        for name in ('cys','cysd'): (self.wave/'bin'/name).symlink_to(binary/name)
        return app
    @unittest.skipUnless(shutil.which('codesign'),'macOS codesign required')
    def test_resume_skips_only_intact_pinned_app(self):
        app = self.signed_app()
        r = self.run_sh('RESUME=1; can_resume_step S04_INSTALL_LINK passed')
        self.assertEqual(r.returncode,0,r.stderr)
        for p in ('macos_arm64','macos_x64'): self.config['release']['cdhash'][p] = '0'*40
        self.steps.write_text(json.dumps(self.config))
        self.assertNotEqual(self.run_sh('RESUME=1; can_resume_step S04_INSTALL_LINK passed').returncode,0)
        self.assertNotEqual(self.run_sh('RESUME=0; can_resume_step S04_INSTALL_LINK passed').returncode,0)
    @unittest.skipUnless(shutil.which('codesign'),'macOS codesign required')
    def test_tampered_bundle_and_wrong_link_do_not_skip(self):
        app = self.signed_app()
        link=self.wave/'bin/cysd'; link.unlink(); link.symlink_to('/bin/echo')
        self.assertNotEqual(self.run_sh('RESUME=1; can_resume_step S04_INSTALL_LINK passed').returncode,0)
        link.unlink(); link.symlink_to(app/'Contents/MacOS/cysd')
        (app/'Contents/Info.plist').write_bytes(b'changed')
        self.assertNotEqual(self.run_sh('RESUME=1; can_resume_step S04_INSTALL_LINK passed').returncode,0)
    @unittest.skipUnless(shutil.which('codesign'),'macOS codesign required')
    def test_main_skips_s04_only_after_real_fingerprint_matches(self):
        self.signed_app()
        harness = ('ensure_pack(){ :; }; load_config(){ :; }; show_help_notice(){ :; }; '
                   'show_permission_notice(){ :; }; init_state(){ :; }; help_progress(){ :; }; '
                   'mark_required_complete(){ :; }; mark_install_complete(){ :; }; '
                   'run_step(){ echo "RAN=$1"; }; main')
        r=self.run_sh(harness)
        self.assertEqual(r.returncode,0,r.stderr)
        self.assertNotIn('RAN=S04_INSTALL_LINK',r.stdout)
        self.assertIn('RAN=S07_INITIAL_FLEET',r.stdout)
        for platform in ('macos_arm64','macos_x64'): self.config['release']['cdhash'][platform]='0'*40
        self.steps.write_text(json.dumps(self.config))
        r=self.run_sh(harness)
        self.assertEqual(r.returncode,0,r.stderr)
        self.assertIn('RAN=S04_INSTALL_LINK',r.stdout)


class WindowsResume(unittest.TestCase):
    def test_app_hash_is_part_of_resume_fingerprint(self):
        pwsh = os.environ.get('PWSH') or shutil.which('pwsh')
        if not pwsh: self.skipTest('PWSH required')
        with tempfile.TemporaryDirectory(prefix='rc5-win-resume-') as td:
            r = subprocess.run([pwsh,'-NoProfile','-File',str(ROOT/'tests/windows_rc5_resume_fixture.ps1')],cwd=ROOT,
                               env=dict(os.environ,HOME=td,USERPROFILE=td,RC5_HOME=td),capture_output=True,text=True)
        self.assertEqual(r.returncode,0,r.stdout+r.stderr)
        self.assertIn('PASS app/CLI/daemon fingerprint',r.stdout)
