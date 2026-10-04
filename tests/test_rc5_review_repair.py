"""독립 대조 지적: 실물 녹취의 명시적 변이와 격리 파일로 재현."""
import hashlib, json, os, shutil, subprocess, tempfile, unittest
from pathlib import Path
import test_rc5_resume as resume
ROOT=Path(__file__).resolve().parents[1]

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
