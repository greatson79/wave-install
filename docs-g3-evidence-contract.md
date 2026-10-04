# G3 설치기와 RC 러너의 경계

설치기 S08은 설치된 팩 지침 원본을 앱 `cys pack-manifest`의 SHA256과 대조하고 활성 팩의 `.new`가 0개인지 확인한다. master/cso/worker 지침이 manifest에 모두 있어야 하며 manifest에 있는 나머지 지침도 대조한다. 빈 파일·누락·변경·심링크 지침은 거부한다.

앱 manifest의 files는 경로→SHA256 구조이며 별도 바이트 수를 제공하지 않는다. 설치기는 원본 바이트 전체의 SHA를 대조하고 `pack_bytes`를 실측해 기록한다. manifest의 길이를 독립 대조했다고 주장하지 않는다.

성공 상태는 `original_match:true`, `new_file_count:0`이며 주입 측정은 `injected_bytes:null`, `injection_reason:"RC 러너 G3_inject.json 판정"`이다. 설치기는 G3_inject.json이나 hook stdout을 읽거나 생성하지 않는다. RC 러너는 같은 run에서 SessionStart 훅을 새로 실행해 본문 포함을 별도로 판정한다.

따라서 과거 stdout 재사용에 관한 종전 소비기의 수정 요청은 설치기에서 해당 소비 경로를 제거해 해소했다. 이 변경이 RC 러너 실행 성공이나 실제 로그인 각성(G9)을 증명하지는 않는다.

근거: W12 통합 요구사항 §1(별도 작업 문서); 앱 src/bin/cys.rs build_pack_manifest_value; bootstrap.sh verify_original_injection 및 bootstrap.ps1 Test-OriginalInjection; tests/test_macos_g3.py, tests/windows_g3_fixture.ps1. confidence: High(코드/격리검증 범위).
