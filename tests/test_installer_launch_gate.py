import importlib.util
from pathlib import Path
import shutil
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('launch_gate', ROOT / 'scripts/check-installer-launch.py')
gate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate)


class LaunchGateTests(unittest.TestCase):
    def test_tree_passes_and_real_launch_mutations_fail(self):
        self.assertEqual(gate.check(ROOT), [])
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            shutil.copyfile(ROOT / 'win-start.ps1', root / 'win-start.ps1')
            original = (ROOT / 'bootstrap.ps1').read_text(encoding='utf-8-sig')
            for helper in ('Invoke-NsisSetup', 'Start-WaveDetached', 'Invoke-BoundedCheck'):
                start = original.index('function ' + helper + '(')
                changed = original[:start] + original[start:].replace('"$env:SystemRoot\\System32\\cmd.exe"', '$ArtifactPath', 1)
                (root / 'bootstrap.ps1').write_text(changed, encoding='utf-8-sig')
                self.assertTrue(gate.check(root), helper)
            (root / 'bootstrap.ps1').write_text(original, encoding='utf-8-sig')
            literal = '\n'.join("$neverExecuted = @'\n" + line + "\n'@" if 'Start-Process -FilePath' in line else line for line in original.splitlines())
            (root / 'bootstrap.ps1').write_text(literal, encoding='utf-8-sig')
            self.assertTrue(gate.check(root), 'here-string launch text is not executable')
            (root / 'bootstrap.ps1').write_text(original, encoding='utf-8-sig')
            entry = (root / 'win-start.ps1').read_bytes()
            (root / 'win-start.ps1').write_bytes(b'\xef\xbb\xbf' + entry)
            self.assertTrue(gate.check(root))


if __name__ == '__main__':
    unittest.main()
