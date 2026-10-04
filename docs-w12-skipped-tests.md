# W12 macOS 회귀에서 건너뛴 Windows 검증 6개

실측: `PWSH=/tmp/wave-v024-pwsh/pwsh python3 -m unittest discover -v -s tests`, 79 tests / 실패0 / skipped6 / 96.239초. 로그: `<작업 폴더>/W12_회귀_fixture.log`. 이름 변경 전 실행 로그의 S07/S08 구 이름은 아래 새 이름과 같은 테스트다.

| 테스트 | 건너뛴 사유 |
|---|---|
| test_real_ntfs_webmark_is_only_removed_after_hash_match | macOS에는 Windows NTFS Zone.Identifier 스트림이 없어 실제 다운로드 표시 제거를 검증할 수 없다. |
| test_s08_preserves_native_exit_and_stderr_with_three_role_evidence | 성공한 native stderr를 오류로 취급하는 Windows PowerShell 5.1 동작은 macOS PowerShell 7로 재현할 수 없다. |
| test_s07_requires_master_marker_and_three_live_roles | Windows Run-S07 계약 테스트로 OS 제한을 유지했다; 외부 호출을 mock한 본문은 macOS pwsh에서도 별도 실행해 통과했다. |
| test_bounded_check_kills_sleeping_child_without_waiting_for_sleep | powershell.exe 자식 프로세스 종료·시간 제한의 실제 Windows 동작을 확인해야 한다. |
| test_shared_check_log_reads_while_writer_is_open | Windows 파일 공유 모드와 배타적 읽기 실패 대조군을 macOS에서 동등하게 검증할 수 없다. |
| test_s08_locked_log_read_failure_is_unmeasured_and_reaches_s09 | Windows 배타 잠금으로 진단 로그 읽기가 실패하는 조건이 필요하다. |

이 표는 실제 Windows 실행 PASS를 대신하지 않는다. 출처: tests/test_windows_bootstrap.py의 skipUnless 조건 및 위 unittest 로그. confidence: High(현재 실행환경과 skip 이유).
