# Wave Install S3 스테이징

이 디렉터리는 `greatson79/wave-install`에 조인된 S3 설치기 핵심본이다. S5에서 S2 릴리스 실값을 반영했고, 공개 저장소 push·Vercel 임시 배포·독립 실설치 검증은 별도 단계로 관리한다.

## 계약

- 설계 정본: `개발본부/_round/설계_WaveTerminal_라이트_설치팩_v1_2026-09-21.md`
- S0 통과 정본: `개발본부/_round/inbox_펄스/2215_벤_전달_테오사과_S0통과_S2S3S4개시_2026-09-21.md`
- 단계 ID: `S00_PREFLIGHT`부터 `S09_COMPLETE`까지 정확히 10개
- 상태 원장: 사용자 폴더의 `~/.wave/install-state.json`
- 로그: 사용자 폴더의 `~/.wave/install.log` 1개
- 관리자 권한: 사용하지 않음. 설치 대상은 `~/.wave`, `~/.cys/pack` 및 Windows 사용자 프로필 아래로 제한
- 선택 엔진: Codex·Antigravity 기본 off
- S03: SHA256과 minisign을 모두 통과해야 다음 단계로 이동
- S09: 필수 단계의 실측 결과가 없으면 완료 상태를 기록하지 않음

## 파일

- `bootstrap.sh`, `bootstrap.ps1`: 10단계 오케스트레이션
- `steps.json`: 설치기와 `/get` 페이지가 함께 소비할 v1 계약
- `reinstall.sh`, `reinstall.ps1`: 상태 백업 후 사용자 폴더 설치만 재수행
- `reset.sh`, `reset.ps1`: `--list`/`-List` 기본 안전 조회와 명시적 적용 모드
- `install-state.json`: 초기 상태 템플릿
- `tests/test_contract.py`: 네트워크·설치 실행 없는 계약 검사
- `S2_RELEASE_SUBSTITUTION.md`: S2 릴리스 뒤 치환 필드·검증 절차

## 로컬 검증 범위

S3에서는 계약 JSON 파싱, 단계 ID·스키마·자리표시자, 셸 문법과 금지 범위를 검증한다. S2 URL 치환 뒤에는 실제 릴리스의 SHA256·minisign 대조를 별도 증거로 남긴다. 로그인·데몬 등록·fleet 기동은 독립 검증 워커가 수행한다.
