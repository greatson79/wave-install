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
    def test_three_live_roles_and_master_marker_without_reviewer(self):
        import time
        with tempfile.TemporaryDirectory() as td:
            home=Path(td); wave=home/'wave'; fleet=wave/'fleet'; fleet.mkdir(parents=True)
            cys=home/'.cys'; cys.mkdir()
            since=int(time.time())-1
            marker=cys/'.master-bootstrapped'
            marker.write_text(json.dumps({'surface_ref':'surface:1','orchestra_check':'exit 0'}))
            lib=home/'lib.sh'; lib.write_text((ROOT/'bootstrap.sh').read_text().rsplit('\nmain "$@"',1)[0])
            seats=[dict(surface_ref=f'surface:{i+1}',role=role,exited=False,agent_alive=True,directive_verified=True,awakened_at=since,created_at=since) for i,role in enumerate(['master','cso','worker'])]
            def check(rows):
                (fleet/'status.json').write_text(json.dumps({'surfaces':rows}))
                return subprocess.run(['bash','-c','source "$1"; verify_live_fleet surface:1 "$2"','fixture',str(lib),str(since)],env=dict(os.environ,HOME=td,WAVE_HOME=str(wave)),capture_output=True,timeout=5).returncode
            self.assertEqual(check(seats),0, 'three roles need no reviewer')
            self.assertNotEqual(check([seats[0],seats[2]]),0, 'missing CSO must fail')
            self.assertNotEqual(check([seats[0],seats[1]]),0, 'missing worker must fail')
            dead=[dict(s) for s in seats]; dead[1]['agent_alive']=False
            self.assertNotEqual(check(dead),0,'dead CSO must fail')
            reviewer=dict(seats[1],role='reviewer')
            self.assertNotEqual(check([seats[0],reviewer,seats[2]]),0,'reviewer cannot replace CSO')
            marker.write_text(json.dumps({'surface_ref':'surface:99','orchestra_check':'exit 0'}))
            self.assertNotEqual(check(seats),0,'wrong master marker must fail')
    def test_awakening_commands_obey_remaining_deadline(self):
        import time
        with tempfile.TemporaryDirectory() as td:
            lib=Path(td)/'lib.sh'; lib.write_text((ROOT/'bootstrap.sh').read_text().rsplit('\nmain "$@"',1)[0])
            start=time.monotonic()
            result=subprocess.run(['bash','-c','source "$1"; SECONDS=419; awakening_command 420 python3 -c "import time; time.sleep(5)"','fixture',str(lib)],capture_output=True,timeout=4)
            self.assertEqual(result.returncode,124)
            self.assertLess(time.monotonic()-start,3)
            result=subprocess.run(['bash','-c','source "$1"; SECONDS=420; awakening_command 420 echo SHOULD_NOT_RUN','fixture',str(lib)],capture_output=True,timeout=4)
            self.assertEqual(result.returncode,124)
            self.assertEqual(result.stdout,b'')
if __name__=='__main__': unittest.main()
