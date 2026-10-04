"""rc.4 S07: 상한 도달 시 좌석이 살아 있으면 실패가 아니라 종료값 2 · 사람 확인 창이 떠 있는 동안은 상한을 멈춘다."""
import copy, json, os, subprocess, tempfile, threading, time, unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REAL = ROOT / 'tests/fixtures/real_cys'   # 실물 cys 바이너리 출력의 녹취 고정본(머리 provenance 에 명령·시각·바이너리 커밋)


def real(name):
    """녹취 고정본의 응답 본문. 손으로 쓴 응답은 쓰지 않는다 — 부정 사례는 이 응답의 행을 고르거나 한 필드를 뒤집어 만든다."""
    return copy.deepcopy(json.loads((REAL / name).read_text(encoding='utf-8'))['response'])
GATE = "WARNING: Claude Code running in Bypass Permissions mode\n 1. No, exit\n 2. Yes, I accept\n"
FAKE_CYS = r'''#!/bin/sh
D="$(dirname "$0")/.."
case "$1" in
  launch-agent) cat "$D/master_ref" ;;
  status) cat "$D/status.json" ;;
  read-screen) if [ -f "$D/gate.on" ]; then cat "$D/gate.txt"; else echo "welcome"; fi ;;
  send) echo "$*" >> "$D/sent.log" ;;
  *) : ;;
esac
'''


class S07Base(unittest.TestCase):
    def setUp(self):
        self.td = tempfile.TemporaryDirectory()
        self.home = Path(self.td.name)
        self.wave = self.home / 'wave'
        (self.wave / 'bin').mkdir(parents=True)
        (self.wave / 'fleet').mkdir()
        (self.home / '.cys').mkdir()
        cys = self.wave / 'bin/cys'
        cys.write_text(FAKE_CYS)
        cys.chmod(0o755)
        (self.wave / 'gate.txt').write_text(GATE)
        self.lib = self.home / 'lib.sh'
        self.lib.write_text((ROOT / 'bootstrap.sh').read_text().rsplit('\nmain "$@"', 1)[0])

    def tearDown(self):
        self.td.cleanup()

    def status(self, roles, alive=True, created=None, source='mac_status_three_seats.json'):
        """녹취 고정본(RC 증거의 실물 `cys status --json`)에서 roles 에 해당하는 행만 고른다. alive=False 는 agent_alive 한 필드 뒤집기,
        created 는 created_at 시각만 이번 시험 시각으로 옮긴다(설치기가 시작 시각과 비교하므로). 그 밖의 키·값은 녹취 그대로."""
        resp = real(source)
        rows = [r for r in resp['surfaces'] if r['role'] in roles]
        ts = created if created is not None else int(time.time()) + 5
        for r in rows:
            r['created_at'] = ts
            if alive is False:
                r['agent_alive'] = False
        resp['surfaces'] = rows
        masters = [r for r in rows if r['role'] == 'master']
        self.master_ref = masters[0]['surface_ref'] if masters else 'surface:1'
        (self.wave / 'master_ref').write_text(self.master_ref + '\n')
        for d in (self.wave, self.wave / 'fleet'):   # 가짜 cys 는 앞쪽을, 직접 호출 시험은 fleet/ 쪽을 읽는다
            (d / 'status.json').write_text(json.dumps(resp))

    def bash(self, script, extra_env=None, timeout=90):
        env = dict(os.environ, HOME=str(self.home), WAVE_HOME=str(self.wave), **(extra_env or {}))
        return subprocess.run(['bash', '-c', 'source "$1"; set +e; SCRIPT_DIR="$2"; ' + script, 'x', str(self.lib), str(ROOT)],
                              env=env, capture_output=True, text=True, timeout=timeout)

    def run_s07(self, extra_env):
        # 앱 기동·온보딩·신뢰 seed·선언 전달은 가짜로 막고, 대기 루프와 종료 판정만 진짜 코드로 돌린다.
        stubs = ('wait_gui_onboarded(){ return 0; }; seed_claude_trust(){ return 0; }; '
                 'awakening_command(){ shift; if [[ "$*" == *"status --json"* ]]; then echo \'{"surfaces":[]}\'; '
                 'elif [[ "$*" == *" send "* ]]; then echo "$*" >> "$WAVE_HOME/sent.log"; fi; return 0; }; ')
        return self.bash(stubs + 'step_s07; echo RC=$?; echo "OBS=$STEP_OBSERVED"', extra_env)


class RecordedShapes(S07Base):
    """루트 원인의 고정: `cys status --json` 에는 launch_complete 가 없고, 데몬 surface.list 응답에만 있다(실물 녹취로 확인)."""

    def test_status_recordings_have_no_launch_complete_but_surface_list_has_it(self):
        for name in ('mac_status_three_seats.json', 'mac_status_noboot.json', 'win_status_three_seats.json',
                     'win_status_noboot.json', 'mac_status_json.json'):
            for row in real(name)['surfaces']:
                self.assertNotIn('launch_complete', row, name)
        rows = real('mac_surface_list.json')['result']['surfaces']
        self.assertTrue(rows and all('launch_complete' in r for r in rows))
        self.assertEqual(sorted(r['launch_complete'] for r in rows), [False, True, True])   # launch-agent 를 거친 두 좌석만 true

    def test_every_recording_carries_its_provenance(self):
        for f in sorted(REAL.glob('*.json')):
            prov = json.loads(f.read_text(encoding='utf-8'))['provenance']
            for key in ('command', 'recorded_at', 'binary'):
                self.assertTrue(prov.get(key), (f.name, key))


class LiveRoleSeats(S07Base):
    def count(self):
        return self.bash('live_role_seats').stdout.strip()

    def test_counts_live_master_cso_worker_from_the_real_status(self):
        self.status(['master', 'cso', 'worker'])
        self.assertEqual(self.count(), '3 cso,master,worker 0 0')   # 실물 status: launch_complete 없음 → 신호 0
        self.status(['master', 'worker'])
        self.assertEqual(self.count(), '2 master,worker 0 0')
        self.status(['master', 'cso', 'worker'], alive=False)
        self.assertEqual(self.count(), '0 - 0 0')
        self.status(['master'], source='win_status_noboot.json')
        self.assertEqual(self.count(), '1 master 0 0')

    def test_a_response_with_launch_complete_is_only_recorded(self):
        # surface.list 녹취의 행(launch_complete 있음)을 살아 있다고 뒤집어(agent_alive 한 필드) 읽혀 본다 — 신호는 기록용 값으로만 나온다.
        resp = real('mac_surface_list.json')['result']
        for r in resp['surfaces']:
            r['agent_alive'] = True
        (self.wave / 'fleet/status.json').write_text(json.dumps(resp))
        self.assertEqual(self.count(), '3 cso,master,worker 2 1')

    def test_reviewer_and_numbered_workers(self):
        resp = real('mac_status_three_seats.json')
        for r in resp['surfaces']:
            if r['role'] == 'worker':
                r['role'] = 'worker-2'
            if r['role'] == 'cso':
                r['role'] = 'reviewer-codex'
        (self.wave / 'fleet/status.json').write_text(json.dumps(resp))
        self.assertEqual(self.count(), '2 master,worker 0 0')

    def test_missing_status_is_zero(self):
        self.assertEqual(self.count(), '0 - 0 0')


class UnfinishedOutcome(S07Base):
    def test_three_live_seats_in_the_real_status_are_exit_2_not_a_failure(self):
        # 이전 status 형식처럼 launch_complete 가 없어도 세 역할이 생존하면 종료값 2 를 반환한다.
        self.status(['master', 'cso', 'worker'])
        r = self.bash('s07_unfinished; echo RC=$?; echo "OBS=$STEP_OBSERVED"')
        self.assertIn('RC=2', r.stdout)
        obs = json.loads(r.stdout.split('OBS=')[1])
        self.assertIs(obs['fleet_started'], False)
        self.assertEqual(obs['fleet_state'], 'alive_unconfirmed')
        self.assertEqual(obs['seats_alive'], 3)
        self.assertIsNone(obs['launch_complete'])   # 신호가 없으면 null — 판정에 쓰지 않는다
        self.assertEqual(obs['j_code'], 'J-VER-04')   # J-UNK-00 대신 전용 진단 코드
        self.assertNotIn('실패', r.stderr)   # 사용자 화면에는 부정형 포함 「실패」 글자 없음(관측 사실만)
        self.assertNotIn('주입', r.stderr)   # 지침을 확인했다는 표현 없음
        self.assertIn('세 칸이 살아 있습니다 · master 첫 답을 확인하세요', r.stderr)
        self.assertIn('같은 설치 명령을 다시 실행', r.stderr)

    def test_launch_complete_when_present_is_recorded_not_decided_on(self):
        resp = real('mac_surface_list.json')['result']
        for r in resp['surfaces']:
            r['agent_alive'] = True
        (self.wave / 'status.json').write_text(json.dumps(resp))   # 가짜 cys 의 `status --json` 응답
        r = self.bash('s07_unfinished; echo RC=$?; echo "OBS=$STEP_OBSERVED"')
        self.assertIn('RC=2', r.stdout)
        self.assertEqual(json.loads(r.stdout.split('OBS=')[1])['launch_complete'], 2)

    def test_the_real_noboot_status_is_a_failure(self):
        self.status(['master'], source='mac_status_noboot.json')
        r = self.bash('s07_unfinished; echo RC=$?')
        self.assertIn('RC=1', r.stdout)
        self.assertIn('살아 있는 칸 1/3', r.stderr)

    def test_fewer_than_three_alive_is_a_failure(self):
        self.status(['master', 'worker'])
        r = self.bash('s07_unfinished; echo RC=$?')
        self.assertIn('RC=1', r.stdout)
        self.assertIn('살아 있는 칸 2/3', r.stderr)

    def test_no_live_seat_is_a_failure(self):
        self.status(['master', 'cso', 'worker'], alive=False)
        r = self.bash('s07_unfinished; echo RC=$?')
        self.assertIn('RC=1', r.stdout)
        self.assertIn('실패:', r.stderr)


class WaitLoop(S07Base):
    def marker(self):
        self.status(['master', 'cso', 'worker'], source='rc5_three_status.json')
        m = self.home / '.cys/.master-bootstrapped'
        m.write_text(json.dumps({'surface_ref': self.master_ref, 'orchestra_check': 'exit 0'}))
        os.utime(m, (time.time() + 20, time.time() + 20))

    def test_all_good_still_passes(self):
        self.status(['master', 'cso', 'worker'])
        self.marker()
        r = self.run_s07({'WAVE_AWAKENING_SECONDS': '8'})
        self.assertIn('RC=0', r.stdout, r.stderr)
        self.assertIn('"fleet_started":true', r.stdout)

    def test_alive_but_marker_missing_ends_with_2(self):
        self.status(['master', 'cso', 'worker'])
        r = self.run_s07({'WAVE_AWAKENING_SECONDS': '4'})
        self.assertIn('RC=2', r.stdout, r.stderr)
        self.assertIn('alive_unconfirmed', r.stdout)

    def test_nothing_alive_ends_with_1(self):
        self.status([])
        r = self.run_s07({'WAVE_AWAKENING_SECONDS': '3'})
        self.assertIn('RC=1', r.stdout, r.stderr)

    def test_open_gate_stops_the_budget(self):
        # 상한 10초인데 확인 창이 ~14초 떠 있다가 사람이 고른 뒤 마커가 생긴다 — 예산이 멈췄으면 통과해야 한다(부하에도 흔들리지 않게 여유를 둠).
        self.status(['master', 'cso', 'worker'], source='rc5_partial_status.json')
        (self.wave / 'gate.on').write_text('')

        def human():
            time.sleep(14)
            (self.wave / 'gate.on').unlink()
            self.marker()
        t = threading.Thread(target=human)
        t.start()
        r = self.run_s07({'WAVE_AWAKENING_SECONDS': '10'})
        t.join()
        self.assertIn('RC=0', r.stdout, r.stderr)

    def test_declaration_names_the_boot_script(self):
        self.status(['master', 'cso', 'worker'])
        self.run_s07({'WAVE_AWAKENING_SECONDS': '3'})
        sent = (self.wave / 'sent.log').read_text()
        self.assertIn('send --queued --to master 너는 마스터다 — ', sent)
        self.assertIn('javis_bootstrap.py', sent)
        self.assertIn('마지막 JSON', sent)

    def test_rerun_with_declared_but_no_marker_resends_once(self):
        # 같은 master 가 살아 있고(이 설치가 만든 것) 선언 기록이 있어도, 각성 표지가 없으면 선언을 한 번 다시 보낸다.
        now = int(time.time())
        self.status(['master', 'cso', 'worker'], created=now + 5)
        (self.wave / 'fleet/started-at').write_text('%d\n' % (now - 10))
        (self.wave / 'fleet/master-ref').write_text(self.master_ref + '\n')
        (self.wave / 'fleet/declared').write_text('')
        before = (self.wave / 'status.json').read_text()
        stubs = ('wait_gui_onboarded(){ return 0; }; seed_claude_trust(){ return 0; }; '
                 'awakening_command(){ shift; if [[ "$*" == *"status --json"* ]]; then cat "$WAVE_HOME/status.json"; '
                 'elif [[ "$*" == *" send "* ]]; then echo "$*" >> "$WAVE_HOME/sent.log"; fi; return 0; }; ')
        r = self.bash(stubs + 'RUN_STARTED=%d; step_s07; echo RC=$?' % (now - 10), {'WAVE_AWAKENING_SECONDS': '3'})
        self.assertIn('RC=2', r.stdout, r.stderr)
        sent = (self.wave / 'sent.log').read_text()
        self.assertEqual(sent.count('너는 마스터다'), 1, sent)
        self.assertIn('지침 완료가 아직 확인되지 않아', r.stderr)

    def test_waiting_line_reports_marker_and_seats(self):
        self.status(['master'], source='mac_status_noboot.json')   # 실물 noboot 모양: master 만 생존
        r = self.run_s07({'WAVE_AWAKENING_SECONDS': '5', 'WAVE_WAIT_REPORT_SECONDS': '1'})
        self.assertIn('기다리는 것: 지침 완료 미확인 · 좌석 1/3', r.stderr)
        self.assertNotIn('주입', r.stderr)

    def test_every_app_gate_wording_pauses_the_budget(self):
        # 앱 first_run_gate.rs 의 질문 문면 전부(폴더 신뢰 4 · 권한 경고 2 · 큰 화면 권유)가 예산을 멈춘다.
        for text in ("Do you trust this folder?", "In Bypass Permissions mode, Claude Code will not ask for your approval",
                     "Try the new fullscreen renderer?", "Quick safety check: Is this a project you created or one you trust?"):
            with self.subTest(text=text[:30]):
                self.status(['master', 'cso', 'worker'])
                (self.wave / 'gate.on').write_text('')
                (self.wave / 'gate.txt').write_text(text + "\n 1. No\n 2. Yes\n")
                r = self.bash('wait_gui_onboarded(){ :; }; notice_first_run_gate; echo VISIBLE=$GATE_VISIBLE')
                self.assertIn('VISIBLE=1', r.stdout, r.stderr)

    def test_gate_pause_is_capped(self):
        self.status(['master', 'cso', 'worker'])
        (self.wave / 'gate.on').write_text('')
        t0 = time.monotonic()
        r = self.run_s07({'WAVE_AWAKENING_SECONDS': '3', 'WAVE_GATE_PAUSE_MAX': '6'})
        self.assertIn('RC=2', r.stdout, r.stderr)
        self.assertLess(time.monotonic() - t0, 40)


class HomeStart(S07Base):
    def test_children_of_bounded_command_start_in_the_home_not_the_callers_folder(self):
        # 2238(맥 대칭): 설치기가 부르는 cys(데몬 자동기동 포함)가 호출자 폴더를 물려받지 않는다.
        elsewhere = self.home / 'project'
        elsewhere.mkdir()
        env = dict(os.environ, HOME=str(self.home), WAVE_HOME=str(self.wave))
        r = subprocess.run(['bash', '-c', 'source "$1"; set +e; bounded_command /bin/pwd', 'x', str(self.lib)],
                           env=env, cwd=str(elsewhere), capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(os.path.realpath(r.stdout.strip()), os.path.realpath(str(self.home)))

    def test_timeout_and_exit_code_behaviour_is_unchanged(self):
        r = self.bash('WAVE_COMMAND_TIMEOUT=1 bounded_command sleep 5; echo RC=$?')
        self.assertIn('RC=124', r.stdout)
        r = self.bash('bounded_command sh -c "exit 7"; echo RC=$?')
        self.assertIn('RC=7', r.stdout)


class PermissionNotice(S07Base):
    TEXT = "이 설치는 Wave 의 세 작업 칸(마스터·CSO·워커)이 권한 확인 창 없이 바로 일하도록 설정합니다. 되돌리려면 reset 을 실행하세요."

    def test_mac_prints_the_confirmed_line_after_the_help_notice(self):
        r = self.bash('show_permission_notice')
        self.assertIn(self.TEXT, r.stderr)
        src = (ROOT / 'bootstrap.sh').read_text()
        self.assertLess(src.index('\n  show_help_notice\n'), src.index('\n  show_permission_notice\n'))
        self.assertLess(src.index('\n  show_permission_notice\n'), src.index('\n  init_state\n'))

    def test_windows_says_the_same_line_right_after_the_help_notice(self):
        src = (ROOT / 'bootstrap.ps1').read_text(encoding='utf-8-sig')
        self.assertIn("Say '" + self.TEXT + "'", src)
        self.assertLess(src.index('  Show-HelpNotice\n}'), src.index("Say '" + self.TEXT))
        self.assertLess(src.index("Say '" + self.TEXT), src.index('\nInit-State'))


if __name__ == '__main__':
    unittest.main()
