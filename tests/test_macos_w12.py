import hashlib, json, os, subprocess, tempfile, unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
from platform_scope import mac_only  # noqa: E402


class W12Tests(unittest.TestCase):
    @mac_only()
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
    @mac_only()
    def test_three_live_injected_roles_without_reviewer(self):
        import time
        with tempfile.TemporaryDirectory() as td:
            home=Path(td); wave=home/'wave'; fleet=wave/'fleet'; fleet.mkdir(parents=True)
            cys=home/'.cys'; cys.mkdir()
            since=int(time.time())-1
            marker=cys/'.master-bootstrapped'
            marker.write_text(json.dumps({'surface_ref':'surface:1','orchestra_check':'exit 0'}))
            lib=home/'lib.sh'; lib.write_text((ROOT/'bootstrap.sh').read_text().rsplit('\nmain "$@"',1)[0])
            raw=json.loads((ROOT/'tests/fixtures/real_cys/rc5_three_status.json').read_text())['response']['surfaces']
            seats=[dict(next(r for r in raw if r['role']==role), surface_ref=f'surface:{i+1}', created_at=since) for i,role in enumerate(['master','cso','worker'])]
            def check(rows):
                (fleet/'status.json').write_text(json.dumps({'surfaces':rows}))
                return subprocess.run(['bash','-c','source "$1"; verify_live_fleet surface:1 "$2"','fixture',str(lib),str(since)],env=dict(os.environ,HOME=td,WAVE_HOME=str(wave)),capture_output=True,timeout=5).returncode
            self.assertEqual(check(seats),0, 'three roles need no reviewer')
            marker.write_text(json.dumps({'surface_ref':'1','orchestra_check':'exit 0'}))
            self.assertEqual(check(seats),0, 'numeric master marker must match surface:1')
            marker.write_text(json.dumps({'surface_ref':'surface:1','orchestra_check':'exit 0'}))
            self.assertNotEqual(check([seats[0],seats[2]]),0, '필수 역할 누락을 거부해야 한다')
            self.assertNotEqual(check([seats[0],seats[1]]),0, 'missing worker must fail')
            dead=[dict(s) for s in seats]; dead[1]['agent_alive']=False
            self.assertNotEqual(check(dead),0,'종료된 필수 역할을 거부해야 한다')
            reviewer=dict(seats[1],role='reviewer')
            self.assertNotEqual(check([seats[0],reviewer,seats[2]]),0,'다른 역할로 필수 역할을 대체할 수 없어야 한다')
            marker.write_text(json.dumps({'surface_ref':'surface:99','orchestra_check':'exit 0'}))
            self.assertEqual(check(seats),0,'marker is observational, not a gate')
    @mac_only()
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
    @mac_only()
    def test_onboarding_marker_wait_matches_app_version(self):
        with tempfile.TemporaryDirectory() as td:
            home=Path(td); wave=home/'wave'; (wave/'bin').mkdir(parents=True); (home/'.cys').mkdir()
            (wave/'bin/cys').write_text('#!/bin/sh\n[ "$1" = --version ] && echo "cys 9.9.9"\n'); (wave/'bin/cys').chmod(0o755)
            lib=home/'lib.sh'; lib.write_text((ROOT/'bootstrap.sh').read_text().rsplit('\nmain "$@"',1)[0])
            def wait():
                return subprocess.run(['bash','-c','source "$1"; wait_gui_onboarded $((SECONDS+2))','fixture',str(lib)],env=dict(os.environ,HOME=td,WAVE_HOME=str(wave)),capture_output=True,text=True,timeout=10)
            r=wait(); self.assertNotEqual(r.returncode,0); self.assertIn('J-VER-02',r.stderr)
            (home/'.cys/.gui-onboarded').write_text('9.9.8\n'); self.assertNotEqual(wait().returncode,0,'other app version accepted')
            (home/'.cys/.gui-onboarded').write_text('9.9.9\n'); self.assertEqual(wait().returncode,0)
    @mac_only()
    def test_master_awake_needs_assistant_record_after_start(self):
        import time
        with tempfile.TemporaryDirectory() as td:
            home=Path(td); wave=home/'wave'; (wave/'fleet').mkdir(parents=True)
            cwd='/Users/설치 user'; proj=home/'.cys/claude/projects/-Users----user'; proj.mkdir(parents=True)
            (wave/'fleet/status.json').write_text(json.dumps({'surfaces':[{'surface_ref':'surface:1','role':'master','cwd':cwd}]}))
            lib=home/'lib.sh'; lib.write_text((ROOT/'bootstrap.sh').read_text().rsplit('\nmain "$@"',1)[0])
            env=dict(os.environ,HOME=td,WAVE_HOME=str(wave)); env.pop('CYS_ACCOUNT_DIR',None)
            def state(since):
                return subprocess.run(['bash','-c','source "$1"; master_awake_state surface:1 "$2"','fixture',str(lib),str(since)],env=env,capture_output=True,text=True,timeout=10).stdout.strip()
            now=int(time.time())-5
            self.assertEqual(state(now),'unconfirmed')
            (proj/'s.jsonl').write_text('{"type":"user"}\n'); self.assertEqual(state(now),'unconfirmed')
            (proj/'s.jsonl').write_text('{"type":"user"}\n{"type":"assistant"}\n'); self.assertEqual(state(now),'confirmed')
            self.assertEqual(state(now+3600),'unconfirmed','stale transcript must not count')
    @mac_only()
    def test_progress_lines_match_windows_say_step(self):
        # 화면 진행 표시 = Windows Say-Step 과 같은 꼴 [n/10] title — 시작, 10개 (steps.json index·title)
        import re
        steps=sorted(json.loads((ROOT/'steps.json').read_text(encoding='utf-8'))['steps'],key=lambda s:s['index'])
        with tempfile.TemporaryDirectory() as td:
            lib=Path(td)/'lib.sh'; lib.write_text((ROOT/'bootstrap.sh').read_text().rsplit('\nmain "$@"',1)[0])
            stubs='ensure_pack(){ :; }; load_config(){ :; }; show_help_notice(){ :; }; init_state(){ :; }; json_value(){ echo pending; }; run_step(){ :; }; help_progress(){ :; }; mark_required_complete(){ :; }; mark_install_complete(){ :; }'
            r=subprocess.run(['bash','-c','source "$1"; STEPS_FILE="$2"; '+stubs+'; main','t',str(lib),str(ROOT/'steps.json')],
                             env=dict(os.environ,HOME=td,WAVE_HOME=str(Path(td)/'wave')),capture_output=True,text=True,timeout=30)
            self.assertEqual(r.returncode,0,r.stderr)
            got=re.findall(r'^\[[^]]+\] \[(\d+)/10\] (.+) — 시작$',r.stderr,re.M)
            self.assertEqual(got,[(str(s['index']+1),s['title']) for s in steps])
            self.assertEqual(len(got),10)
            self.assertNotRegex(r.stderr,r'\[S0\d_')

if __name__=='__main__': unittest.main()
