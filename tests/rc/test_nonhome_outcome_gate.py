"""The non-home install job must gate the installer's raw exit and S07-S09 state."""
from pathlib import Path
import re
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github/workflows/rc-gates.yml"
sys.path.insert(0, str(ROOT / "tests/rc"))
import check_first_run
import check_seat_cwd


def has_first_run_gate(workflow: str) -> bool:
    match = re.search(r"(?ms)^  win-nonhome-cwd:\n(.*?)(?=^  [a-z0-9-]+:\n|\Z)", workflow)
    if not match:
        return False
    job = match.group(1)
    return (
        'check_first_run.py "$RUNNER_TEMP/ev/win/run.exit" "$RUNNER_TEMP/ev/win/G1_state.json"'
        in job
    )


class NonhomeOutcomeGateTests(unittest.TestCase):
    def test_signal_run_fixture_was_false_positive_before_and_fails_after(self):
        fixture = ROOT / "tests/rc/fixtures/nonhome-exit2-37188325110"
        old_rc, old_msg = check_seat_cwd.judge(
            str(fixture / "identity.json"),
            [str(fixture / "win/G4_status.json"), str(fixture / "win/G6/G4_status.json")],
        )
        new_rc, new_msg = check_first_run.judge(
            str(fixture / "win/run.exit"), str(fixture / "win/G1_state.json")
        )
        self.assertEqual(old_rc, 0, old_msg)
        self.assertEqual(new_rc, 1, new_msg)
        self.assertIn("exit=2 S07=failed", new_msg)

    def test_nonhome_job_checks_raw_install_exit_and_state(self):
        workflow = WORKFLOW.read_text(encoding="utf-8")
        self.assertTrue(has_first_run_gate(workflow))

    def test_mutant_without_exit_gate_is_rejected(self):
        workflow = WORKFLOW.read_text(encoding="utf-8")
        mutant = workflow.replace(
            'python3 tests/rc/check_first_run.py "$RUNNER_TEMP/ev/win/run.exit" "$RUNNER_TEMP/ev/win/G1_state.json"',
            "echo removed-outcome-blind-check",
            1,
        )
        self.assertNotEqual(mutant, workflow, "mutation did not alter the workflow")
        self.assertFalse(has_first_run_gate(mutant))


if __name__ == "__main__":
    unittest.main(verbosity=2)
