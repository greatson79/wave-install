"""S07 역할 시각 결속과 설치 이어받기 검증 회귀."""
import hashlib, json, os, shutil, subprocess, tempfile, unittest
from pathlib import Path
import test_rc5_resume as resume
ROOT=Path(__file__).resolve().parents[1]

from platform_scope import mac_only  # noqa: E402


class Binding(unittest.TestCase):
    def run_case(self, mode):
        pwsh=os.environ.get('PWSH') or shutil.which('pwsh')
        if not pwsh:self.skipTest('PWSH required')
        with tempfile.TemporaryDirectory(prefix='rc5-review-') as td:
            r=subprocess.run([pwsh,'-NoProfile','-File',str(ROOT/'tests/windows_rc5_binding_fixture.ps1'),'-Mode',mode],cwd=ROOT,
                env=dict(os.environ,HOME=td,USERPROFILE=td,RC5_HOME=td),text=True,capture_output=True)
        self.assertEqual(r.returncode,0,r.stdout+r.stderr)
    def test_old_children_are_rejected(self): self.run_case('old')
    def test_other_master_cannot_supply_signal(self): self.run_case('master')
    def test_missing_nonboolean_live_fields_and_invalid_roles(self): self.run_case('fields')

class ResumeReview(unittest.TestCase):
    def setUp(self):
        self.h=resume.MacResume(); self.h.setUp()
    def tearDown(self):self.h.tearDown()
    def artifact(self):
        h=self.h; body=b'verified artifact fixture'
        sha=hashlib.sha256(body).hexdigest()
        for p in ('macos_arm64','macos_x64'):h.config['release']['sha256'][p]=sha
        h.steps.write_text(json.dumps(h.config))
        file=h.wave/'downloads'/h.config['release']['asset_name']['macos_arm64'];file.parent.mkdir();file.write_bytes(body)
        state=json.loads((h.wave/'install-state.json').read_text())
        state['steps']['S03_DOWNLOAD_VERIFY'].update(status='passed',exit_code=0,version=h.config['release']['version'],observed={'bytes':len(body),'sha256':sha,'codesign_verified':True})
        (h.wave/'install-state.json').write_text(json.dumps(state))
        return file
    def test_preflight_install_and_login_are_always_rechecked(self):
        for step in ('S00_PREFLIGHT','S01_CLAUDE_INSTALL','S02_CLAUDE_LOGIN'):
            with self.subTest(step=step):self.assertNotEqual(self.h.run_sh('RESUME=1; can_resume_step '+step+' passed').returncode,0)
    @mac_only()
    def test_s03_rechecks_size_hash_and_requires_verified_record(self):
        file=self.artifact()
        code='RESUME=1; can_resume_step S03_DOWNLOAD_VERIFY passed'
        self.assertEqual(self.h.run_sh(code).returncode,0)
        state_path=self.h.wave/'install-state.json'
        state=json.loads(state_path.read_text())
        observed=state['steps']['S03_DOWNLOAD_VERIFY']['observed']
        size=observed.pop('bytes');state_path.write_text(json.dumps(state))
        self.assertNotEqual(self.h.run_sh(code).returncode,0,'old record without size skipped')
        observed['bytes']=size;state_path.write_text(json.dumps(state))
        file.write_bytes(b'x'*file.stat().st_size)
        self.assertNotEqual(self.h.run_sh(code).returncode,0,'same size different hash skipped')
        file.write_bytes(b'short')
        self.assertNotEqual(self.h.run_sh(code).returncode,0,'wrong size skipped')
    def test_s04_rechecks_dmg_before_mount(self):
        file=self.artifact();file.write_bytes(b'tampered')
        r=self.h.run_sh('require_command(){ :; }; wave_bundle_in_use(){ return 1; }; hdiutil(){ touch "$HOME/unsafe-mount"; return 9; }; step_s04')
        self.assertNotEqual(r.returncode,0)
        self.assertFalse((self.h.home/'unsafe-mount').exists(), 'tampered DMG reached hdiutil attach')
