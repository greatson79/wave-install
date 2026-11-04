"""rc.5 wake: 설치기가 CSO·워커 칸을 직접 띄우고, 마스터 응답을 기다려 확인하며, 미확인을 숨기지 않는다(맥 bootstrap.sh).
시험 환경변수(실사용 기본값): WAVE_AWAKE_SECONDS=120 · WAVE_AWAKE_INTERVAL=30 · WAVE_AWAKE_RESEND_AT=60."""
import json, os, re, shutil, subprocess, tempfile, threading, time, unittest
from pathlib import Path
from test_rc4_s07 import S07Base, ROOT

from platform_scope import mac_only  # noqa: E402

FAKE_CYS = r'''#!/bin/sh
D="$(dirname "$0")/.."
case "$1" in
  launch-agent) echo "launch-agent $*" >> "$D/calls.log"; cat "$D/master_ref" ;;
  status) cat "$D/status.json" ;;
  boot) echo "$*" >> "$D/boot.log"; echo "boot" >> "$D/calls.log"; [ -f "$D/boot.fail" ] && exit 1; [ -f "$D/three.json" ] && cp "$D/three.json" "$D/status.json"; exit 0 ;;
  send) echo "$*" >> "$D/sent.log"; echo "send" >> "$D/calls.log" ;;
  *) : ;;
esac
'''
# 앱 기동·온보딩·신뢰 seed 는 막고, boot·send 는 가짜 cys 를 실제로 호출한다.
S07_STUBS = ('wait_gui_onboarded(){ return 0; }; seed_claude_trust(){ return 0; }; '
             'awakening_command(){ shift; case "$1" in open) return 0;; esac; '
             'if [[ "$*" == *"status --json"* ]]; then echo \'{"surfaces":[]}\'; else "$@"; fi; }; ')
S08_STUBS = 'verify_original_injection(){ echo \'{"original_match":true,"new_file_count":0}\'; }; '
DECLARATION = '너는 마스터다'


def iso(ns):
    from datetime import datetime, timezone
    return datetime.fromtimestamp(ns / 1e9, timezone.utc).strftime('%Y-%m-%dT%H:%M:%S.%f')[:-3] + 'Z'


def tool_result_rec(ns):
    """도구 결과가 든 user 줄의 모양 — message.content 가 tool_result 항목 목록(내용 없음)."""
    return json.dumps({'type': 'user', 'timestamp': iso(ns), 'message': {'role': 'user', 'content': [{'type': 'tool_result'}]}},
                      separators=(',', ':')) + '\n'


def rec(kind, ns):
    """실제 세션 기록 한 줄의 모양(최상위 type·timestamp 만 — 내용 없음)."""
    return json.dumps({'type': kind, 'timestamp': iso(ns), 'message': {'role': kind}}, separators=(',', ':')) + '\n'
NOTICE = '마스터 응답'          # 미확인 안내의 공통 어구 — 확인됨 경로에는 나오면 안 된다
UNCONFIRMED = '확인하지 못했습니다'


class WakeBase(S07Base):
    def bash(self, script, extra_env=None, timeout=90):
        return super().bash('claude_seat_auth(){ :; }; claude(){ :; }; ' + script, extra_env, timeout)

    def status(self, roles, **kwargs):
        super().status(roles, **kwargs)
        marker = self.home / '.cys/.master-bootstrapped'
        marker.write_text(json.dumps({'surface_ref': self.master_ref, 'orchestra_check': 'exit 0'}))
        future = time.time() + 10
        os.utime(marker, (future, future))

    def setUp(self):
        super().setUp()
        cys = self.wave / 'bin/cys'
        cys.write_text(FAKE_CYS)
        cys.chmod(0o755)

    def three_then_master_only(self):
        """boot 가 성공하면 세 칸이 서는 상황: three.json 은 녹취 세 칸, status.json 은 master 한 칸."""
        self.status(['master', 'cso', 'worker'], source='rc5_three_status.json')
        shutil.copy(self.wave / 'status.json', self.wave / 'three.json')
        self.status(['master'], source='rc5_three_status.json')

    def boot_log(self):
        p = self.wave / 'boot.log'
        return p.read_text() if p.exists() else ''

    def sent_count(self):
        p = self.wave / 'sent.log'
        return p.read_text().count(DECLARATION) if p.exists() else 0

    def s07(self, seconds='15'):
        return self.bash(S07_STUBS + 'step_s07; echo RC=$?; echo "OBS=$STEP_OBSERVED"', {'WAVE_AWAKENING_SECONDS': seconds})


class SupportSeats(WakeBase):
    @mac_only()
    def test_installer_starts_cso_and_worker_without_master_help(self):
        self.three_then_master_only()          # 마스터 AI 는 아무 명령도 안 내린다 — 설치기 혼자서
        r = self.s07()
        self.assertIn('boot --cwd', self.boot_log(), r.stderr)
        self.assertIn('RC=0', r.stdout, r.stdout + r.stderr)
        self.assertIn('"fleet_started":true', r.stdout)

    @mac_only()
    def test_support_seats_are_started_before_master_then_declaration(self):
        self.three_then_master_only()
        r = self.s07()
        calls = [c.split()[0] for c in (self.wave / 'calls.log').read_text().splitlines()]
        self.assertEqual(calls[:3], ['boot', 'launch-agent', 'send'], calls)
        self.assertIn('--cwd', (self.wave / 'boot.log').read_text())
        self.assertIn('RC=0', r.stdout, r.stdout + r.stderr)

    @mac_only()
    def test_boot_failure_does_not_change_exit_code(self):
        (self.wave / 'boot.fail').write_text('')
        self.status(['master', 'cso', 'worker'], source='rc5_three_status.json')   # 세 칸이 이미 서 있으면 통과
        r = self.s07()
        self.assertIn('boot --cwd', self.boot_log(), r.stderr)
        self.assertIn('RC=0', r.stdout, r.stdout + r.stderr)
        self.status(['master'], source='rc5_three_status.json')                     # 안 서면 기존 규칙대로 1
        (self.wave / 'boot.log').unlink()
        r = self.s07('4')
        self.assertIn('boot --cwd', self.boot_log(), r.stderr)
        self.assertIn('RC=1', r.stdout, r.stdout + r.stderr)
        self.assertIn('살아 있는 칸 1/3', r.stderr)


class AwakeCheck(WakeBase):
    ENV = {'WAVE_AWAKE_SECONDS': '12', 'WAVE_AWAKE_INTERVAL': '1', 'WAVE_AWAKE_RESEND_AT': '6'}

    def prepare(self):
        """S08 직전 상태: 세 칸 생존 · 선언 전달 완료(declared) · 마스터 세션 기록 폴더 없음."""
        self.status(['master', 'cso', 'worker'], source='rc5_three_status.json')
        fleet = self.wave / 'fleet'
        (fleet / 'master-ref').write_text(self.master_ref + '\n')
        (fleet / 'started-at').write_text('%d\n' % (int(time.time()) - 200))
        (fleet / 'declared').write_text('')
        cwd = json.loads((self.wave / 'status.json').read_text())['surfaces'][0]['cwd']
        self.account = self.home / '.cys/claude'
        self.project = self.account / 'projects' / re.sub(r'[^A-Za-z0-9]', '-', cwd)
        self.project.mkdir(parents=True)
        self.declared = fleet / 'declared'

    def s08(self, **override):
        env = dict(self.ENV, CYS_ACCOUNT_DIR=str(self.account), **override)
        return self.bash(S08_STUBS + 'step_s08; echo RC=$?; echo "OBS=$STEP_OBSERVED"', env)

    def awake_value(self, r):
        return json.loads(r.stdout.split('OBS=')[1])['master_awake']

    @mac_only()
    def test_awake_check_waits_and_resends_once(self):
        self.prepare()
        # (가) 응답 기록이 선언 뒤 2초에 생긴다 → 기다렸다가 확인됨, 재전송 없음
        t = threading.Timer(2, lambda: (self.project / 's.jsonl').write_text(rec('user', time.time_ns()) + rec('assistant', time.time_ns())))
        t.start()
        r = self.s08(); t.join()
        self.assertIn('RC=0', r.stdout, r.stdout + r.stderr)
        self.assertEqual(self.awake_value(r), 'confirmed', r.stderr)
        self.assertEqual(self.sent_count(), 0)
        # (나) 끝내 응답이 없다 → 선언을 정확히 1회만 다시 보내고 미확인으로 끝(설치는 계속 — 종료값 0)
        (self.project / 's.jsonl').unlink()
        r = self.s08()
        self.assertIn('RC=0', r.stdout, r.stdout + r.stderr)
        self.assertEqual(self.awake_value(r), 'unconfirmed')
        self.assertEqual(self.sent_count(), 1, (self.wave / 'sent.log').read_text() if (self.wave / 'sent.log').exists() else '')

    @mac_only()
    def test_record_before_declaration_is_not_confirmation(self):
        # 지침 주입 뒤·선언 전 시각의 응답 기록만 있으면 확인됨이 아니다(설치 시작 기준이면 잘못 확인됨이 된다).
        self.prepare()
        f = self.project / 's.jsonl'
        f.write_text('{"type":"user"}\n{"type":"assistant"}\n')
        past = time.time() - 100
        os.utime(f, (past, past))
        r = self.s08()
        self.assertEqual(self.awake_value(r), 'unconfirmed', r.stdout + r.stderr)

    def _declared_at(self, ns, transcript_ns):
        f = self.project / 's.jsonl'
        f.write_text(rec('user', transcript_ns) + rec('assistant', transcript_ns + 10_000_000))
        os.utime(self.declared, ns=(ns, ns))
        os.utime(f, ns=(transcript_ns, transcript_ns))

    def _put(self, name, text, mtime_ns=None):
        f = self.project / name
        f.write_text(text)
        if mtime_ns is not None:
            os.utime(f, ns=(mtime_ns, mtime_ns))
        return f

    def _declare_at(self, ns):
        os.utime(self.declared, ns=(ns, ns))

    @mac_only()
    def test_assistant_before_declaration_plus_user_after_is_unconfirmed(self):
        # 선언 전 assistant 기록 + 선언 뒤 user 기록(선언문 자체) — 파일 수정 시각은 선언 뒤여도 응답이 아니다.
        self.prepare()
        T = (int(time.time()) - 60) * 10**9
        self._declare_at(T)
        self._put('s.jsonl', rec('assistant', T - 10 * 10**9) + rec('user', T + 5 * 10**9))
        r = self.s08(WAVE_AWAKE_SECONDS='0')
        self.assertEqual(self.awake_value(r), 'unconfirmed', r.stdout + r.stderr)

    @mac_only()
    def test_assistant_record_after_declaration_is_confirmed(self):
        self.prepare()
        T = (int(time.time()) - 60) * 10**9
        self._declare_at(T)
        self._put('s.jsonl', rec('assistant', T - 10 * 10**9) + rec('user', T + 5 * 10**9) + rec('assistant', T + 8 * 10**9))
        r = self.s08(WAVE_AWAKE_SECONDS='0')
        self.assertEqual(self.awake_value(r), 'confirmed', r.stdout + r.stderr)

    @mac_only()
    def test_many_session_files_only_a_post_declaration_assistant_counts(self):
        self.prepare()
        T = (int(time.time()) - 60) * 10**9
        self._declare_at(T)
        self._put('a.jsonl', rec('assistant', T - 20 * 10**9))                       # 옛 세션: 선언 전 답
        self._put('b.jsonl', rec('user', T + 2 * 10**9))                             # 선언 뒤 user 만
        r = self.s08(WAVE_AWAKE_SECONDS='0')
        self.assertEqual(self.awake_value(r), 'unconfirmed', r.stdout + r.stderr)
        self._put('c.jsonl', rec('user', T + 3 * 10**9) + rec('assistant', T + 4 * 10**9))   # 다른 파일: 선언 뒤 user 다음 답
        r = self.s08(WAVE_AWAKE_SECONDS='0')
        self.assertEqual(self.awake_value(r), 'confirmed', r.stdout + r.stderr)

    @mac_only()
    def test_broken_partial_or_untimed_records_are_not_confirmation(self):
        self.prepare()
        T = (int(time.time()) - 60) * 10**9
        self._declare_at(T)
        text = (rec('user', T + 2 * 10**9)                                                  # 선언이 들어간 user 줄은 정상 — 그 뒤 답 줄들이 전부 무효
                + '{"type":"assistant","timestamp":"' + iso(T + 3 * 10**9) + '"\n'            # 닫히지 않은 줄
                + '{"type":"assistant"}\n'                                                 # 시각 없음
                + '{"type":"assistant","timestamp":"방금"}\n'                               # 파싱 불가
                + '{"type":"assistant","timestamp":"' + iso(T + 3 * 10**9)[:-1] + '"}\n'    # 시간대 없음
                + 'garbage\n'
                + '{"type":"assistant","timestamp":"' + iso(T + 4 * 10**9) + '"')           # 줄바꿈 없는 부분 줄
        self._put('s.jsonl', text)
        r = self.s08(WAVE_AWAKE_SECONDS='0')
        self.assertEqual(self.awake_value(r), 'unconfirmed', r.stdout + r.stderr)

    @mac_only()
    def test_assistant_after_declaration_time_without_a_declaration_user_line_is_unconfirmed(self):
        # 선언 시각 뒤에 끝난 assistant 가 있어도, 그 앞에 「선언 뒤 user 줄」이 없으면 선언에 대한 답이 아니다
        # (지침 주입에 대한 답이 선언 전달 전에 아직 진행 중이었을 뿐).
        self.prepare()
        T = (int(time.time()) - 60) * 10**9
        self._declare_at(T)
        self._put('s.jsonl', rec('user', T - 30 * 10**9) + rec('assistant', T + 5 * 10**9))
        r = self.s08(WAVE_AWAKE_SECONDS='0')
        self.assertEqual(self.awake_value(r), 'unconfirmed', r.stdout + r.stderr)

    @mac_only()
    def test_assistant_before_the_declaration_user_line_in_file_order_is_unconfirmed(self):
        self.prepare()
        T = (int(time.time()) - 60) * 10**9
        self._declare_at(T)
        self._put('s.jsonl', rec('assistant', T + 4 * 10**9) + rec('user', T + 5 * 10**9))   # 줄 순서: 답이 먼저, 선언 user 가 뒤
        r = self.s08(WAVE_AWAKE_SECONDS='0')
        self.assertEqual(self.awake_value(r), 'unconfirmed', r.stdout + r.stderr)

    @mac_only()
    def test_production_call_always_passes_the_declaration_file(self):
        # 선언 파일 인자 없는 옛 호출은 느슨한 옛 판정 — 운영 경로(await_master_awake)는 항상 인자를 준다.
        self.prepare()
        r = self.bash('master_awake_state(){ echo "ARGC=$# A3=$3" >&2; echo unconfirmed; }; '
                      'await_master_awake surface:1 100 >/dev/null; echo done',
                      {'WAVE_AWAKE_SECONDS': '0'})
        self.assertIn('ARGC=3', r.stderr, r.stderr)
        self.assertIn('/fleet/declared', r.stderr)

    @mac_only()
    def test_tool_result_user_line_is_not_the_declaration(self):
        # 도구 결과도 type=user 줄이다 — 선언 없이 도구를 쓰며 답하는 중에 생긴 줄 + 그 뒤 assistant 는 확인이 아니다.
        self.prepare()
        T = (int(time.time()) - 60) * 10**9
        self._declare_at(T)
        self._put('s.jsonl', rec('user', T - 30 * 10**9) + tool_result_rec(T + 3 * 10**9) + rec('assistant', T + 4 * 10**9))
        r = self.s08(WAVE_AWAKE_SECONDS='0')
        self.assertEqual(self.awake_value(r), 'unconfirmed', r.stdout + r.stderr)
        # 같은 파일에 진짜 선언 user 줄(문자열 content)이 뒤따르고 그 뒤에 답이 있으면 확인됨.
        self._put('s.jsonl', rec('user', T - 30 * 10**9) + tool_result_rec(T + 3 * 10**9) + rec('assistant', T + 4 * 10**9)
                  + rec('user', T + 6 * 10**9) + rec('assistant', T + 7 * 10**9))
        r = self.s08(WAVE_AWAKE_SECONDS='0')
        self.assertEqual(self.awake_value(r), 'confirmed', r.stdout + r.stderr)

    @mac_only()
    def test_record_100ms_before_declaration_in_same_second_is_unconfirmed(self):
        self.prepare()
        base = (int(time.time()) - 30) * 10**9 + 900_000_000   # N.9 초에 선언
        self._declared_at(base, base - 100_000_000)             # N.8 초의 응답 기록 — 같은 초 안, 선언 직전
        r = self.s08(WAVE_AWAKE_SECONDS='0')
        self.assertEqual(self.awake_value(r), 'unconfirmed', r.stdout + r.stderr)

    @mac_only()
    def test_record_100ms_after_declaration_is_confirmed(self):
        self.prepare()
        base = (int(time.time()) - 30) * 10**9 + 900_000_000
        self._declared_at(base, base + 100_000_000)
        r = self.s08(WAVE_AWAKE_SECONDS='0')
        self.assertEqual(self.awake_value(r), 'confirmed', r.stdout + r.stderr)

    @mac_only()
    def test_rerun_flow_resends_the_declaration_once_in_total(self):
        # 재실행: S07 이 지침 완료 미확인으로 선언을 다시 보낸 뒤, 같은 흐름의 S08 응답 대기가 또 보내면 안 된다(총 1회).
        self.three_then_master_only()
        fleet = self.wave / 'fleet'
        (fleet / 'master-ref').write_text(self.master_ref + '\n')
        (fleet / 'started-at').write_text('%d\n' % (int(time.time()) - 10))
        (fleet / 'declared').write_text('')
        self.account = self.home / '.cys/claude'
        stubs = ('wait_gui_onboarded(){ return 0; }; seed_claude_trust(){ return 0; }; '
                 'awakening_command(){ shift; case "$1" in open) return 0;; esac; '
                 'if [[ "$*" == *"status --json"* ]]; then cat "$WAVE_HOME/status.json"; else "$@"; fi; }; ' + S08_STUBS)
        env = dict(self.ENV, CYS_ACCOUNT_DIR=str(self.account), WAVE_AWAKENING_SECONDS='20')
        r = self.bash(stubs + 'step_s07; echo RC07=$?; step_s08; echo RC08=$?; echo "OBS=$STEP_OBSERVED"', env)
        self.assertIn('RC07=0', r.stdout, r.stdout + r.stderr)
        self.assertIn('RC08=0', r.stdout, r.stdout + r.stderr)
        self.assertEqual(self.awake_value(r), 'unconfirmed')
        self.assertEqual(self.sent_count(), 1, (self.wave / 'sent.log').read_text())


class UnconfirmedIsStated(WakeBase):
    def state_with(self, awake):
        state = json.loads((ROOT / 'install-state.json').read_text())
        for entry in state['steps'].values():
            entry.update(status='passed', exit_code=0, error_id=None, observed={})
        state['steps']['S07_INITIAL_FLEET']['observed'] = {'fleet_started': True}
        state['steps']['S08_VERIFY']['observed'] = {'original_match': True, 'new_file_count': 0, 'master_awake': awake}
        path = self.wave / 'install-state.json'
        path.write_text(json.dumps(state))
        return path

    def start_here(self, awake):
        path = self.state_with(awake)
        r = self.bash('STATE_FILE="%s"; STEPS_FILE="%s"; mark_required_complete; step_s09; echo RC=$?' % (path, ROOT / 'steps.json'))
        self.assertIn('RC=0', r.stdout, r.stdout + r.stderr)
        return (self.wave / 'START-HERE.md').read_text(encoding='utf-8')

    def last_stderr_line(self, awake):
        path = self.state_with(awake)
        stubs = ('ensure_pack(){ :; }; load_config(){ :; }; show_help_notice(){ :; }; show_permission_notice(){ :; }; init_state(){ :; }; '
                 'attempt_start(){ :; }; run_step(){ :; }; help_progress(){ :; }; mark_required_complete(){ :; }; mark_install_complete(){ :; }; ')
        r = self.bash('STATE_FILE="%s"; STEPS_FILE="%s"; %s main; echo RC=$?' % (path, ROOT / 'steps.json', stubs))
        self.assertIn('RC=0', r.stdout, r.stdout + r.stderr)
        return [l for l in r.stderr.splitlines() if l.strip()][-1], r.stderr

    @mac_only()
    def test_unconfirmed_is_stated_in_start_here_and_last_line(self):
        text = self.start_here('unconfirmed')
        self.assertIn(UNCONFIRMED, text)
        self.assertIn('필수 단계 검증을 통과했습니다.', text)      # status·종료값 규칙은 그대로
        last, _ = self.last_stderr_line('unconfirmed')
        self.assertIn(UNCONFIRMED, last)

    @mac_only()
    def test_confirmed_leaves_no_warning(self):
        text = self.start_here('confirmed')
        self.assertNotIn(UNCONFIRMED, text)
        self.assertIn('필수 단계 검증을 통과했습니다.', text)
        last, err = self.last_stderr_line('confirmed')
        self.assertNotIn(UNCONFIRMED, err)
        self.assertNotIn(NOTICE, last)

    @mac_only()
    def test_state_file_has_a_master_awake_field_for_state_only_readers(self):
        # 테오 보완 1건: 완료 값·종료값은 그대로 두고, 상태 파일만 읽는 도구가 구분할 수 있는 칸을 하나 더 둔다.
        for awake in ('confirmed', 'unconfirmed'):
            with self.subTest(awake=awake):
                path = self.state_with(awake)
                r = self.bash('STATE_FILE="%s"; STEPS_FILE="%s"; summarize_state final; echo RC=$?' % (path, ROOT / 'steps.json'))
                self.assertIn('RC=0', r.stdout, r.stdout + r.stderr)
                state = json.loads(path.read_text())
                self.assertEqual(state['status'], 'complete')
                self.assertIs(state['required_steps_passed'], True)
                self.assertEqual(state.get('master_awake'), awake)
