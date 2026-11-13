"""0.3.5 diagnostics: injected exceptions and scripted 410, no app binaries."""
import unittest

from tests import test_windows_bootstrap as bootstrap_fixture
from tests import test_help_client_windows as help_fixture


class AppControlTests(unittest.TestCase):
    def test_exception_identity_and_existing_codes(self):
        bootstrap_fixture.BootstrapTests().run_ps(r'''
$blocked = [ComponentModel.Win32Exception]::new(4551, 'localized text is irrelevant')
$wrapped = [InvalidOperationException]::new('outer', $blocked)
$hresult = [Runtime.InteropServices.Marshal]::GetExceptionForHR(-2147020345)
if ((Get-JCode $hresult) -ne 'J-AV-04') { throw 'HRESULT identity lost' }
foreach ($failure in @($blocked, $wrapped)) {
  if ((Get-JCode $failure) -ne 'J-AV-04') { throw 'app-control identity lost' }
}
if ((Get-JCode ([ComponentModel.Win32Exception]::new(5))) -ne 'J-UNK-00') { throw 'access denied mislabeled' }
if ((Get-JCode ([ComponentModel.Win32Exception]::new(4556))) -eq 'J-AV-04') { throw 'malicious reputation mislabeled' }
if ((Get-JCode '검증된 artifact 없음') -ne 'J-AV-02') { throw 'existing mapping lost' }
if ((Get-JCode 'an unclassified failure') -ne 'J-UNK-00') { throw 'fallback changed' }
function Start-Process { throw [ComponentModel.Win32Exception]::new(4551, 'blocked') }
function Write-Log { param($Message) }
foreach ($action in @({ Invoke-NsisSetup 'fake.exe' 'fake-dir' }, { Start-WaveDetached 'fake.exe' })) {
  try { & $action; throw 'expected failure' } catch {
    if ((Get-JCode $_.Exception) -ne 'J-AV-04') { throw 'launcher dropped identity' }
  }
}
function Start-Process { return [pscustomobject]@{ ExitCode = 4551 } }
try { Invoke-NsisSetup 'fake.exe' 'fake-dir'; throw 'expected policy failure' } catch {
  if ((Get-JCode $_) -ne 'J-AV-04') { throw 'cmd exit lost policy identity' }
}
function Invoke-BoundedCheck { throw [ComponentModel.Win32Exception]::new(4551, 'blocked') }
foreach ($action in @({ Test-DaemonReady }, { Run-S05 })) {
  try { & $action; throw 'expected policy failure' } catch {
    if ((Get-JCode $_) -ne 'J-AV-04') { throw 'daemon swallowed policy identity' }
  }
}
''')


class HelpGoneTests(unittest.TestCase):
    def test_410_receipt_has_honest_reply_channel(self):
        result = help_fixture.WindowsHelpClientParity().run_ps()
        gone = result['results']['gone_410']
        text = '\n'.join(gone['output'])
        self.assertNotIn('담당자 답을 이 창에 표시', text)
        self.assertIn('접수번호: cccccccc', text)
        self.assertIn('담당자에게 접수번호를 알려', text)
        self.assertIn('직접 안내', text)
        self.assertEqual([c['method'] for c in gone['calls']], ['POST', 'GET', 'POST'])


if __name__ == '__main__':
    unittest.main()
