"""Mutants for help-table consistency and the portable syntax precheck."""
import importlib.util
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('balance', ROOT/'tests/ps-balance.py')
balance = importlib.util.module_from_spec(spec)
spec.loader.exec_module(balance)

class CheckTests(unittest.TestCase):
    def test_delimiter_mutants(self):
        cases = [
            ('function f { @("[]", \'{}\') } # ]', True),
            ('function f {', False), ('([)]', False),
            ("<# unterminated", False), ("'unterminated", False),
            ('"unterminated', False), ("@'\nunterminated", False),
            ("@'\n} [ (\n'@\n@{key=1}", True),
            ("'multi\nline'\n{ }", True),
            ('<# [ <# } #> ( #>\n{}', True),
            ('`{\n@(1,2)', True),
        ]
        with tempfile.TemporaryDirectory(dir=ROOT, prefix='.balance-test-') as td:
            path = Path(td)/'sample.ps1'
            for source, ok in cases:
                with self.subTest(source=source):
                    path.write_text(source)
                    self.assertEqual(not balance.check(path), ok)

    def test_help_mutants(self):
        with tempfile.TemporaryDirectory(dir=ROOT, prefix='.help-test-') as td:
            root = Path(td)
            paths = ['tests/help-rules.tsv', 'docs/help-codes.md', 'bootstrap.ps1']
            originals = {}
            for name in paths:
                dest = root/name
                dest.parent.mkdir(parents=True, exist_ok=True)
                originals[name] = (ROOT/name).read_text(encoding='utf-8-sig')
                dest.write_text(originals[name])
            def run():
                return subprocess.run([sys.executable, str(ROOT/'tests/help-rules-check.py'), '--root', str(root)], capture_output=True, text=True)
            self.assertEqual(run().returncode, 0)
            for name in paths:
                with self.subTest(name=name):
                    (root/name).write_text(originals[name].replace('J-PS32-01', 'J-PS32-99'))
                    self.assertNotEqual(run().returncode, 0)
                    (root/name).write_text(originals[name])

if __name__ == '__main__':
    unittest.main(verbosity=2)
