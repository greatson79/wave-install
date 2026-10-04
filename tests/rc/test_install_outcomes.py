"""실제 rc.4 녹취 회귀: fixtures/install-outcomes/provenance.json 참조."""
import json
import importlib.util
import pathlib
import shutil
import sys
import tempfile
import unittest
sys.path.insert(0, str(pathlib.Path(__file__).parent))
import install_outcomes as outcomes
FIX = pathlib.Path(__file__).parent / 'fixtures/install-outcomes'

class Outcomes(unittest.TestCase):
    def test_rc4_false_pass_is_rejected(self):
        for gate in ('G1', 'G5'):
            with self.subTest(gate=gate):
                verdict, why = outcomes.check(FIX/'negative', 'win', gate, schema='rc4')
                self.assertEqual(verdict, 'FAIL'); self.assertIn('exit=1', why)
    def test_official_normal_runs_pass(self):
        for osn in ('mac','win'):
            for gate in ('G1','G5'):
                self.assertEqual(outcomes.check(FIX/'positive',osn,gate,schema='rc4')[0], 'PASS')
    def test_real_noboot_expected_two_is_test_pass_not_install_success(self):
        self.assertEqual(outcomes.check(FIX/'positive','win','noboot',schema='rc4')[0], 'PASS')
    def test_non_ascii_or_signed_exit_fails(self):
        for raw in ('+0','-0','00','0_0','٠'):
            with self.subTest(raw=raw), tempfile.TemporaryDirectory() as d:
                root=pathlib.Path(d);shutil.copytree(FIX/'positive',root,dirs_exist_ok=True)
                (root/'win/run.exit').write_text(raw)
                self.assertEqual(outcomes.check(root,'win','G1',schema='rc4')[0],'FAIL')
    def test_invalid_state_mutations_fail(self):
        # 실물 녹취 복사본의 결함 주입. 새로운 외부 응답을 생성하지 않는다.
        mutations=[lambda d:d.update(status='failed'),lambda d:d.update(required_steps_passed=False)]
        for value in (False,0.0):
            mutations.append(lambda d,value=value:d['steps']['S07_INITIAL_FLEET'].update(exit_code=value))
        mutations += [lambda d:d['steps']['S07_INITIAL_FLEET'].update(observed=[]),
                      lambda d:d['steps']['S07_INITIAL_FLEET']['observed'].update(fleet_started=False),
                      lambda d:d['steps']['S07_INITIAL_FLEET']['observed'].update(master_awakened=False)]
        for mutate in mutations:
            with tempfile.TemporaryDirectory() as d:
                root=pathlib.Path(d);shutil.copytree(FIX/'positive',root,dirs_exist_ok=True)
                p=root/'win/G1_state.json';doc=json.loads(p.read_text(encoding='utf-8-sig'))
                mutate(doc);p.write_text(json.dumps(doc))
                self.assertEqual(outcomes.check(root,'win','G1',schema='rc4')[0],'FAIL')
    def test_rc5_recorded_s07_observation_and_mutations(self):
        obs=json.loads((FIX/'rc5-s07-observed.json').read_text())['observed']
        for change,want in (({},'PASS'),({'launch_complete':2},'FAIL'),({'launch_complete':True},'FAIL'),({'master_marker_present':None},'FAIL')):
            with tempfile.TemporaryDirectory() as d:
                root=pathlib.Path(d);shutil.copytree(FIX/'positive',root,dirs_exist_ok=True)
                p=root/'mac/G1_state.json';doc=json.loads(p.read_text())
                # 기존 실제 설치 상태의 S07만 실제 rc.5 함수 재생 출력으로 교체.
                doc['steps']['S07_INITIAL_FLEET']['observed']=dict(obs,**change)
                p.write_text(json.dumps(doc))
                self.assertEqual(outcomes.check(root,'mac','G1',schema='rc5')[0],want)
    def test_rc5_schema_rejects_rc4_keys_on_both_platforms(self):
        for osn,rel in (('mac','mac/G1_state.json'),('win','win/G1_state.json')):
            with self.subTest(os=osn), tempfile.TemporaryDirectory() as d:
                root=pathlib.Path(d);shutil.copytree(FIX/'positive',root,dirs_exist_ok=True)
                p=root/rel;doc=json.loads(p.read_text(encoding='utf-8-sig'))
                obs=doc['steps']['S07_INITIAL_FLEET']['observed']
                obs.pop('launch_complete',None);obs.pop('master_marker_present',None)
                obs['master_marker_verified']=True;obs['master_awakened']=True;obs['child_alive']=True;obs['cso_alive']=True
                p.write_text(json.dumps(doc))
                self.assertEqual(outcomes.check(root,osn,'G1',schema='rc5')[0],'FAIL')
                self.assertEqual(outcomes.check(root,osn,'G1',schema='rc4')[0],'PASS')
    def test_rc5_schema_rejects_missing_schema_and_unknown_schema(self):
        for schema in (None,'rc6'):
            with self.subTest(schema=schema):self.assertEqual(outcomes.check(FIX/'positive','mac','G1',schema=schema)[0],'FAIL')
    def test_rc5_noboot_cross_checks_raw_status_and_s08_claim(self):
        raw=FIX/'positive/rc5/cys-status.json'
        status=json.loads(raw.read_text())
        self.assertEqual({s['role'] for s in status['surfaces'] if s['launch_complete'] is True},{'master','cso','worker'})
        doc={'status':'complete','required_steps_passed':True,'steps':{
            'S07_INITIAL_FLEET':{'observed':{'fleet_started':True,'seats':3,'roles':['master','cso','worker'],'master_marker_present':False,'launch_complete':3}},
            'S08_VERIFY':{'observed':{'master_awake':'unconfirmed'}},
            'S09_COMPLETE':{'observed':{}}}}
        with tempfile.TemporaryDirectory() as d:
            base=pathlib.Path(d)/'mac/noboot';base.mkdir(parents=True)
            (base/'marker_absent').write_text('');(base/'cys-status.json').write_bytes(raw.read_bytes())
            from install_outcomes import RC5_BOOT_NOTICE, _check_rc5_noboot
            (base/'install.log').write_text('prefix '+RC5_BOOT_NOTICE+' suffix')
            self.assertIsNone(_check_rc5_noboot(base,doc,'test'))
            (base/'cys-status.json').write_text(json.dumps(dict(status,surfaces=[dict(x,launch_complete=False) if x['role']=='worker' else x for x in status['surfaces']])))
            reason=_check_rc5_noboot(base,doc,'test')[1]
            self.assertIn('원문 cys status 역할 신호 불일치',reason)
            self.assertIn("'role': 'worker'",reason);self.assertIn("'launch_complete': False",reason)
            self.assertNotIn('cwd',reason)
            (base/'cys-status.json').write_bytes(raw.read_bytes());doc['steps']['S08_VERIFY']['observed']['master_awake']='confirmed'
            self.assertIn('S08_VERIFY',_check_rc5_noboot(base,doc,'test')[1])
    def test_real_mac_noboot(self):
        self.assertEqual(outcomes.check(FIX/'positive','mac','noboot',schema='rc4')[0],'PASS')
    def test_missing_evidence_fails(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(outcomes.check(pathlib.Path(d),'win','G1',schema='rc4')[0], 'FAIL')
    def test_exit_zero_cannot_mask_failed_stages(self):
        with tempfile.TemporaryDirectory() as d:
            root=pathlib.Path(d);shutil.copytree(FIX/'negative',root,dirs_exist_ok=True)
            shutil.copyfile(FIX/'positive/win/run.exit',root/'win/run.exit')
            self.assertEqual(outcomes.check(root,'win','G1',schema='rc4')[0],'FAIL')
    def test_missing_state_fails_even_with_exit_zero(self):
        with tempfile.TemporaryDirectory() as d:
            root=pathlib.Path(d);(root/'win').mkdir()
            shutil.copyfile(FIX/'positive/win/run.exit',root/'win/run.exit')
            self.assertEqual(outcomes.check(root,'win','G1',schema='rc4')[0],'FAIL')
    def test_exit_two_never_passes_normal_job(self):
        with tempfile.TemporaryDirectory() as d:
            root=pathlib.Path(d);shutil.copytree(FIX/'positive',root,dirs_exist_ok=True)
            shutil.copyfile(root/'win/noboot/exit',root/'win/run.exit')
            self.assertEqual(outcomes.check(root,'win','G1',schema='rc4')[0],'FAIL')
    def test_table_existing_failure_is_preserved(self):
        rows=[{'id':'G1','win':['FAIL','기존 관문 실패']}]
        outcomes.strengthen(rows,FIX/'positive',('win',),('G1','G5'),schema='rc4')
        self.assertEqual(rows[0]['win'][0],'FAIL')
    def test_table_false_pass_becomes_fail(self):
        rows=[{'id':g,'win':['PASS','기존 판정']} for g in ('G1','G5')]
        outcomes.strengthen(rows,FIX/'negative',('win',),('G1','G5'),schema='rc4')
        self.assertTrue(all(r['win'][0]=='FAIL' for r in rows))
    def test_raw_table_includes_exit_and_stages(self):
        report=outcomes.raw_report(FIX/'negative')
        self.assertIn('| ./win/run.exit | 1 |',report)
        self.assertIn('S07=failed/1',report)

if __name__=='__main__':unittest.main()
