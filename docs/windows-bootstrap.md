# Windows bootstrap 이식 기록

`oogisoogi/jarvis-install`의 `install-master/bootstrap.ps1`에서 핀 선언,
Say 단계 출력, 지문 확인 뒤 웹 표식 제거, J-코드, fail-open 진행 보고,
600초 재실행 표지 패턴을 함수 단위로 옮겼습니다. 원본 전체나 원본 설치 대상은 복사하지 않았습니다.
기존 S00~S09 계약과 작업 시작 시 이미 있던 S04 NSIS 설치·PE 검사·Windows 스모크를 통합했습니다.

## Windows 릴리스 핀

`bootstrap.ps1` 상단의 `WaveVersion`, `WaveWinBytes`, `WaveWinSha256`이 판올림 시 수정할 3값입니다.
`WaveWinFile`은 버전에서 파생합니다. s746 수정 검체의 확정값은 다음과 같습니다.

- 버전: `0.1.0`
- 파일: `wave-terminal-0.1.0-windows-x64-setup.exe`
- 바이트: `128814816`
- SHA256: `733a595c1270d62e9ca83e82cda143d8ec223985b857f648939541d20ba12fc3`

`steps.json`과 `site/steps.json`의 Windows 매핑도 기존 공개 `v0.1.0` 경로로 맞췄습니다.
공개 전 draft 대조와 공개 릴리스 대조는 별도로 기록하며, 픽스처 통과를 출하 증거로 쓰지 않습니다.

배포 담당자는 실제 서명된 자산과 SHA256SUMS를 확보한 뒤 다음을 함께 갱신합니다.

1. 핀 3값을 독립 측정한 값으로 교체합니다. 선언은 값 하나만 있는 한 줄을 유지합니다.
2. `steps.json`과 `site/steps.json`의 release 버전·Windows 이름·URL·SHA256·minisig URL을 맞춥니다.
   Mac 릴리스 매핑도 함께 검사합니다. 공개키와 minisign 검증은 유지합니다.
3. `bash tests/win-pin-release.sh`로 해당 공개 릴리스의 실제 파일 바이트·지문·체크섬 정확한 1행을 대조합니다.
4. Windows workflow_dispatch에서 `release_smoke=true`를 선택하고 같은 태그와 독립 SHA256을 넣습니다.
   공개 핀 대조 또는 OS 매트릭스 실패 시 NSIS 스모크로 가지 않습니다.

`--release-dir <폴더>`는 로컬 후보/픽스처 대조 옵션입니다. 폴더에는 `SHA256SUMS`와
`wave-terminal-<버전>-windows-x64-setup.exe`가 있어야 합니다. 없는 파일·중복 선언·중복 체크섬 행·
측정 실패는 모두 실패입니다. 핀 변조 테스트에는 정상 측정 검체 1개와 거부해야 할 변형 12개가 있습니다.

## 사용자 동작과 상태

- 화면은 `[1/10]`부터 `[10/10]`까지입니다. 기존 S00~S09 ID와 WT 오류 ID는 보존하며,
  분류한 J-코드는 `steps.<ID>.observed.j_code`에 추가합니다.
- `Clear-WebMark`는 함수 내부에서 SHA256을 다시 확인한 뒤 그 파일의 `Zone.Identifier`만 제거합니다.
  S04 호출 전에는 S03의 바이트·SHA256·minisign 검증을 거칩니다. 표식이 없으면 그대로 진행하며,
  제거 실패는 로그로 구별합니다. 백신 예외나 시스템 SmartScreen 설정은 변경하지 않습니다.
- 모든 필수 단계가 검증되어 `complete`인 경우에만 `install-done.txt`를 씁니다.
  `complete_with_exceptions`, 주입량·좌석 기동 미측정에는 성공 표지를 만들지 않습니다.
- 표지 수정 시각이 0~600초이고 핀·설정·상태 지문이 같으면 즉시 완료 안내합니다.
  미래 시각·만료·변경·읽기 실패에는 정상 흐름을 수행합니다. `-Reinstall`은 표지를 무시합니다.
- 보통 재실행도 완료 단계를 건너뜁니다. `-Resume`은 호환 인자로 계속 받습니다.
  사전 검사·Claude 버전·인증·최종 검증은 매번 확인하고, 다운로드와 설치 결과는 지문을 재확인합니다.
  건너뛴 S04도 현재 프로세스 PATH를 복구합니다. `skipped`·실패·다른 릴리스 단계는 재시도합니다.
- 백신 알림이 있다면 이름·대상 파일·조치(차단/격리/삭제)를 확인하세요. 창이 갑자기 닫혀도
  같은 설치 명령으로 다시 시작할 수 있습니다. 이전 running 상태는 중단 흔적이며 백신 원인의 확증은 아닙니다.

## 진행 보고와 진단

기본 주소는 `https://waveainetworks.com/api/progress`이며 `WAVE_PROGRESS_URL`로 우리 배포의
HTTPS `/api/progress` 주소를 지정할 수 있습니다. **실제 엔드포인트 수신 성공은 이번 로컬 작업에서 확인하지 않았습니다.**
원본 형식의 `install_id`, `installer_version`, `os`, `step`, `event`, `at`와 선택 `elapsed_s`,
`detail`을 보냅니다. 이벤트는 `start`·`end`·`fail`이며 detail은 J-코드만 허용합니다.
토큰·계정·로그·원문 오류는 전송하지 않습니다. 요청 제한은 3초이며 전송·ID 저장·로그 실패를 모두 삼킵니다.
`-DryRun`과 `WAVE_NO_PROGRESS=1`에서는 보내지 않습니다.

진단 정본은 [help-rules.tsv](../tests/help-rules.tsv)이며 [도움말](help-codes.md)은 자동 생성합니다.
12범주·19세부 코드입니다. 원본 TSV의 18개 외에 원본 설치기에 있던 PS32도 표에 포함했습니다.
사례 열은 우리 코드·회귀 검체를 가리킵니다. 원본의 타인 실기 기록을 우리 관측으로 옮기지 않았습니다.
`python3 tests/help-rules-check.py --write`는 문서를 생성하며 설치기의 내장 규칙과 다르면 여전히 실패합니다.

## 로컬 검증 및 Windows CI

```bash
python3 tests/ps-balance.py bootstrap.ps1 reinstall.ps1 reset.ps1 scripts/windows-smoke.ps1
python3 tests/help-rules-check.py
python3 tests/test_windows_checks.py
bash tests/win-pin-mutate.sh
PWSH=/path/to/pwsh python3 tests/test_windows_bootstrap.py
PWSH=/path/to/pwsh python3 tests/test_windows_install.py
```

PowerShell 괄호 검사는 문자열·주석을 제외하며 실제 파서는 아닙니다. 문자열 보간 안의 식은 검사하지 않습니다.
Windows job은 체크아웃 직후 이 검사를 먼저 하고 PowerShell 5.1/7 네이티브 파싱·함수 검증을 합니다.
Windows·macOS 매트릭스에서 일반 push/PR과 기본 workflow_dispatch는 핀과 무관한 로컬 검체를 검증합니다.
`release_smoke` 기본값은 false입니다. true로 명시한 수동 실행만 공개 릴리스 핀 검증과 실제 서명 NSIS 스모크를 추가합니다.
s746의 draft 릴리스가 나온 것만으로 공개 자산 다운로드가 가능하다고 간주하지 않습니다.
확정 핀과 검증 가능한 자산 경로가 준비될 때까지 릴리스 스모크는 실행하지 않습니다.
Windows 전용 NTFS ADS 검증은 Windows에서만 실행합니다. macOS의 S04 회귀는 NSIS 프로세스를 대역으로 실행합니다.
실제 Windows 작업·V3·GUI/SmartScreen·한글/공백 계정명·실제 로그인과 전체 설치 성공은 별도 검증 대상입니다.

`bootstrap.sh`가 이미 있어 신규 이식하지 않았습니다. 기존 Mac 설치기·공통 상태 회귀를 유지했습니다.
Windows 전용 MOTW·J-코드·600초 표지의 Mac 동등 기능 추가는 이번 티켓 범위에 넣지 않았습니다.

## 2026-09-22 로컬 검증 결과

참조 원본 커밋: `605cdc35c3abb966473a83f414a0514e399d006e` (읽기 전용).

macOS 호스트의 PowerShell 7에서 unittest 39건 중 38건 통과, 실제 Windows NTFS ADS 1건은
플랫폼 조건으로 건너뛰었습니다. 핀 정상 검체·변형 13건, 도움말 3자 정합, PowerShell 괄호·
네이티브 파싱, Bash 문법, 워크플로 YAML, S3/S2/S5 계약 검사도 통과했습니다.
`win-pin-release.sh`는 미확정 `WaveVersion`을 거부하여 종료값 1을 반환했습니다.
Windows CI는 파일로 구성했으며 실행하지 않았습니다. push·배포·실제 로그인·실제 설치는 하지 않았습니다.


## 핀 대기 중 워크플로 정합성 검사

`python3 -m pip install -r tests/requirements-ci.txt`로 YAML 검사 의존성만 준비합니다.
설치기 자체에 추가되는 의존성은 없습니다.

```bash
python3 tests/workflow-check.py
python3 tests/test_workflow_contract.py
```

검사기는 실제 YAML을 읽어 중복 키, Windows/macOS 매트릭스, 플랫폼별 첫 괄호 검사,
PowerShell 5.1/7 파싱, 릴리스 스모크의 명시적 선택과 선행 검증 의존성을 확인합니다.
정상 구성 외에 9개 변형(매트릭스 제거·조기 PowerShell 실행·기본 릴리스 실행·필수 핀 입력·
PR 실설치·선행 검증 제거·실패 무시·쓰기 토큰·무조건 공개 다운로드)을 거부합니다.
`actionlint`는 GitHub Actions 문법·표현식을 별도로 검사하는 용도이며,
이 프로젝트 계약 검사는 actionlint나 실제 러너 실행을 대체하지 않습니다.

후속 로컬 검증(2026-09-22, e741246 이후): actionlint 1.7.7의 워크플로 문법·표현식 검사 통과.
공식 릴리스의 체크섬을 확인한 검사기를 워크트리 안 임시 폴더에서 실행한 뒤 제거했습니다.
shellcheck는 설치되어 있지 않아 actionlint에서 비활성화했으며 Bash 3개 실행 블록은 `bash -n`으로 검사했습니다.
PowerShell 6개 실행 블록은 로컬 PowerShell 7 파서로 검사했습니다.
전체 unittest 42건 중 41건 통과, Windows NTFS ADS 1건은 macOS이므로 건너뛰었습니다.
괄호·도움말·핀 변조 13검체·S3/S2/S5 계약도 통과했습니다.
핀·설치기 본문은 수정하지 않았으며 실제 GitHub 러너 실행, 공개 릴리스 다운로드, push는 하지 않았습니다.
