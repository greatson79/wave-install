"""rc.4 S07: 상한 도달 시 좌석이 살아 있으면 실패가 아니라 종료값 2 · 사람 확인 창이 떠 있는 동안은 상한을 멈춘다."""
import json, os, subprocess, tempfile, threading, time, unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GATE = "WARNING: Claude Code running in Bypass Permissions mode\n 1. No, exit\n 2. Yes, I accept\n"
FAKE_CYS = r'''#!/bin/sh
D="$(dirname "$0")/.."
case "$1" in
  launch-agent) echo surface:1 ;;
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

    def status(self, roles, alive=True, created=None, injected=True):
        created = created if created is not None else int(time.time()) + 5
        rows = [dict(surface_ref='surface:%d' % (i + 1), role=r, exited=False, agent_alive=alive, created_at=created,
                     launch_complete=injected)
                for i, r in enumerate(roles)]
        for d in (self.wave, self.wave / 'fleet'):   # 가짜 cys 는 앞쪽을, 직접 호출 시험은 fleet/ 쪽을 읽는다
            (d / 'status.json').write_text(json.dumps({'surfaces': rows}))

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


class LiveRoleSeats(S07Base):
    def count(self):
        r = self.bash('live_role_seats')
        return r.stdout.strip()

    def test_counts_only_live_agent_roles(self):
        self.status(['master', 'cso', 'worker'])
        self.assertEqual(self.count(), '3 cso,master,worker 3')
        self.status(['master', 'worker-2', 'reviewer-codex'])
        self.assertEqual(self.count(), '2 master,worker 2')
        self.status(['master', 'cso', 'worker'], injected=False)
        self.assertEqual(self.count(), '3 cso,master,worker 0')   # 지침 주입 신호(launch_complete)가 없으면 0
        self.status(['master', 'cso', 'worker'], alive=False)
        self.assertEqual(self.count(), '0 - 0')

    def test_missing_status_is_zero(self):
        self.assertEqual(self.count(), '0 - 0')


class UnfinishedOutcome(S07Base):
    def test_alive_seats_are_exit_2_not_a_failure(self):
        self.status(['master', 'cso', 'worker'])
        r = self.bash('s07_unfinished; echo RC=$?; echo "OBS=$STEP_OBSERVED"')
        self.assertIn('RC=2', r.stdout)
        obs = json.loads(r.stdout.split('OBS=')[1])
        self.assertIs(obs['fleet_started'], False)
        self.assertEqual(obs['fleet_state'], 'alive_unconfirmed')
        self.assertEqual(obs['seats_alive'], 3)
        self.assertEqual(obs['j_code'], 'J-VER-04')   # J-UNK-00 대신 전용 진단 코드
        self.assertNotIn('실패:', r.stderr)
        self.assertIn('세 칸 생존 · master 첫 답을 확인하세요', r.stderr)
        self.assertIn('같은 설치 명령을 다시 실행', r.stderr)

    def test_three_alive_but_not_injected_is_a_failure(self):
        self.status(['master', 'cso', 'worker'], injected=False)
        r = self.bash('s07_unfinished; echo RC=$?')
        self.assertIn('RC=1', r.stdout)
        self.assertIn('지침 주입 확인 0/3', r.stderr)

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
        m = self.home / '.cys/.master-bootstrapped'
        m.write_text(json.dumps({'surface_ref': 'surface:1', 'orchestra_check': 'exit 0'}))
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
        self.status(['master', 'cso', 'worker'])
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
        (self.wave / 'fleet/master-ref').write_text('surface:1\n')
        (self.wave / 'fleet/declared').write_text('')
        before = (self.wave / 'status.json').read_text()
        stubs = ('wait_gui_onboarded(){ return 0; }; seed_claude_trust(){ return 0; }; '
                 'awakening_command(){ shift; if [[ "$*" == *"status --json"* ]]; then cat "$WAVE_HOME/status.json"; '
                 'elif [[ "$*" == *" send "* ]]; then echo "$*" >> "$WAVE_HOME/sent.log"; fi; return 0; }; ')
        r = self.bash(stubs + 'RUN_STARTED=%d; step_s07; echo RC=$?' % (now - 10), {'WAVE_AWAKENING_SECONDS': '3'})
        self.assertIn('RC=2', r.stdout, r.stderr)
        sent = (self.wave / 'sent.log').read_text()
        self.assertEqual(sent.count('너는 마스터다'), 1, sent)
        self.assertIn('각성 표지가 아직 없어', r.stderr)

    def test_waiting_line_reports_marker_and_seats(self):
        self.status(['master', 'cso'])
        r = self.run_s07({'WAVE_AWAKENING_SECONDS': '5', 'WAVE_WAIT_REPORT_SECONDS': '1'})
        self.assertIn('기다리는 것: 각성 표지 없음 · 좌석 2/3 · 지침 주입 2/3', r.stderr)

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
