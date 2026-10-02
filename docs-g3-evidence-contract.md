# G3 설치기 증거 계약

0142·0151 승인에 따라 20KB 상한은 사용하지 않는다. master·cso·worker 각각 설치된 directive SHA256이 앱의 `cys pack-manifest`와 같고, SessionStart 훅 stdout에 그 원본의 전체 바이트가 포함되어야 한다. 활성 팩의 `*.new`가 0개여야 한다.

## 입력

`$WAVE_HOME/verify/`에 다음 파일을 함께 제공한다.

- `G3_inject.json`: `roles` 객체의 키는 정확히 master, cso, worker. 각 항목은 `injected_sha256`, `pack_sha256`(64자리 16진수), `injected_bytes`, `pack_bytes`(양의 정수)를 가진다.
- `hook_master.out`, `hook_cso.out`, `hook_worker.out`: 실제 SessionStart 훅의 stdout 원시 바이트. 앞뒤의 헤더·오버레이는 허용하지만 원본 본문은 바이트 그대로 포함되어야 한다.

설치기는 실행 중인 앱 manifest와 설치된 원본을 다시 읽는다. 영수증 수치만 신뢰하지 않고 stdout의 본문 포함 여부를 직접 검사한다. 팩·directive·stdout 심링크는 거부한다. 활성 팩을 직접 검색해 .new 잔여를 판정한다. 백업 폴더는 활성 팩 검색 범위 밖이다.

## 상태 및 한계

영수증이 없으면 S08은 `unmeasured`이며 설치 완료 관문을 통과하지 않는다. 원본·stdout·영수증 불일치나 .new 잔여는 실패한다. 성공 관측값은 `original_match: true`, `new_file_count: 0`이다.

W6 RC 수집기는 같은 이름의 stdout 파일을 제공한다. 수집 산출물을 위 입력 경로에 전달하는 실제 설치 연동은 별도 확인이 필요하다. 파일 검증은 기록된 stdout의 내용 일치를 증명하며 실제 로그인·LLM 각성을 증명하지 않는다. 승인된 실제 3석 각성 확인은 G9에서 별도로 수행한다. 기존 stdout의 실행 시점까지 인증하는 계약은 이번 변경에 포함되지 않는다.

근거 및 신뢰도: bootstrap.sh의 verify_original_injection, bootstrap.ps1의 Test-OriginalInjection, tests/test_macos_g3.py 및 tests/windows_g3_fixture.ps1 — confidence: High(격리 fixture 검증 범위).

## 독립 검토 잔여 — REVISE

현재 소비기는 과거 receipt/stdout 재사용을 차단하지 못한다. 독립 검토자는 파일 mtime을 1970년으로 설정하고 SessionStart를 실행하지 않아도 내용 일치가 통과함을 격리 재현했다. 따라서 이 변경은 내용 검증 체크포인트이며 G3 최종 완료로 판정하지 않는다. producer와 이번 실행의 run-id 및 역할별 surface/session 식별자를 결속하는 후속 계약이 필요하다.
