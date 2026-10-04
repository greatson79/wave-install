# W12 macOS / Windows 동등성 · 검증 상태

발동 스킬: systematic-debugging, hallucination-guard, test-driven-development, verification-before-completion.

| 순서 | macOS | Windows | 근거/제한 |
|---|---|---|---|
| 앱 다운로드·지문 | S03/S04 유지 | S03/S04 유지 | 기존 해시/서명 경계 유지 |
| 원본 팩 | S06 init-pack + pack-manifest | S06 init-pack + pack-manifest | 설치기 스텁 동일 바이트만 백업, 사용자 변경 보존; 불일치/.new 실패 |
| 데몬 | S05 daemon install, ping, 앱 폴백 | S05 daemon install, ping, cysd/app 폴백 | 등록 실패는 예외 기록, 이후 각성 실측 |
| 자동 각성 | 온보딩 표지 대기 → `cys launch-agent --role master` | 같음 | S08 각성 증거 = upstream MIT Confirm-MasterAwake 축(1) 세션 기록 답 레코드 |
| 부트 확인 | 최신 master marker + live master/cso/worker | marker + live/awakened master/cso/worker | 실제 LLM 로그인·실기 설치는 이 변경에서 미실행 |
| G3 원본 일치 | 앱 manifest·설치팩 원본 바이트 SHA 대조 | 같은 계약 | 필수3역할·manifest의 전체 지침, .new 실측0; 주입은 null/RC판정 |
| 재설치 | 검증된 상태파일 백업 이동 | 상태/완료표지 검증 백업, 정확한 옛 Run 값만 정리 | 앱·bin 전체 삭제 위한 소유 manifest 없음: 삭제 구현 미완 |

## 남은 출시 관문

- 양 OS 깨끗한 러너와 실제 로그인 기기에서 자동 각성 검증.
- 검증 책임 구분: 설치기=팩 원본 SHA·.new0, 실제 hook stdout 판정=RC 러너.
- 재설치 소유 manifest 도입, 앱·pack 설치기 소유 파일만 제거하는 전체 왕복 검증.
- 설치기는 injected_bytes=null과 RC 판정 사유를 기록한다. RC 런의 실제 주입 성공은 이 검증 범위 밖이다.
- 독립 검토 전이며 배포 가능 판정 아님.

출처(confidence: High): 로컬 bootstrap.sh/bootstrap.ps1·앱 src/pack.rs의 PACK_ALL 및 cys pack-manifest, cysjavis-pack/bin/javis_bootstrap.py의 .master-bootstrapped 계약.
이식 참고: https://github.com/oogisoogi/jarvis-install/blob/main/bootstrap.sh (MIT, LICENSES/jarvis-install-MIT.txt 보존).

## 필수 역할 및 대기 시간

확인 필수 역할은 master·cso·worker 3석이며 리뷰어는 기다리지 않는다. 각성 후 대기는 실제 경과시간 420초로 제한하고 명령 timeout도 남은 시간 안으로 제한한다. 구 2석 역할 메타데이터를 갱신했다.
