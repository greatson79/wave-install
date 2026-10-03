"""Portable ordering checks; the Windows runner also measures real PID cleanup."""
import subprocess
import unittest
from unittest.mock import MagicMock, patch

import windows_job


class JobOrderingTests(unittest.TestCase):
    def fixtures(self, timeout=False):
        events = []
        api = MagicMock()
        api.CreateJobObjectW.return_value = 42
        api.SetInformationJobObject.return_value = True
        api.AssignProcessToJobObject.side_effect = lambda *_: events.append('assigned') or True
        api.CloseHandle.side_effect = lambda *_: events.append('closed') or True
        process = MagicMock()
        process._handle = 99
        process.returncode = 0
        calls = 0

        def communicate(**kwargs):
            nonlocal calls
            calls += 1
            if calls == 1:
                self.assertEqual(kwargs['input'], b'G')
                self.assertIn('assigned', events)
                events.append('gate')
                if timeout:
                    raise subprocess.TimeoutExpired(['child'], 1)
            if timeout and calls > 1:
                self.assertIn('closed', events)
                self.assertEqual(kwargs['timeout'], 10)
                events.append('bounded-drain')
            return b'output', b'error'

        process.communicate.side_effect = communicate
        return api, process, events

    def test_assign_precedes_gate_and_success_closes_job(self):
        api, process, events = self.fixtures()
        with patch.object(windows_job, '_kernel', return_value=api), patch.object(windows_job.subprocess, 'Popen', return_value=process):
            result = windows_job.run_in_job(['powershell.exe', '-Command', 'literal'], timeout=1)
        self.assertEqual(result.stdout, b'output')
        self.assertEqual(events, ['assigned', 'gate', 'closed'])
        api.CloseHandle.assert_called_once_with(42)

    def test_timeout_closes_tree_before_bounded_pipe_drain(self):
        api, process, events = self.fixtures(timeout=True)
        with patch.object(windows_job, '_kernel', return_value=api), patch.object(windows_job.subprocess, 'Popen', return_value=process):
            with self.assertRaises(subprocess.TimeoutExpired) as error:
                windows_job.run_in_job(['powershell.exe'], timeout=1)
        self.assertEqual(error.exception.output, b'output')
        self.assertEqual(events[:3], ['assigned', 'gate', 'closed'])
        self.assertIn('bounded-drain', events)
        api.CloseHandle.assert_called_once_with(42)


if __name__ == '__main__':
    unittest.main(verbosity=2)
