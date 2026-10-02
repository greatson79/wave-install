#!/usr/bin/env python3
"""Install-help client for the macOS bootstrap (API contract v1 §1-4, §5-1).

Fail-open by design: every network error is swallowed and the caller's install state,
continuation and exit code never depend on this module. Nothing is sent before the
first-screen notice was shown. Prescriptions are displayed as plain text only; nothing
received from the server is ever executed. The client_token lives in memory only.
"""
import argparse
import getpass
import json
import os
import platform
import re
import sys
import time
import urllib.error
import urllib.request
import uuid
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from install_help import safe_text  # noqa: E402

DEFAULT_BASE_URL = 'https://waveainetworks.com'
PROGRESS_TIMEOUT = 3
HELP_TIMEOUT = 20
PROGRESS_MAX_BYTES = 8 * 1024
HELP_MAX_BYTES = 4 * 1024 * 1024
ENV_MAX_BYTES = 96 * 1024
LOG_MAX_BYTES = 128 * 1024
LOG_MAX_LINES = 40
RESPONSE_MAX_BYTES = 256 * 1024
BUSY_RETRY_SECONDS = 60
POLL_SECONDS = 20
POLL_MAX_SECONDS = 7200
MESSAGE_MAX_CHARS = 4096

ID_RE = re.compile(r'^[0-9a-f]{32}$')
TOKEN_RE = re.compile(r'^[0-9a-f]{64}$')
DETAIL_RE = re.compile(r'^J-[A-Z0-9]{2,8}-\d{2,3}$')
VERSION_RE = re.compile(r'^[0-9A-Za-z._-]{1,20}$')
STEP_RE = re.compile(r'^\d{1,2}/\d{1,2}$')


def clean_display(text):
    """Strip ANSI sequences and control characters (keep tab/newline) before printing."""
    text = re.sub(r'\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)', '', str(text))
    text = re.sub(r'\x1b\[[0-?]*[ -/]*[@-~]', '', text)
    return re.sub(r'[\x00-\x08\x0b-\x1f\x7f]', '', text)[:MESSAGE_MAX_CHARS]


def head_bytes(text, limit):
    return text.encode('utf-8')[:limit].decode('utf-8', 'ignore')


def tail_bytes(text, limit):
    return text.encode('utf-8')[-limit:].decode('utf-8', 'ignore') if limit else ''


def _now():
    return datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')


class HelpClient:
    def __init__(self, base_url, install_id, version, notice=False, username='', transport=None,
                 sleep=time.sleep, clock=time.monotonic, emit=print):
        if not str(base_url).startswith('https://'):
            raise ValueError('help base URL must be https')
        if not ID_RE.match(install_id):
            raise ValueError('install_id must be 32 hex')
        self.base_url = base_url.rstrip('/')
        self.install_id = install_id
        self.version = version if VERSION_RE.match(str(version)) else 'unknown'
        self.notice = notice is True
        self.username = username or ''
        self.transport = transport or urllib_transport(self.base_url)
        self.sleep, self.clock, self.emit = sleep, clock, emit
        self.progress_warned = False

    def _call(self, method, path, payload, token, timeout):
        try:
            status, body = self.transport(method, path, payload, token, timeout)
            return status, body
        except Exception:  # fail-open; never surface raw errors (may contain hosts/paths)
            return None, None

    def _safe(self, text):
        return safe_text(str(text or ''), self.username)

    def progress(self, step, event, elapsed=None, detail=''):
        """POST /api/progress. Returns True on 2xx. 503 and errors are dropped (no retry)."""
        if not self.notice:
            return False
        payload = {'install_id': self.install_id, 'installer_version': self.version, 'os': 'mac',
                   'step': step, 'event': event, 'at': _now()}
        if elapsed is not None:
            payload['elapsed_s'] = max(0, min(86400, int(elapsed)))
        if detail and DETAIL_RE.match(detail):
            payload['detail'] = detail
        if len(json.dumps(payload).encode('utf-8')) > PROGRESS_MAX_BYTES:
            return False
        status, _ = self._call('POST', '/api/progress', payload, None, PROGRESS_TIMEOUT)
        ok = isinstance(status, int) and 200 <= status < 300
        if not ok and not self.progress_warned:
            self.progress_warned = True
            self.emit('progress send failed (fail-open); 설치를 계속합니다.')
        return ok

    def build_help_payload(self, step, code, env_report, log_tail):
        lines = re.split(r'\r?\n', str(log_tail or ''))
        if lines and lines[-1] == '':
            lines.pop()
        lines = lines[-LOG_MAX_LINES:]
        payload = {
            'install_id': self.install_id, 'os': 'mac', 'installer_version': self.version,
            'step': step if STEP_RE.match(str(step)) else '1/10',
            'code': code if DETAIL_RE.match(str(code)) else 'J-UNK-00',
            'notice_shown': True,
            'env_report': head_bytes(self._safe(env_report), ENV_MAX_BYTES),
            'log_tail': tail_bytes(self._safe('\n'.join(lines)), LOG_MAX_BYTES),
        }
        return payload

    def help(self, step, code, env_report, log_tail, interactive):
        """POST /api/help once (+1 retry on 503 busy), then poll only when interactive."""
        if not self.notice:
            return None
        payload = self.build_help_payload(step, code, env_report, log_tail)
        if len(json.dumps(payload).encode('utf-8')) > HELP_MAX_BYTES:
            return None
        status, body = self._call('POST', '/api/help', payload, None, HELP_TIMEOUT)
        if status == 503:
            self.sleep(BUSY_RETRY_SECONDS)
            status, body = self._call('POST', '/api/help', payload, None, HELP_TIMEOUT)
        receipt = body if isinstance(body, dict) else {}
        rid, token = receipt.get('id'), receipt.get('client_token')
        if status != 201 or not isinstance(rid, str) or not isinstance(token, str) \
                or not ID_RE.match(rid) or not TOKEN_RE.match(token):
            self.emit('도움 요청을 보내지 못했습니다. 설치 결과와 종료 상태는 바뀌지 않습니다.')
            return None
        self.emit('도움 요청을 접수했습니다. 접수번호: ' + rid[:8])
        if not interactive:
            self.emit('이 창은 기다리지 않고 끝납니다. 담당자에게 접수번호를 알려 주세요.')
            return rid
        self.emit('담당자 답을 이 창에 표시합니다(최대 2시간). 끝내려면 Ctrl+C를 누르세요. 받은 글은 실행하지 않습니다.')
        try:
            self._poll(rid, token)
        except KeyboardInterrupt:
            pass
        finally:
            self._call('POST', '/api/help/' + rid + '/close', {}, token, HELP_TIMEOUT)
        return rid

    def _poll(self, rid, token):
        deadline = self.clock() + POLL_MAX_SECONDS
        last_seq, first = 0, True
        while True:
            if not first:
                if self.clock() + POLL_SECONDS > deadline:
                    return
                self.sleep(POLL_SECONDS)
            first = False
            status, body = self._call('GET', '/api/help/' + rid, None, token, HELP_TIMEOUT)
            if status in (404, 410):
                return
            if status != 200 or not isinstance(body, dict) or not isinstance(body.get('messages'), list):
                continue
            fresh = [m for m in body['messages'] if isinstance(m, dict) and m.get('kind') == 'text'
                     and type(m.get('seq')) is int and m['seq'] > last_seq]
            for message in sorted(fresh, key=lambda m: m['seq']):
                last_seq = message['seq']
                self.emit(clean_display(message.get('body', '')))


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """Refuse every redirect so the token/payload can never follow to another host."""
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _read_capped(fp, cap):
    data = fp.read(cap + 1)
    if len(data) > cap:
        raise ValueError('response too large')
    try:
        return json.loads(data.decode('utf-8')) if data.strip() else None
    except ValueError:
        return None


def urllib_transport(base_url):
    opener = urllib.request.build_opener(_NoRedirect())

    def send(method, path, payload, token, timeout):
        headers = {'Content-Type': 'application/json'}
        if token:
            headers['x-help-client'] = token
        data = None if payload is None else json.dumps(payload).encode('utf-8')
        request = urllib.request.Request(base_url + path, data=data, method=method, headers=headers)
        try:
            response = opener.open(request, timeout=timeout)
        except urllib.error.HTTPError as error:
            response = error
        with response:
            status = response.status if hasattr(response, 'status') else response.code
            return status, _read_capped(response, RESPONSE_MAX_BYTES)
    return send


def _install_id(wave_home):
    path = Path(wave_home) / 'install-id.txt'
    try:
        value = path.read_text(encoding='ascii').strip()
    except OSError:
        value = ''
    if not ID_RE.match(value):
        value = uuid.uuid4().hex
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(value + '\n', encoding='ascii')
    return value


def _read_tail(path, limit=LOG_MAX_BYTES * 2):
    try:
        with open(path, 'rb') as handle:
            handle.seek(0, os.SEEK_END)
            handle.seek(max(0, handle.tell() - limit))
            return handle.read().decode('utf-8', 'replace')
    except OSError:
        return ''


def _env_report(wave_home, version, step):
    lines = ['os=mac', 'installer_version=' + version, 'step=' + step,
             'platform=' + platform.platform(), 'machine=' + platform.machine(),
             'python=' + platform.python_version(), 'shell=' + os.environ.get('SHELL', '')]
    state = _read_tail(Path(wave_home) / 'install-state.json', ENV_MAX_BYTES)
    if state:
        lines += ['install-state.json:', state]
    return '\n'.join(lines)


def main(argv=None):
    if os.environ.get('WAVE_NO_PROGRESS') == '1':
        return 0
    parser = argparse.ArgumentParser(description='Wave installer help client (fail-open)')
    parser.add_argument('command', choices=('progress', 'help'))
    parser.add_argument('--notice-shown', action='store_true')
    parser.add_argument('--version', default='unknown')
    parser.add_argument('--step', default='1/10')
    parser.add_argument('--event', default='start', choices=('start', 'end', 'wait', 'fail'))
    parser.add_argument('--detail', default='')
    parser.add_argument('--code', default='J-UNK-00')
    parser.add_argument('--log-file', default='')
    parser.add_argument('--interactive', action='store_true')
    try:
        args = parser.parse_args(argv)
    except SystemExit:
        return 0
    if not args.notice_shown:
        return 0
    try:
        wave_home = os.environ.get('WAVE_HOME') or os.path.join(os.path.expanduser('~'), '.wave')
        base = os.environ.get('WAVE_HELP_BASE_URL') or DEFAULT_BASE_URL
        try:
            username = os.environ.get('USER') or getpass.getuser()
        except Exception:
            username = ''
        client = HelpClient(base, _install_id(wave_home), args.version, notice=True, username=username,
                            emit=lambda line: print(line, flush=True))
        if args.command == 'progress':
            client.emit = lambda line: None
            return 0 if client.progress(args.step, args.event, detail=args.detail) else 3
        client.help(args.step, args.code, _env_report(wave_home, client.version, args.step),
                    _read_tail(args.log_file) if args.log_file else '', args.interactive)
    except Exception:
        return 3 if args.command == 'progress' else 0
    return 0


if __name__ == '__main__':
    sys.exit(main())
