"""Status transport/storage failures retain their cause; no byte-limit assertions changed."""
import unittest
import test_windows_bootstrap as helpers

class StatusIOTests(unittest.TestCase):
    def test_status_timeout_retains_timeout_category(self):
        helpers.BootstrapTests().run_ps(r'''
function Say { param($Message) }
function Invoke-BoundedCheck {
  param($FilePath,$Arguments,$Name,$TimeoutMs)
  return [pscustomobject]@{timed_out=($Name -eq 'fleet-status');timeout_ms=$TimeoutMs;exit_code=0;stdout='{}';stderr='';kill_error=$null}
}
Run-S08
if ($StepStatus -ne 'unmeasured' -or $StepObserved.reason -ne 'timeout' -or $StepObserved.timed_out_command -ne 'cys status --json') { throw 'status timeout cause lost' }
''')

    def test_status_storage_error_is_recorded(self):
        helpers.BootstrapTests().run_ps(r'''
function Say { param($Message) }
function Invoke-BoundedCheck {
  param($FilePath,$Arguments,$Name,$TimeoutMs)
  return [pscustomobject]@{timed_out=$false;timeout_ms=$TimeoutMs;exit_code=0;stdout='{"surfaces":[]}';stderr='';kill_error=$null}
}
function Set-Content { param($LiteralPath,$Value,$Encoding); throw 'fixture status.json access denied' }
Run-S08
if ($StepStatus -ne 'unmeasured' -or $StepObserved.reason -ne 'call_failed' -or $StepObserved.detail -notmatch 'status.json access denied') { throw 'status storage failure escaped' }
''')

    def test_invalid_status_json_is_recorded(self):
        helpers.BootstrapTests().run_ps(r'''
function Say { param($Message) }
function Invoke-BoundedCheck {
  param($FilePath,$Arguments,$Name,$TimeoutMs)
  return [pscustomobject]@{timed_out=$false;timeout_ms=$TimeoutMs;exit_code=0;stdout='not-json';stderr='';kill_error=$null}
}
Run-S08
if ($StepStatus -ne 'unmeasured' -or $StepObserved.reason -ne 'call_failed') { throw 'malformed status accepted' }
''')

if __name__=='__main__': unittest.main()
