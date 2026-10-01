# 0.2.4

- 첫 실행 부트 검증을 설치된 팩의 preflight READY까지 확장합니다.
- wave-light 프로필을 명시합니다.
- master·worker·reviewer 스텁을 Wave Terminal v0.1.0(`2f45ad9`) 앱 임베드 원문으로 교체하고 원천 지문을 manifest에 기록합니다.

# 변경 기록

## v0.1.0

- 초기 master 1석 + 부서 1석 역할 매핑을 추가했습니다.
- master·worker·reviewer 지침 골격과 `wave` CLI 래퍼를 포함했습니다.
- `SHA256SUMS`로 팩 파일 무결성을 고정했습니다.

## 0.1.3

- Bash·PowerShell의 주입량 상수 0을 미측정 null로 정정했습니다.
- 좌석 목록은 roles.json 정의이며 실제 기동·주입 실측 결과가 아닙니다.
