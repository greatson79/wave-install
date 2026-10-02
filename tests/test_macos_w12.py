import hashlib, json, os, subprocess, tempfile, unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
class W12Tests(unittest.TestCase):
    def test_pack_replaces_only_exact_stub_and_checks_embedded_hash(self):
        with tempfile.TemporaryDirectory() as td:
            home=Path(td); wave=home/'wave'; pack=home/'.cys/pack'; (wave/'bin').mkdir(parents=True); (pack/'directives').mkdir(parents=True)
            old=ROOT/'wave-pack/directives/MASTER_DIRECTIVE.md'
            (pack/'directives/MASTER_DIRECTIVE.md').write_bytes(old.read_bytes())
            body=b'full app directive\n'; sha=hashlib.sha256(body).hexdigest()
            cli=wave/'bin/cys'; cli.write_text('#!/bin/sh\ncase "$1" in\ninit-pack) printf "full app directive\\n" > "$CYS_PACK_DIR/directives/MASTER_DIRECTIVE.md";;\npack-manifest) printf \'{"files":{"directives/MASTER_DIRECTIVE.md":"'+sha+'"}}\';;\nesac\n'); cli.chmod(0o755)
            lib=home/'lib.sh'; lib.write_text((ROOT/'bootstrap.sh').read_text().rsplit('\nmain "$@"',1)[0])
            env=dict(os.environ,HOME=td,WAVE_HOME=str(wave))
            result=subprocess.run(['bash','-c','source "$1"; SCRIPT_DIR="$2"; step_s06','test',str(lib),str(ROOT)],env=env,capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)
            self.assertEqual((pack/'directives/MASTER_DIRECTIVE.md').read_bytes(),body)
            self.assertTrue(list((wave/'backups').rglob('MASTER_DIRECTIVE.md')))
            (pack/'directives/MASTER_DIRECTIVE.md').write_text('custom')
            cli.write_text('#!/bin/sh\ncase "$1" in\ninit-pack) :;;\npack-manifest) printf \'{"files":{"directives/MASTER_DIRECTIVE.md":"'+sha+'"}}\';;\nesac\n')
            result=subprocess.run(['bash','-c','source "$1"; SCRIPT_DIR="$2"; step_s06','test',str(lib),str(ROOT)],env=env,capture_output=True,text=True)
            self.assertNotEqual(result.returncode,0)
            self.assertEqual((pack/'directives/MASTER_DIRECTIVE.md').read_text(),'custom')
if __name__=='__main__': unittest.main()
