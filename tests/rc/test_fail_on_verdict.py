#!/usr/bin/env python3
"""CI judge result must fail when its saved verdict table contains FAIL."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

CHECK = Path(__file__).with_name('fail-on-verdict.py')


class FailOnVerdictTests(unittest.TestCase):
    def test_fail_cell_fails_job_after_both_tables_exist(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            standard = [{'id': 'G2', 'mac': ['FAIL', 'C43.serena'], 'win': ['PASS', '']},
                        {'id': 'G9', 'common': ['미측정', '실기 대기']}]
            korean = [{'id': 'G1', 'win': ['PASS', '']}]
            (root / 'gate-result.json').write_text(json.dumps(standard), encoding='utf-8')
            (root / 'gate-result-kr.json').write_text(json.dumps(korean), encoding='utf-8')
            r = subprocess.run([sys.executable, str(CHECK), str(root / 'gate-result.json'), str(root / 'gate-result-kr.json')],
                               capture_output=True, text=True)
            self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
            self.assertIn('G2.mac=FAIL', r.stderr)
            workflow = (CHECK.parents[2] / '.github/workflows/rc-gates.yml').read_text(encoding='utf-8')
            call = 'python3 tests/rc/fail-on-verdict.py gate-result.json gate-result-kr.json'
            self.assertIn(call, workflow)
            self.assertGreater(workflow.index(call), workflow.index('gate.py evidence-kr --json > gate-result-kr.json'))
            marker = root / 'after-judge'
            job = subprocess.run(['bash', '-e', '-c', 'python3 "$1" "$2" "$3"; : > "$4"', '_',
                                  str(CHECK), str(root / 'gate-result.json'), str(root / 'gate-result-kr.json'), str(marker)],
                                 capture_output=True, text=True)
            self.assertEqual(job.returncode, 1, job.stdout + job.stderr)
            self.assertFalse(marker.exists())
            standard[0]['mac'][0] = 'PASS'
            (root / 'gate-result.json').write_text(json.dumps(standard), encoding='utf-8')
            r = subprocess.run([sys.executable, str(CHECK), str(root / 'gate-result.json'), str(root / 'gate-result-kr.json')],
                               capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)


if __name__ == '__main__':
    unittest.main()
