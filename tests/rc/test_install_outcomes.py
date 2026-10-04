"""실제 rc.4 녹취 회귀: fixtures/install-outcomes/provenance.json 참조."""
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
                verdict, why = outcomes.check(FIX/'negative', 'win', gate)
                self.assertEqual(verdict, 'FAIL'); self.assertIn('exit=1', why)
    def test_official_normal_runs_pass(self):
        for osn in ('mac','win'):
            for gate in ('G1','G5'):
                self.assertEqual(outcomes.check(FIX/'positive',osn,gate)[0], 'PASS')
    def test_real_noboot_expected_two_is_test_pass_not_install_success(self):
        self.assertEqual(outcomes.check(FIX/'positive','win','noboot')[0], 'PASS')
    def test_missing_evidence_fails(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(outcomes.check(pathlib.Path(d),'win','G1')[0], 'FAIL')
    def test_exit_zero_cannot_mask_failed_stages(self):
        with tempfile.TemporaryDirectory() as d:
            root=pathlib.Path(d);shutil.copytree(FIX/'negative',root,dirs_exist_ok=True)
            shutil.copyfile(FIX/'positive/win/run.exit',root/'win/run.exit')
            self.assertEqual(outcomes.check(root,'win','G1')[0],'FAIL')
    def test_missing_state_fails_even_with_exit_zero(self):
        with tempfile.TemporaryDirectory() as d:
            root=pathlib.Path(d);(root/'win').mkdir()
            shutil.copyfile(FIX/'positive/win/run.exit',root/'win/run.exit')
            self.assertEqual(outcomes.check(root,'win','G1')[0],'FAIL')
    def test_exit_two_never_passes_normal_job(self):
        with tempfile.TemporaryDirectory() as d:
            root=pathlib.Path(d);shutil.copytree(FIX/'positive',root,dirs_exist_ok=True)
            shutil.copyfile(root/'win/noboot/exit',root/'win/run.exit')
            self.assertEqual(outcomes.check(root,'win','G1')[0],'FAIL')
    def test_table_existing_failure_is_preserved(self):
        rows=[{'id':'G1','win':['FAIL','기존 관문 실패']}]
        outcomes.strengthen(rows,FIX/'positive',('win',))
        self.assertEqual(rows[0]['win'][0],'FAIL')
    def test_table_false_pass_becomes_fail(self):
        rows=[{'id':g,'win':['PASS','기존 판정']} for g in ('G1','G5')]
        outcomes.strengthen(rows,FIX/'negative',('win',))
        self.assertTrue(all(r['win'][0]=='FAIL' for r in rows))
    def test_raw_table_includes_exit_and_stages(self):
        report=outcomes.raw_report(FIX/'negative')
        self.assertIn('| ./win/run.exit | 1 |',report)
        self.assertIn('S07=failed/1',report)

if __name__=='__main__':unittest.main()
