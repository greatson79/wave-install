import os
import pty
import subprocess
import tarfile
import hashlib
import fcntl
import termios
import unittest

from test_one_line import Sandbox


class LoginTty(unittest.TestCase):
    def setUp(self):
        self.sb = Sandbox(self)
        self.sb.stub('claude', '''
if [ "$2" = status ]; then [ -f "$CLAUDE_CONFIG_DIR/loggedin" ]; exit; fi
python3 -c 'import os; open(os.environ["FAKE"] + "/input", "w").write(os.ttyname(0) if os.isatty(0) else "pipe")'
touch "$CLAUDE_CONFIG_DIR/loggedin"
''')
        self.master, self.slave = pty.openpty()
        self.addCleanup(os.close, self.master)
        self.addCleanup(os.close, self.slave)

    def run_auth(self, stdin, ps_tty=None):
        if ps_tty is not None:
            self.sb.stub('ps', 'echo "' + ps_tty + '"')
        script = 'source "$1"; claude_seat_auth'
        return subprocess.run(['bash', '-c', script, 'test', str(self.sb.lib())],
                              stdin=stdin, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                              env=self.sb.env, timeout=10)

    def test_existing_terminal_is_preserved(self):
        self.sb.stub('ps', 'exit 99')
        result = self.run_auth(self.slave)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((self.sb.fake / 'input').read_text(), os.ttyname(self.slave))

    def test_pipe_uses_real_terminal_device(self):
        with open(os.devnull, 'rb') as pipe:
            result = self.run_auth(pipe, os.ttyname(self.slave).removeprefix('/dev/'))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((self.sb.fake / 'input').read_text(), os.ttyname(self.slave))

    def test_missing_terminal_falls_back(self):
        with open(os.devnull, 'rb') as pipe:
            result = self.run_auth(pipe, 'not-a-terminal')
        self.assertIn(b'/dev/tty', result.stderr)
        self.assertEqual((self.sb.fake / 'input').read_text(), 'pipe')

    def test_piped_pack_restart_passes_real_terminal_to_login(self):
        package = self.sb.tmp / 'package'
        (package / 'wave-pack').mkdir(parents=True)
        (package / 'steps.json').write_text('{}')
        (package / 'bootstrap.sh').write_text('#!/bin/bash\nclaude auth login\n')
        archive = self.sb.tmp / 'pack.tar.gz'
        with tarfile.open(archive, 'w:gz') as tar:
            tar.add(package, arcname='package')
        digest = hashlib.sha256(archive.read_bytes()).hexdigest()
        tty_path = os.ttyname(self.slave)

        def controlling_tty():
            os.setsid()
            fcntl.ioctl(self.slave, termios.TIOCSCTTY, 0)

        account = self.sb.home / 'account'
        account.mkdir()
        env = dict(self.sb.env, CLAUDE_CONFIG_DIR=str(account), WAVE_INSTALL_TARBALL_URL=archive.as_uri(),
                   WAVE_INSTALL_TARBALL_SHA256=digest)
        result = subprocess.run(['bash', '-c', 'source "$1"; FROM_STDIN=1; ensure_pack',
                                 'test', str(self.sb.lib())], input=b'', stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, env=env, preexec_fn=controlling_tty,
                                timeout=15)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((self.sb.fake / 'input').read_text(), tty_path)
