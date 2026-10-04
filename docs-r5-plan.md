# R5 설치 도움 구현 계획

발동 스킬: brainstorming, writing-plans, test-driven-development.
설계 정본: `<작업 폴더>/설계_설치도움_수신_v1_2026-10-03.md` 및 `<작업 폴더>/2026-10-03/P2/설치도움_API계약.md`. 진행 조건: 회귀 실패 0건을 확인한 뒤 R5 진행. 서버 배포·키 등록·외부 전송은 이번 로컬 검증 범위 밖이다.

## 구조

기존 PowerShell progress는 그대로 확장하고 Bash에 동등 경로를 추가한다. Windows에 Python 런타임 의존을 새로 만들지 않는다. OS별 모듈 2개에 같은 계약을 구현하고 동일 fixture로 비교한다. 처방을 받은 뒤 실행하는 경로는 만들지 않는다.

## 작업 순서와 확인

- [x] 기존 Windows stale fixture 수리·전체 unittest 실패0·skip 사유6개 기록.
- [x] 공통 가림 fixture: 이메일, Bearer, sk 키, 로그인 코드/프롬프트, Windows/mac/Linux 홈, USERNAME/whoami, 로그인명, GitHub 토큰. 원문이 전송 JSON에 남으면 실패. 줄바꿈 보존/ESC 제거 확인.
- [x] 첫 고지 출력 뒤에만 progress/help 허용. progress는 3초·8KB; 도움은 20초·4MB, 로그 마지막40줄 및128KB, 환경96KB 이하. 기본 주소는 환경변수로 변경 가능하고 HTTPS만 허용. 응답 리다이렉트로 비밀값이 다른 서버로 흘러가지 않게 차단한다.
- [x] 막힘에서 help 접수 id32hex/token64hex 검증. client_token은 메모리만 유지한다. 503이면 60초 뒤 1회 재시도. 서버 실패는 원래 설치 상태/종료값을 변경하지 않는다.
- [x] GET20초 간격·최대7200초, 404/410 종료. kind=text의 새 seq만 표시, 제어문자 제거. close도 같은 메모리 token 사용, 예외 삼킴. 비대화 실행은 기다리지 않고 종료한다.
- [x] 양OS 같은 입력의 가림·전송본·처방 표시를 대조. transport를 fixture로 대체해 실제 외부 전송없이 HTTP 실패·503 재시도·토큰누출0·명령실행0 확인.
- [ ] 전체 회귀와 독립 검토 후 로컬 커밋·검토자에게 결과 전달.

## 설계와 달라진 점

상위 설계 v1은 창 그림≤3장을 포함하지만 W5 최소판은 그림을 제외한다. 텍스트 경로를 먼저 검증하며 그림 수집은 범위 결정 후 진행한다. 서버가 현재 미구현 Google adapter로503을 반환한다는 서버 담당자의 보고는 실제 운영 도움 완료를 의미하지 않는다.

## 첫 구현 체크포인트

lib/install_help.py와 lib/install-help.ps1은 순수 가림 함수이며 설치기/전송에는 아직 연결하지 않았다. tests/test_help_redaction.py가 같은 입력의 양OS 결과를 비교한다. 독립 검토에서 공백 계정명 일부 노출과 ANSI 색상 삽입 토큰 우회를 재현하여 회귀 사례에 추가했다. ANSI CSI/OSC를 먼저 제거하고, 알려진 전체 계정명을 홈 경로 치환보다 먼저 가린다.

후속은 고지→전송연결→503 재시도/폴링→H1~H4 통합시험 순서다. 현 단계는 R5 전체 완료가 아니다.

## 클라이언트 연결 체크포인트(R5 후속)

- lib/install_help_client.py(mac)·lib/install-help.ps1(Windows) 같은 계약 구현. 고지문 정본 lib/help-notice.txt 하나를 양OS가 읽는다. 그림 수집은 보류(텍스트만).
- bootstrap.sh: 고지 → 단계 start/end/fail 진행 신호 → 필수 단계 실패 시 help(J-UNK-00 — mac은 진단 코드 체계가 없음). bootstrap.ps1: 기존 Send-Progress 앞에 고지 가드·리다이렉트 차단·8KB 상한, trap 에서 Invoke-FinalHelp.
- WAVE_NO_PROGRESS=1 은 고지·진행·도움을 모두 끈다. WAVE_HELP_BASE_URL 로 주소 교체(https만).
- 설치팩(make-release.sh)에 lib 동봉. 실제 서버·실제 Windows 미검증. 남은 일: 독립 검토, one-line-e2e CI 의 실서버 전송 여부 결정.
