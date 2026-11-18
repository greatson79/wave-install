"""C11: GUI-open refusal precedes the first installer mutation, including stdin download."""
try:
    import rig_guard  # noqa: F401
except ImportError:
    from tests import rig_guard  # noqa: F401
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class AppOpenPreflight(unittest.TestCase):
    def run_guard(self, processes, probe_rc=0, stdin=False, uname_rc=0):
        with tempfile.TemporaryDirectory(prefix='appopen-') as td:
            root = Path(td)
            home = root / 'home'
            home.mkdir()
            (home / 'record').write_text('keep\n')
            fake = root / 'bin'
            fake.mkdir()
            for name, body in {
                'uname': 'echo Darwin; exit "$UNAME_RC"',
                'ps': 'printf "%s\\n" "$PROCESSES"; exit "$PROBE_RC"',
                'lsof': 'exit 97',
                'pgrep': 'exit 97',
            }.items():
                p = fake / name
                p.write_text('#!/bin/sh\n' + body + '\n')
                p.chmod(0o755)
            # Keep real main ordering; stop at the first would-write operation.
            source = (ROOT / 'bootstrap.sh').read_text().rsplit('\nmain "$@"', 1)[0]
            source += '\nensure_pack() { echo FIRST_WRITE_REACHED >&2; return 73; }\nmain\n'
            env = dict(os.environ, HOME=str(home), WAVE_HOME=str(home / '.wave'),
                       PATH=str(fake) + os.pathsep + os.environ['PATH'],
                       PROCESSES=processes, PROBE_RC=str(probe_rc), UNAME_RC=str(uname_rc), WAVE_NO_PROGRESS='1')
            if stdin:
                result = subprocess.run(['bash'], input=source, env=env, text=True, capture_output=True, timeout=15)
            else:
                script = root / 'bootstrap.sh'
                script.write_text(source)
                result = subprocess.run(['bash', str(script)], env=env, text=True, capture_output=True, timeout=15)
            self.assertEqual(sorted(str(p.relative_to(home)) for p in home.rglob('*')), ['record'])
            self.assertEqual((home / 'record').read_text(), 'keep\n')
            return result

    def test_gui_paths_refuse_before_first_write(self):
        for bundle, binary in [('Wave Terminal.app', 'wave-app'), ('Wave Terminal.app', 'cys-app'), ('cys.app', 'cys-app')]:
            for prefix in ['/Applications', '/Users/learner/Applications', '/Users/learner/.wave/apps']:
                for stdin in (False, True):
                    with self.subTest(bundle=bundle, binary=binary, prefix=prefix, stdin=stdin):
                        r = self.run_guard(f'{prefix}/{bundle}/Contents/MacOS/{binary}', stdin=stdin)
                        self.assertNotEqual(r.returncode, 0)
                        self.assertIn('[1/10]', r.stderr)
                        self.assertIn('Wave Terminal을 먼저 종료하세요', r.stderr)
                        self.assertNotIn('FIRST_WRITE_REACHED', r.stderr)

    def test_daemons_and_similar_names_do_not_refuse(self):
        r = self.run_guard('\n'.join([
            '/Applications/Wave Terminal.app/Contents/MacOS/waved',
            '/Applications/cys.app/Contents/MacOS/cysd',
            '/Applications/Other.app/Contents/MacOS/wave-app',
            '/tmp/wave-app',
            '/Applications/Wave Terminal.app/Contents/MacOS/wave-app-helper',
        ]))
        self.assertEqual(r.returncode, 1)
        self.assertIn('FIRST_WRITE_REACHED', r.stderr)
        self.assertNotIn('먼저 종료하세요', r.stderr)

    def test_empty_process_table_does_not_refuse(self):
        self.assertIn('FIRST_WRITE_REACHED', self.run_guard('').stderr)

    def test_unreadable_process_table_fails_closed(self):
        r = self.run_guard('', probe_rc=97)
        self.assertNotEqual(r.returncode, 0)
        self.assertNotIn('FIRST_WRITE_REACHED', r.stderr)
        self.assertIn('실행 상태를 확인할 수 없습니다', r.stderr)

    def test_unreadable_platform_fails_closed(self):
        r = self.run_guard('', uname_rc=97)
        self.assertNotEqual(r.returncode, 0)
        self.assertNotIn('FIRST_WRITE_REACHED', r.stderr)
        self.assertIn('확인할 수 없습니다', r.stderr)
