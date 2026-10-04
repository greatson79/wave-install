import hashlib,json,os,subprocess,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
from platform_scope import mac_only  # noqa: E402


class OriginalTests(unittest.TestCase):
    @mac_only()
    def test_large_original_matches_and_mismatches_or_new_are_rejected(self):
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
            original=files['directives/MASTER_DIRECTIVE.md'];files['directives/MASTER_DIRECTIVE.md']='0'*64;manifest.write_text(json.dumps({'files':files}));self.assertNotEqual(run().returncode,0);files['directives/MASTER_DIRECTIVE.md']=original;manifest.write_text(json.dumps({'files':files}))
            (pack/'pending.new').write_text('pending');self.assertNotEqual(run().returncode,0)
if __name__=='__main__':unittest.main()
