#!/usr/bin/env python3
"""설치기 단위 시험 전체 실행기. 결과 끝에 「맥 전용 N개 건너뜀」을 따로 출력한다(platform_scope.MAC_ONLY 사유만 센다).
사용: python tests/run_unit_suite.py   (PowerShell 5.1 단계는 PWSH 를 Windows PowerShell 로 고정한 뒤 이것을 실행한다)"""
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from platform_scope import MAC_ONLY  # noqa: E402


def main():
    suite = unittest.defaultTestLoader.discover(str(HERE))
    result = unittest.TextTestRunner(verbosity=1).run(suite)
    mac = [s for s in result.skipped if str(s[1]).startswith(MAC_ONLY)]
    other = len(result.skipped) - len(mac)
    print('맥 전용 %d개 건너뜀 (그 밖의 skip %d개 · 실행 %d개 · 실패 %d · 오류 %d)'
          % (len(mac), other, result.testsRun, len(result.failures), len(result.errors)))
    for name in sorted({str(s[0]).split(' ')[1].strip('()').rsplit('.', 1)[0] if ' ' in str(s[0]) else str(s[0]) for s in mac}):
        print('  맥 전용: ' + name)
    return 0 if result.wasSuccessful() else 1


if __name__ == '__main__':
    sys.exit(main())
