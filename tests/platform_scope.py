"""시험의 실행 범위 표지. 윈 호스트(PowerShell 5.1 단계)에서 맥 bash 설치기를 돌리는 시험은 「맥 전용」으로 명시하고
tests/run_unit_suite.py 가 건너뛴 개수를 출력한다. WAVE_TEST_SCOPE=windows 는 맥에서 윈 범위를 흉내 내 선택이 빠짐없는지 확인하는 용도."""
import os
import unittest

IS_WINDOWS = os.name == 'nt' or os.environ.get('WAVE_TEST_SCOPE') == 'windows'
MAC_ONLY = 'mac-only:'


def mac_only(reason='macOS bootstrap.sh/make-release.sh 를 bash 로 실행한다'):
    return unittest.skipIf(IS_WINDOWS, MAC_ONLY + ' ' + reason)


def skip_bash_engine(case, engine):
    """엔진을 나눠 도는 시험에서 bash 엔진 회차만 맥 전용으로 건너뛴다(건너뛴 회차가 개수에 잡힌다)."""
    if engine == 'bash' and IS_WINDOWS:
        case.skipTest(MAC_ONLY + ' bash 엔진 회차')


def write_fake_exe(path, pwsh, stdout='', code=0):
    """시험용 가짜 cys. 윈에서는 셸 스크립트가 실행 파일이 아니므로 PowerShell Add-Type 으로 진짜 콘솔 exe 를 만든다(맥·리눅스는 셸 스크립트)."""
    import subprocess
    from pathlib import Path
    path = Path(path)
    if os.name == 'nt' and path.suffix.lower() == '.exe':
        src = 'public class FakeExe { public static int Main(string[] a) { System.Console.Write("%s"); return %d; } }' % (stdout, code)
        cmd = "Add-Type -OutputAssembly $env:FAKE_EXE_OUT -OutputType ConsoleApplication -TypeDefinition $env:FAKE_EXE_SRC"
        r = subprocess.run([pwsh, '-NoProfile', '-Command', cmd], env=dict(os.environ, FAKE_EXE_OUT=str(path), FAKE_EXE_SRC=src), capture_output=True, text=True)
        if r.returncode:
            raise RuntimeError('가짜 exe 컴파일 실패: ' + r.stdout + r.stderr)
    else:
        path.write_text('#!/bin/sh\n%sexit %d\n' % (("printf '%s'\n" % stdout) if stdout else '', code))
        path.chmod(0o755)
