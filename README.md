# Wave Install

Wave AI Networks의 Wave Terminal 라이트 설치 GitHub 배포와 설치 가이드입니다.
공개 설치 페이지는 `site/`에 있고, 설치기는 S3 계약에 따라 `steps.json`의 10단계를 실행합니다.

## 구성

- `bootstrap.sh`, `bootstrap.ps1`: macOS·Windows 설치기
- `steps.json`: 릴리스 URL·SHA256·macOS CDHash·10단계 정본
- `site/`: 설치 한 줄, 단계별 안내, 릴리스 무결성 안내
- `wave-pack/`: 초기 master·cso·worker 3석 편성 메타데이터

## 출처와 라이선스

Wave Terminal은 원개발자 idoforgod의 [`cys-terminal`](https://github.com/idoforgod/cys-terminal)
(MIT)을 기반으로 한 파생본입니다. 원본 고지와 라이선스는 `wave-pack/LICENSES/`에 기록합니다.

이 설치 도우미는 oogisoogi/jarvis-install(MIT)을 바탕으로 구조·함수 단위로 이식했습니다.
[참고 저장소](https://github.com/oogisoogi/jarvis-install)의 고지는 `LICENSES/jarvis-install-MIT.txt`에 보존합니다.

## 무결성

설치팩 자체는 두 운영체제 모두 고정 SHA256으로 확인합니다. Wave Terminal 앱은 macOS에서 고정 SHA256 + `codesign --verify` + CDHash로, Windows에서 고정 SHA256 + SHA256SUMS 대조 + Authenticode 확인(현재 미서명 — SHA256으로 진행)으로 확인합니다. minisign은 더 이상 필요하지 않습니다.

## 운영체제 안내

현재 최신 공개 설치기 릴리스는 `v0.3.0-rc.4`입니다. Wave Terminal 앱 0.2.0 설치 자산(macOS arm64 DMG · Windows setup.exe)은 이 릴리스에 함께 올라 있으며 그 주소에 연결되어 있습니다. macOS DMG는 CI 빌드 앱(3af28f2)을 ad-hoc 서명으로 다시 봉인한 재패키징이고(공증 없음), 별도 x64 빌드가 없어 `macos_x64` 항목도 같은 arm64 DMG를 가리킵니다.

## 설치

macOS: `curl -fsSL https://waveainetworks.com/mac | bash`

Windows PowerShell: `irm https://waveainetworks.com/win | iex`

자세한 안내는 [waveainetworks.com/get](https://waveainetworks.com/get)을 확인하세요.

### Windows 앱의 SmartScreen 안내

Wave Terminal 설치 파일을 실행할 때 SmartScreen 창이 뜨면 **추가 정보 → 실행**을 누릅니다. 백신이 경고하면 예외 등록 없이 화면을 사진으로 남겨 문의해 주세요.

Claude Code 최소 버전은 `tooling.claude_code_min_version`의 `2.1.278`입니다.
정식 X.Y.Z 최소값에 대해 [SemVer 2.0.0](https://semver.org/)의 숫자 우선순위로 비교하며,
동일 버전의 사전 릴리스는 정식 버전보다 낮고 빌드 메타데이터는 비교에 쓰지 않습니다.
낮은 버전이면 `claude update`를 실행하고 다시 확인하며, 그래도 낮을 때만 중단합니다.
`tooling.claude_code_version`은 호환용 키로 유지하고, 미정 placeholder가 남으면 중단합니다.
실측 문자열은 `~/.wave/tooling/claude.version`에 남기며 파일 내용 자체를 비교에 재사용하지 않습니다.

## macOS Gatekeeper 관측과 안내

**두 DMG 모두 Apple 공증 없음 · spctl 거부됨.**
2026-09-22 v0.1.0 자산 검증에서 DMG 파일 자체에 대한 `spctl --assess`는 양쪽 모두
`rejected`, `source=no usable signature`, exit 3이었습니다.
v0.1.0의 arm64 앱은 리소스 봉인 검증에 실패했고 x64 앱은 미서명이었습니다 — v0.1.1에서 두 앱 모두 ad-hoc 서명을 다시 봉인해 `codesign --verify --deep --strict`를 통과합니다.
SHA256·codesign(Windows는 SHA256·Authenticode) 검증은 배포 파일의 무결성 확인이며 Apple 공증을 대신하지 않습니다.

양쪽 아키텍처에 공통으로 적용하는 수동 안내입니다.

1. 설치기가 DMG의 고정 SHA256·codesign 검증을 통과시킨 것부터 확인합니다.
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

## Windows bootstrap 구조 이식

Windows 설치기는 핀 3값, `[1/10]`~`[10/10]` 출력, 검증 뒤 웹 표식 제거,
12범주 J-코드, fail-open `/api/progress` 보고, 600초 완료 표지와 자동 이어하기를 사용합니다.
Windows 핀은 앱 0.2.0 CI 빌드(87d206b)로 확정했으며, 바이트 수와 SHA256 은 `steps.json` 의 핀이 정본입니다.
공개 릴리스 대조와 실제 러너 결과는 아래 검증 기록에 구분해 남깁니다.
[핀 갱신·재실행·검증 절차](docs/windows-bootstrap.md)와 [진단 코드](docs/help-codes.md)를 참고하세요.

## 재설치·이어받기

`/mac`·`/win` 설치 한 줄은 옵션 없이 기본 실행합니다. 재설치·이어받기 절차는 [자세한 안내](https://waveainetworks.com/get)를 확인하세요.

## 좌석 초기 설정과 reset

CYS 좌석 설정 폴더(`CYS_ACCOUNT_DIR`, 기본 `~/.cys/claude`)의 settings.json에
`autoUpdatesChannel=stable`을 기록합니다. theme는 맥에서 dark로 맞추고, 윈도에서는
키가 없을 때만 dark를 넣습니다. 개인 `~/.claude` 설정은 수정하지 않습니다.

설치팩에 동봉된 `reset.sh --apply --target wave|all` 및 `reset.ps1 -Apply -Target wave|all`은
`.wave`를 삭제하기 전에 `trust-seed.tsv`에 기록된 홈 신뢰와 remoteControlAtStartup 값을
되돌리고 작업폴더 신뢰 칸을 제거합니다. 원복 실패 시 삭제를 중단하고 저널을 남깁니다.
`--list`/`-List`(기본값)와 `--target pack`/`-Target pack`은 이 설정을 바꾸지 않습니다.
온보딩·fullscreen·theme·autoUpdatesChannel은 원작처럼 남습니다. reset은 기본 사용자
`.wave`가 대상이며, 별도 WAVE_HOME 환경값을 원복 경로로 사용하지 않습니다.
