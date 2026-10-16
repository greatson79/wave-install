import hashlib,json,os,subprocess,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
class OriginalTests(unittest.TestCase):
    def test_s06_keeps_custom_directive_and_one_sidecar_on_two_runs(self):
        with tempfile.TemporaryDirectory() as td:
            home=Path(td);pack=home/'.cys/pack';wave=home/'wave';(pack/'directives').mkdir(parents=True);(wave/'bin').mkdir(parents=True)
            target=pack/'directives/MASTER_DIRECTIVE.md';target.write_text('student edit');before=hashlib.sha256(target.read_bytes()).hexdigest()
            embedded=b'vendor';manifest=home/'manifest.json';manifest.write_text(json.dumps({'files':{'directives/MASTER_DIRECTIVE.md':hashlib.sha256(embedded).hexdigest()}}))
            lib=home/'lib.sh';lib.write_text((ROOT/'bootstrap.sh').read_text().rsplit('\nmain "$@"',1)[0])
            command='source "$1"; SCRIPT_DIR="$2"; bounded_cys() { if [[ "$1" == init-pack ]]; then printf vendor > "$PACK_HOME/directives/MASTER_DIRECTIVE.md.new"; else cat "$G3_FIXTURE_MANIFEST"; fi; }; step_s06; step_s06'
            result=subprocess.run(['bash','-c',command,'fixture',str(lib),td],env=dict(os.environ,HOME=td,WAVE_HOME=str(wave),G3_FIXTURE_MANIFEST=str(manifest)),text=True,capture_output=True,timeout=5)
            self.assertEqual(result.returncode,0,result.stderr)
            self.assertEqual(result.stdout.count('직접 고치신 파일 1개는 그대로 두었습니다'),2)
            self.assertEqual(hashlib.sha256(target.read_bytes()).hexdigest(),before)
            self.assertEqual(len(list(pack.rglob('*.new'))),1)

    def test_large_original_and_custom_files_are_reported(self):
        with tempfile.TemporaryDirectory() as td:
            home=Path(td);pack=home/'.cys/pack';wave=home/'wave';(pack/'directives').mkdir(parents=True);(wave/'verify').mkdir(parents=True);(wave/'bin').mkdir()
            files={};roles={}
            for role in ('master','cso','worker'):
                data=(role+'\n').encode()*6000
                rel='directives/'+role.upper()+'_DIRECTIVE.md';(pack/rel).write_bytes(data);h=hashlib.sha256(data).hexdigest();files[rel]=h;roles[role]=dict(injected_sha256=h,pack_sha256=h,injected_bytes=len(data),pack_bytes=len(data))

            manifest=home/'manifest.json';manifest.write_text(json.dumps({'files':files}))
            cli=wave/'bin/cys';cli.write_text('#!/bin/sh\ncat "$G3_FIXTURE_MANIFEST"\n');cli.chmod(0o755)
            lib=home/'lib.sh';lib.write_text((ROOT/'bootstrap.sh').read_text().rsplit('\nmain "$@"',1)[0])
            receipt=wave/'verify/G3_inject.json'
            def run():

                return subprocess.run(['bash','-c','source "$1"; verify_original_injection','fixture',str(lib)],env=dict(os.environ,HOME=td,WAVE_HOME=str(wave),G3_FIXTURE_MANIFEST=str(manifest)),text=True,capture_output=True,timeout=5)
            result=run();self.assertEqual(result.returncode,0,result.stderr);self.assertTrue(json.loads(result.stdout)['original_match'])
            self.assertIsNone(json.loads(result.stdout)['injected_bytes'])
            original=files['directives/MASTER_DIRECTIVE.md'];files['directives/MASTER_DIRECTIVE.md']='0'*64;manifest.write_text(json.dumps({'files':files}));self.assertEqual(run().returncode,0);files['directives/MASTER_DIRECTIVE.md']=original;manifest.write_text(json.dumps({'files':files}))
            target=pack/'directives/MASTER_DIRECTIVE.md';target.write_text('student edit');edited=hashlib.sha256(target.read_bytes()).hexdigest()
            sidecar=pack/'directives/MASTER_DIRECTIVE.md.new';sidecar.write_text('vendor')
            result=run();self.assertEqual(result.returncode,0,result.stderr);observed=json.loads(result.stdout)
            self.assertFalse(observed['original_match']);self.assertEqual(observed['custom_preserved'],['directives/MASTER_DIRECTIVE.md']);self.assertEqual(observed['new_file_count'],1)
            self.assertEqual(hashlib.sha256(target.read_bytes()).hexdigest(),edited)
            self.assertEqual(len(list(pack.rglob('*.new'))),1)
if __name__=='__main__':unittest.main()
