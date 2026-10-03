# 0.3.0

- 설치기 판을 0.3.0으로 올리고 Wave Terminal 앱 0.2.0에 연결합니다(0.2.4는 공개되지 않아 이 판에 합칩니다).
- 첫 실행 부트 검증을 설치된 팩의 preflight READY까지 확장합니다.
- wave-light 프로필을 명시합니다.
- macOS 설치 화면도 Windows와 같은 `[n/10] 단계 제목` 형식으로 진행을 표시합니다.

# 변경 기록

## v0.1.0

- 초기 master 1석 + 부서 1석 역할 매핑을 추가했습니다.
- master·worker·reviewer 지침 골격과 `wave` CLI 래퍼를 포함했습니다.
- `SHA256SUMS`로 팩 파일 무결성을 고정했습니다.

## 0.1.3

- Bash·PowerShell의 주입량 상수 0을 미측정 null로 정정했습니다.
- 좌석 목록은 roles.json 정의이며 실제 기동·주입 실측 결과가 아닙니다.
