import os
import pty
import subprocess
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
