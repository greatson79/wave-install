# W12 회귀 12개 실패 분류 — 0130 브리프

대상: 794f522 작업 중 실행한 전체 회귀 72 tests의 실패 항목 12개(서브테스트 포함). 원문 로그: `/Users/kylechoi/Desktop/Ai_works/개발본부/_round/inbox_펄스/워커_W12_전체회귀_0126.log`.

정본 계획: `/Users/kylechoi/Desktop/Ai_works/output/WaveAI/프로젝트/WaveInstall/계획_원본팩자체운영_무오류설치_v1_2026-10-03.md` §1·P2 W1/W2·P3 G3/G4/G5. 추가 0119의 master/cso/worker 3석은 구 2석 계약보다 우선한다. **20KB 상한·바이트 측정 판정·관련 테스트는 결재 전 동결한다.**

| # | 실패 항목 | 분류 | 근거 및 조치 |
|---|---|---|---|
| 1 | state_contract: bytes_contract_and_display_copies | 코드 결함 | 로그 9행: steps/site 사본 불일치. 20KB assertion 실패가 아님. e0056fb 사본 동기화 완료; 테스트는 수정하지 않는다. |
| 2 | S08 unmeasured/bash (null,null) | 테스트가 옛 계약 | tests/test_state_contract.py 39~65: roles.json 2석/doctor만 준비하며 현재 S07의 master-ref·status·부트표지가 없음(로그18행). 계획 P3 G4 실제 부트 확인으로 바뀜. 단 바이트 판정과 한 테스트로 묶여 있으므로 결재 전 수정 보류. |
| 3 | S08 unmeasured/bash (null,10) | 테스트가 옛 계약 | #2와 동일, 로그28행. G4의 실제 부트 증거 누락; 바이트 관련 테스트 동결. |
| 4 | S08 unmeasured/bash (0,10) | 판정 불가 | 누락 master-ref(로그38행)로 바이트 측정 분기까지 못 감. 10바이트 실측을 기대하는 종전 입력과 현재 status 미제공 계약은 20KB 상신 결과에 의존. 코드/테스트 변경 보류. |
| 5 | S08 unmeasured/PS (null,null) | 코드 결함 | 로그48행: verify/status.json 쓰기 실패가 unmeasured 경계 밖으로 탈출. mock이 verify 폴더 생성 부수효과를 생략했으나 실제 쓰기권한 실패도 같은 경로로 탈출한다. 저장 실패를 구조화하여 기록하는 경계 수리, 바이트 조건 유지. |
| 6 | S08 unmeasured/PS (null,10) | 코드 결함 | #5와 동일, 로그58행. 저장 오류 경계를 수리하되 기존 doctor fixture는 G4 구계약이 함께 섞여 있어 테스트는 동결. |
| 7 | S08 unmeasured/PS (0,10) | 판정 불가 | 저장 오류(로그68행) 이후 측정 입력 계약도 #4와 같이 상신 대상. 쓰기경계만 수리, 바이트 판정/테스트는 보류. |
| 8 | version_gate: public_configuration_is_resolved_and_copies_match | 코드 결함 | 로그78행: #1과 동일한 공개 사본 drift. e0056fb에서 동기화, 기존 version_gate 4 tests 재통과. |
| 9 | windows_bootstrap: main_rerun_expires_resumes_and_reinstall_bypasses_marker | 테스트가 옛 계약 | 테스트64행은 만료 재실행에서 S06 미실행을 요구. 계획 §1 원본팩 설치·P3 G3 원본바이트/G5 업그레이드 재검증에 따라 S06 다시 실행해야 함. assertion만 갱신 가능. |
| 10 | windows_bootstrap: s05_registers_quoted_hkcu_value_and_verifies_readback | 테스트가 옛 계약 | 테스트275~303행은 HKCU 직접 등록/읽기 대조를 요구. 계획 §1·P2 W1/W2는 `cys daemon install`·유계 ping·직접 실행 폴백. 초기 브리프2번에서 자체 HKCU/schtasks 제거 명시. CLI/폴백 fixture로 교체 가능. |
| 11 | windows_bootstrap: s08_timeout_and_call_failure_allow_s09_without_false_measurements | 코드 결함 | 로그151~165행: 상태 저장 오류 탈출; status timeout도 Get-LiveFleet 문자열 예외로 바뀌어 timeout/call_failed 구분 소실. 명령 결과·저장·JSON 경계를 수리. 기존 fixture는 doctor 이름을 쓰므로 그대로 두고 새 status 전용 I/O 회귀를 추가한다. 바이트 조건은 수정 금지. |
| 12 | windows_bootstrap: step_numbers_resume_and_failed_dispatch | 테스트가 옛 계약 | 테스트441~452행은 S06 status=passed이면 resume skip을 요구. #9와 같은 §1·G3/G5 변경. S06 재측정 assertion으로 갱신 가능. |

각 분류의 신뢰도 High=테스트 본문/로그 직접 대조. #4/#7의 최종 바이트 판정은 미확정이며 결론 보류. 같은 실패에 fixture 구계약과 오류 경계 결함이 함께 있는 경우, 표의 분류는 먼저 관찰된 실패 또는 판단을 막는 지점 기준이다.

발동 스킬: systematic-debugging, hallucination-guard, test-driven-development, verification-before-completion.

## 수리·검증 결과

- Windows S08는 status 명령의 timeout/exit 결과를 직접 보존하고, JSON 해석·디렉터리 생성·상태 저장·각성 판정을 한 예외 경계로 묶었다. timeout은 `unmeasured/timeout`, 나머지 호출·저장 오류는 `unmeasured/call_failed`로 남긴다. null을 실측값으로 바꾸지 않았다.
- 새 `tests/test_windows_s08_io.py`의 저장 실패·status timeout을 기존 코드에서 RED로 확인하고 수리 후 JSON 오류까지 3건 GREEN. 독립 내부 검수자도 지정 PowerShell로 3건 PASS 확인.
- 구 계약으로 분류한 Windows #9/#10/#12만 수정했다. #10 새 테스트명은 `test_s05_registers_via_cli_and_checks_bounded_fallbacks`; 외부 I/O는 모두 mock이며 직접 레지스트리 호출을 하면 실패한다. 이 3개 독립 실행 PASS.
- 양 OS 완료 판정 함수, steps S08 bytes_lte=20480 객체, `tests/test_state_contract.py` 전체 파일이 작업 직전 HEAD와 바이트 동일함을 검산했다. R5는 API 계약 미수신으로 착수하지 않았다.

## 재실행 — 78 tests, failures 8, skipped 6 (170.008s)

전체 로그: `/Users/kylechoi/Desktop/Ai_works/개발본부/_round/inbox_펄스/워커_W12_회귀재실행_0145.log`.

| 잔여 | 개수 | 관찰 및 처리 |
|---|---:|---|
| doctor producer 좌석 수=2 assertion (양 OS) | 2 | 추가0119가 3석으로 바꾼 부분. null 주입량 검사와 같은 동결 테스트에 있어 이 턴에는 그대로 보존. |
| Bash S08 (null,null)/(null,10)/(0,10) | 3 | 구 fixture는 S07 master-ref/표지를 만들지 않음. 실제 부트 확인으로 바뀐 입력과 기존 바이트 fixture를 결재 후 분리해야 함. |
| PS S08 (0,10) | 1 | 구 doctor 입력을 실측값으로 기대하나 현재 status 경로는 그 입력을 소비하지 않아 미측정(false). 실제 측정 계약 정렬 필요. |
| PS S08 (20481,10) | 1 | 종전에는 앞선 저장 실패 때문에 비정상 종료해 이 테스트가 겉으로 통과했음. 저장 실패를 정상적으로 기록하자 '초과 바이트 입력 거부' 기대가 실패함. 단 현재 fixture의 doctor 바이트는 status 경로에 전달되지 않으므로 실기에서 상한 초과를 승인했다는 증거는 아님. **기존 초과 측정 테스트의 검증력이 사라진 상태를 상급에 명시**하고, 동결 지시에 따라 관련 게이트/테스트 수정 보류. 완료 요약은 미측정이라 complete를 막는다. |
| PS timeout/call_failure 구 doctor 이름 | 1 | fixture가 doctor에 timeout을 주입하지만 코드는 fleet-status를 호출. 새 status 전용 회귀에서는 timeout 분류 보존 확인. 기존 S08 테스트는 동결 범위로 보존. |

위 8개를 제외하거나 xfail/skip으로 바꾸지 않았다. 전체 GREEN이 아니며 출시 관문 통과 주장 없음.
