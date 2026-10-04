"""rc.5: 표지와 지침 완료 신호 분리, 실패 진단은 종료값을 바꾸지 않는다."""
import json, os, subprocess, tempfile, unittest
from pathlib import Path
from test_rc4_s07 import S07Base, ROOT, real

class SignalCompatibility(S07Base):
    def test_old_app_with_marker_is_still_unconfirmed(self):
        self.status(['master','cso','worker'])
        (self.home/'.cys/.master-bootstrapped').write_text(json.dumps({'surface_ref':self.master_ref,'orchestra_check':'exit 0'}))
        r=self.bash('verify_live_fleet "$(cat "$WAVE_HOME/master_ref")" 0; echo RC=$?')
        self.assertIn('RC=1',r.stdout,r.stderr)
        r=self.run_s07({'WAVE_AWAKENING_SECONDS':'3'})
        self.assertIn('RC=2',r.stdout,r.stderr)
        self.assertIn('J-VER-04',r.stdout+r.stderr)
    def test_failure_snapshot_keeps_raw_status_and_role_refs(self):
        self.status(['master','cso','worker'])
        recorded_list=real('rc5_three_list.json')
        (self.wave/'list.txt').write_text(recorded_list)
        cli=self.wave/'bin/cys'
        cli.write_text(cli.read_text().replace('case "$1" in', 'case "$1" in\n  list) cat "$D/list.txt" ;;'))
        r=self.bash('capture_s07_evidence 2; echo RC=$?')
        self.assertIn('RC=0',r.stdout,r.stderr)
        self.assertIn('이 폴더는 이 컴퓨터에만 저장됩니다.',r.stderr)
        dirs=list((self.wave/'fleet').glob('failure-*'))
        self.assertEqual(len(dirs),1)
        self.assertEqual((dirs[0]/'list.txt').read_text(),recorded_list)
        self.assertEqual((dirs[0]/'status.json').read_bytes(),(self.wave/'status.json').read_bytes())
        seats=json.loads((dirs[0]/'roles.json').read_text())
        self.assertEqual({s['role'] for s in seats},{'master','cso','worker'})
        self.assertTrue(all(s['surface_ref'] and s['agent_alive'] is True for s in seats))
        self.assertEqual(json.loads((dirs[0]/'result.json').read_text())['installer_exit_code'],2)
    def test_snapshot_command_failure_is_nonfatal(self):
        r=self.bash('bounded_cys(){ return 9; }; capture_s07_evidence 1; echo RC=$?')
        self.assertIn('RC=0',r.stdout,r.stderr)
        dirs=list((self.wave/'fleet').glob('failure-*'))
        self.assertEqual(len(dirs),1)
        report=json.loads((dirs[0]/'result.json').read_text())
        self.assertEqual(report['status_exit_code'],9)
        self.assertEqual(report['list_exit_code'],9)
        self.assertEqual(report['installer_exit_code'],1)

    def test_step_failure_keeps_exit_one_or_two_even_when_diagnostics_fail(self):
        for code in (1,2):
            with self.subTest(code=code):
                r=self.bash('STEPS_FILE="$SCRIPT_DIR/steps.json"; help_progress(){ :; }; state_patch(){ :; }; step_error_id(){ echo WT-S07-FLEET; }; '
                            'step_s07(){ return '+str(code)+'; }; capture_s07_evidence(){ return 7; }; '
                            'run_step S07_INITIAL_FLEET')
                self.assertEqual(r.returncode,code,r.stdout+r.stderr)

class WindowsSignal(unittest.TestCase):
    def run_mode(self,mode):
        import shutil
        pwsh=os.environ.get('PWSH') or shutil.which('pwsh')
        if not pwsh: self.skipTest('PWSH required')
        with tempfile.TemporaryDirectory(prefix='rc5-s07-win-') as td:
            return subprocess.run([pwsh,'-NoProfile','-File',str(ROOT/'tests/windows_rc5_s07_fixture.ps1'),'-Mode',mode],cwd=ROOT,
                                  env=dict(os.environ,HOME=td,USERPROFILE=td,RC5_HOME=td),capture_output=True,text=True)
    def test_old_app_marker_is_not_injection_signal(self):
        r=self.run_mode('old'); self.assertEqual(r.returncode,0,r.stdout+r.stderr)
    def test_diagnostic_failure_does_not_change_result(self):
        r=self.run_mode('evidence'); self.assertEqual(r.returncode,0,r.stdout+r.stderr)

class RecordedSignal(S07Base):
    def load_recording(self,name):
        data=real(name)
        (self.wave/'fleet/status.json').write_text(json.dumps(data))
        self.ref=next(s['surface_ref'] for s in data['surfaces'] if s['role']=='master')
        return data
    def verify(self):
        return self.bash('verify_live_fleet '+self.ref+' 0; echo RC=$?')
    def test_recorded_three_roles_pass_without_marker(self):
        self.load_recording('rc5_three_status.json')
        self.assertIn('RC=0',self.verify().stdout)
        (self.home/'.cys/.master-bootstrapped').write_text('malformed observational marker')
        self.assertIn('RC=0',self.verify().stdout)
    def test_real_partial_recording_does_not_pass(self):
        self.load_recording('rc5_partial_status.json')
        self.assertIn('RC=1',self.verify().stdout)
    def test_each_role_needs_live_boolean_true_on_the_same_seat(self):
        for role in ('master','cso','worker'):
            for field,value in [('launch_complete',False),('launch_complete',None),('launch_complete','true'),('agent_alive',False),('exited',True)]:
                with self.subTest(role=role,field=field,value=value):
                    data=self.load_recording('rc5_three_status.json')
                    next(s for s in data['surfaces'] if s['role']==role)[field]=value
                    (self.wave/'fleet/status.json').write_text(json.dumps(data))
                    self.assertIn('RC=1',self.verify().stdout)
    def test_same_format_passes_in_powershell_strict_mode(self):
        import shutil
        pwsh=os.environ.get('PWSH') or shutil.which('pwsh')
        if not pwsh:self.skipTest('PWSH required')
        r=subprocess.run([pwsh,'-NoProfile','-File',str(ROOT/'tests/windows_rc5_s07_fixture.ps1'),'-Mode','signals'],cwd=ROOT,
                         env=dict(os.environ,HOME=str(self.home),USERPROFILE=str(self.home),RC5_HOME=str(self.home)),capture_output=True,text=True)
        self.assertEqual(r.returncode,0,r.stdout+r.stderr)
