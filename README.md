# Wave Install

Wave AI Networks의 Wave Terminal 라이트 설치 GitHub 배포와 설치 가이드입니다.
공개 설치 페이지는 `site/`에 있고, 설치기는 S3 계약에 따라 `steps.json`의 10단계를 실행합니다.

## 구성

- `bootstrap.sh`, `bootstrap.ps1`: macOS·Windows 설치기
- `steps.json`: 릴리스 URL·SHA256·minisign 공개키·10단계 정본
- `site/`: 설치 한 줄, 단계별 안내, 릴리스 무결성 안내
- `wave-pack/`: 초기 master 1석 + 부서 1석 편성 팩

## 출처와 라이선스

Wave Terminal은 원개발자 idoforgod의 [`cys-terminal`](https://github.com/idoforgod/cys-terminal)
(MIT)을 기반으로 한 파생본입니다. 원본 고지와 라이선스는 `wave-pack/LICENSES/`에 기록합니다.

설치 가이드의 흐름과 공개 배포 구성은 [`oogisoogi/jarvis-install`](https://github.com/oogisoogi/jarvis-install)
(MIT)을 참고했습니다. 해당 저장소의 코드를 이 저장소에 복제했다는 뜻은 아닙니다.

## 무결성

설치기는 공개 Wave Terminal Release의 SHA256SUMS와 minisign 서명을 확인합니다.
공개키만 `steps.json`에 기록하며, 비밀키는 `~/.config/waveai/minisign/`에 유지하고 저장소에는 넣지 않습니다.

## 운영체제 안내

macOS 설치 자산은 v0.1.0 릴리스에 연결되어 있습니다. Windows 설치기는 준비 중이며,
Windows 설치 자산이 준비되기 전에는 설치를 진행하지 않습니다.

공식 도메인은 별도 결재 후 연결하며, 그 전까지는 배포된 임시 URL만 검증 대상으로 삼습니다.

## 설치팩 v0.1.3 사용

[전체 설치팩 v0.1.3](https://github.com/greatson79/wave-install/archive/refs/tags/v0.1.3.zip)을
내려받아 압축을 풀고 터미널에서 그 폴더로 이동합니다. `steps.json`, `install-state.json`,
`wave-pack/`이 함께 있어야 하므로 설치기 한 파일만 내려받아 실행할 수는 없습니다.

```bash
curl -fsSL https://raw.githubusercontent.com/greatson79/wave-install/main/bootstrap.sh -o bootstrap.sh && bash bootstrap.sh
```

태그의 동일 판본을 그대로 사용하려면 위 재다운로드 없이 압축파일의 `bash bootstrap.sh`를 실행합니다.
Windows 준비 중: PowerShell 설치기는 제공하지만 Windows 설치 자산과 전체 실행 검증은 아직 없습니다.

Claude Code 최소 버전은 `tooling.claude_code_min_version`의 `2.1.278`입니다.
정식 X.Y.Z 최소값에 대해 [SemVer 2.0.0](https://semver.org/)의 숫자 우선순위로 비교하며,
동일 버전의 사전 릴리스는 정식 버전보다 낮고 빌드 메타데이터는 비교에 쓰지 않습니다.
낮은 버전이면 `claude update`로 업그레이드하라는 안내 후 중단합니다.
`tooling.claude_code_version`은 호환용 키로 유지하고, 미정 placeholder가 남으면 중단합니다.
실측 문자열은 `~/.wave/tooling/claude.version`에 남기며 파일 내용 자체를 비교에 재사용하지 않습니다.

## macOS Gatekeeper 관측과 안내

**두 DMG 모두 Apple 공증 없음 · spctl 거부됨.**
2026-09-22 v0.1.0 자산 검증에서 DMG 파일 자체에 대한 `spctl --assess`는 양쪽 모두
`rejected`, `source=no usable signature`, exit 3이었습니다.
arm64 앱은 리소스 봉인 검증에 실패했고, x64 앱은 미서명입니다.
SHA256·minisign 검증은 배포 파일의 무결성 확인이며 Apple 공증을 대신하지 않습니다.

양쪽 아키텍처에 공통으로 적용하는 수동 안내입니다.

1. 공식 Release에서 받은 DMG의 SHA256SUMS·minisign 검증부터 확인합니다.
2. DMG에서 사용자 폴더로 복사한 앱의 위치를 확인합니다.
3. 앱을 Control-클릭(또는 우클릭)하고 **열기**를 선택합니다.
4. 출처와 무결성을 확인하고 격리속성 해제를 직접 선택한 경우에만, 설치된 해당 앱에 한해
   `xattr -dr com.apple.quarantine "$HOME/.wave/apps/Wave Terminal.app"`을 실행합니다.
   다른 위치에 복사했다면 실제 앱 경로로 바꾸세요.
5. 격리속성 해제는 서명 결함을 고치거나 공증을 추가하지 않습니다. 실행 성공은 확인되지 않았으며,
   계속 차단되면 중단하고 오류를 전달하세요.

GUI 다이얼로그와 위 절차의 실행 성공은 아직 검증하지 않았습니다. DMG 재빌드·재서명·공증은
이번 설치팩 수정에 포함하지 않았습니다. **v0.1.3 독립 설치 검증 대기 / macOS 공증 없음**이며,
전체 설치 완료나 파일럿 준비 완료로 표기하지 않습니다.

## 판본 보존과 검증

기존 설치팩 `v0.1.0`·`v0.1.1`·`v0.1.2` 태그·커밋은 보존하고, 이번 수정은 `v0.1.3`에만 추가합니다.
Wave Terminal DMG의 버전과 다운로드 해시는 유지합니다. wave-pack의 미측정 출력과 해시 목록은 갱신합니다.
로컬 코드 비교는 `git diff v0.1.2..v0.1.3`로 확인할 수 있습니다.

```bash
python3 tests/test_contract.py --require-resolved-release
python3 tests/test_release_mapping.py
python3 tests/test_join.py
PWSH=/path/to/pwsh python3 tests/test_version_gate.py
bash -n bootstrap.sh reinstall.sh reset.sh
```

S01 테스트는 실제 설치기의 함수만 임시 폴더에서 실행합니다. 전체 설치·로그인·데몬·좌석을
기동하지 않으므로 독립 실설치 검증을 대신하지 않습니다.

## v0.1.2 실패 기록·데몬 확인 수정

Bash 설치기는 단계 목록에서 ID가 일치하는 항목의 on_fail.error_id를 찾습니다.
원래 실패의 종료 코드와 오류 ID를 상태 파일에 남기며, S02 실패 원인은 독립 재실행 전까지 미판정입니다.
S04는 cysd를 실행하지 않습니다. DMG 안 원본과 복사본의 바이트 일치, 실행 파일 존재·실행권한,
설치 경로 심링크를 확인합니다. 데몬의 실제 기동은 기존 S05 등록 단계의 책임입니다.
cysd 자체의 --version 동작은 별건이며 이번 설치팩에서 수정하지 않았습니다.
v0.1.2에서는 PowerShell 설치기를 v0.1.1 그대로 유지했습니다. v0.1.3에서는 아래 공통 상태 계약을 양쪽에 적용합니다. Windows는 계속 준비 중입니다.

```bash
python3 tests/test_failure_and_daemon_gate.py
```

위 회귀는 가짜 앱·명령과 임시 HOME만 사용하며 Task 3a 전체 실설치 판정을 대신하지 않습니다.

## v0.1.3 공통 상태 기록 계약

Bash와 PowerShell은 `install-state.json`을 같은 의미로 기록합니다.

- `passed`와 비어 있지 않은 `error_id`를 함께 쓰려 하면 쓰기 전에 거부합니다.
- `required_steps_passed`는 단계 목록 전체를 대조해 계산합니다. 오류 ID, 0이 아닌/미기록 exit,
  합성 시험 표식 `TEST_SYNTHETIC_BYPASS`, 건너뜀, 누락, 좌석 기동·주입 미측정이 있으면 `false`입니다.
- 절차를 마무리할 수 있는 예외는 `complete_with_exceptions`와 `exceptions[]`의 단계 ID·사유로 남깁니다.
  기존 상태에 `passed`와 오류 ID가 공존하면 요약 시 그 단계를 `failed`로 정정하고 오류 ID를 보존합니다.
  실제 명령 실패는 기존대로 중단합니다. 이 상태는 전체 실설치 검증 통과를 뜻하지 않습니다.
- `wave doctor`와 `fleet status`의 주입량은 현재 `null`입니다. S08은 미측정을 0으로 바꾸지 않고
  `injection_measured:false`, `max_injected_bytes:null`로 기록하며 이 이유만으로 설치를 막지 않습니다.
  `bytes_lte`의 20480바이트 기준은 유지하며, 실제 수치가 기준을 넘으면 실패합니다.
- S07의 좌석 수 2는 `roles.json` 정의를 센 값입니다. 실제 두 좌석 기동은 구현·검증하지 않았으며
  `fleet_started:null`로 남깁니다. 실제 주입 측정, S08 폴백 데몬, cysd 자체 변경은 포함하지 않습니다.
- START-HERE와 안내 페이지도 미측정·예외를 표시합니다. Windows 자산·실설치는 계속 준비 중입니다.

```bash
PWSH=/path/to/pwsh python3 tests/test_state_contract.py
```

공통 회귀는 임시 HOME·가짜 외부 명령에서 설치기 함수와 상태 기록을 검사합니다.
PowerShell 테스트는 호스트의 PowerShell 실행체로 수행하며 Windows 운영체제 실설치 판정은 아닙니다.
독립 전체 설치 판정과 자격증명·데몬 등록 실검증은 별도로 남습니다.
