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

`steps.json`의 Windows 매핑은 공개 `v0.1.0` 경로를 유지합니다. Draft `v0.1.0-windows-draft-20260922`는 공개 설치 링크가 아니며 자산 지문 조사 기준입니다.
공개 전 draft 대조와 공개 릴리스 대조는 별도로 기록하며, 픽스처 통과를 출하 증거로 쓰지 않습니다.

배포 담당자는 실제 게시 자산과 SHA256SUMS를 확보한 뒤 다음을 함께 갱신합니다.

1. 핀 3값을 독립 측정한 값으로 교체합니다. 선언은 값 하나만 있는 한 줄을 유지합니다.
2. `steps.json`의 Windows 이름·URL·SHA256·windows_sha256sums_url·windows_publisher_subject를 맞춥니다.
   Mac 릴리스 매핑도 함께 검사합니다. Windows 실행 경로는 minisign을 사용하지 않습니다.
3. `bash tests/win-pin-release.sh`로 해당 공개 릴리스의 실제 파일 바이트·지문·체크섬 정확한 1행을 대조합니다.
4. Windows workflow_dispatch에서 `release_smoke=true`를 선택하고 같은 태그와 독립 SHA256을 넣습니다.
   공개 핀 대조 또는 OS 매트릭스 실패 시 NSIS 스모크로 가지 않습니다.

`--release-dir <폴더>`는 로컬 후보/픽스처 대조 옵션입니다. 폴더에는 `SHA256SUMS`와
`wave-terminal-<버전>-windows-x64-setup.exe`가 있어야 합니다. 없는 파일·중복 선언·중복 체크섬 행·
측정 실패는 모두 실패입니다. 핀 변조 테스트에는 정상 측정 검체 1개와 거부해야 할 변형 12개가 있습니다.


## v0.2 한 줄 설치 흐름

배포 시 `scripts/make-release.sh`가 `bootstrap.ps1`의 `__WAVE_INSTALL_ZIP_URL__`과 `__WAVE_INSTALL_ZIP_SHA256__`을 ZIP URL·측정 SHA256으로 채웁니다. 원본 자리표시자 상태는 실행을 거부합니다. 릴리스 게시 뒤 사용자 명령은 아래 한 줄입니다. 현재 URL은 게시 전이므로 실행 명령이 아니라 확정 문자열입니다.

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -Command "irm https://github.com/greatson79/wave-install/releases/download/v0.2.4/bootstrap.ps1 -OutFile ([Environment]::GetFolderPath('UserProfile')+'\install-wave.ps1'); powershell -NoProfile -ExecutionPolicy Bypass -File ([Environment]::GetFolderPath('UserProfile')+'\install-wave.ps1')"
```

이 한 줄은 설치기를 사용자 폴더에 `install-wave.ps1` 파일로 내려받아 `-File` 로 실행합니다(`irm | iex` 는 쓰지 않습니다 — 릴리스 파일의 UTF-8 BOM 이 문자열로 섞여 Windows PowerShell 5.1 파서가 깨짐 · 2026-10-01 실기 실측). 이 단계에는 SmartScreen 창이 없습니다. ZIP 검증 뒤 설치기가 다시 시작되고, Claude Code 설치·업데이트가 필요하면 이 창에서 실행합니다. 미로그인 상태면 브라우저 인증과 코드 붙여넣기를 요청합니다. Wave Terminal `setup.exe` 실행 시 SmartScreen 경고가 나타날 수 있으며, Defender·V3·알약이 다운로드나 실행을 차단하면 해당 백신의 알림·격리 기록을 확인합니다. 메모리에서 실행된 스크립트는 HTTPS ZIP을 받아 고정 SHA256을 검사하고, ZIP 안의 절대·상위 경로와 symlink를 거부한 뒤 `powershell.exe -ExecutionPolicy Bypass -File`로 검증된 팩의 설치기를 다시 실행합니다.

S01은 Claude Code가 없으면 공식 `https://claude.ai/install.ps1`을 받아 설치하고, 버전이 낮으면 `claude update` 뒤 버전을 재확인합니다. S02는 인증되지 않았을 때 같은 창에서 `claude auth login`을 실행하고 상태를 다시 확인합니다.

S03은 고정 바이트·SHA256·체크섬 행 대조 뒤 `Get-AuthenticodeSignature`를 실행합니다. 서명이 있으면 `Valid`와 설정된 발급자 Subject의 정확한 일치를 요구합니다. 미서명은 SHA256 검증 후 SmartScreen 안내를 출력합니다. Defender·V3·알약 차단 문구는 백신 알림의 파일명·격리 조치를 확인하도록 안내하며 자동 예외 등록은 하지 않습니다.

2026-10-01 Draft 검체는 128814816바이트, SHA256 `733a595c1270d62e9ca83e82cda143d8ec223985b857f648939541d20ba12fc3`이고 PE 보안 디렉터리의 인증서 테이블 offset/size가 둘 다 0이라 Authenticode 서명 부재 후보입니다. 실제 Windows의 `Get-AuthenticodeSignature`와 SmartScreen·백신 동작은 아직 검증하지 않았습니다.

## 사용자 동작과 상태

- 화면은 `[1/10]`부터 `[10/10]`까지입니다. 기존 S00~S09 ID와 WT 오류 ID는 보존하며,
  분류한 J-코드는 `steps.<ID>.observed.j_code`에 추가합니다.
- `Clear-WebMark`는 함수 내부에서 SHA256을 다시 확인한 뒤 그 파일의 `Zone.Identifier`만 제거합니다.
  S04 호출 전에는 S03의 바이트·SHA256·Authenticode 상태 검사를 거칩니다. 표식이 없으면 그대로 진행하며,
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
12범주·20세부 코드입니다. 한국어·영문 접근 거부는 J-PERM-02로 분류합니다.
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

## v0.2.4 비관리자 설치

- S05는 `HKCU\Software\Microsoft\Windows\CurrentVersion\Run`의 `WaveTerminal-cysd` 값을 등록하고 다시 읽어 확인합니다. 경로는 따옴표로 감싸며, 실패 원문을 로그와 상태에 남깁니다. Run 값의 260자 제한은 [Microsoft 문서](https://learn.microsoft.com/windows/win32/setupapi/run-and-runonce-registry-keys)를 따릅니다.
- `optional: true`인 단계가 실패하면 `skipped_with_reason`으로 기록하고 다음 단계로 진행합니다. 필수 단계 실패는 중단합니다. 예외가 있으면 최종 상태는 `complete_with_exceptions`이며 전체 검증 통과를 뜻하지 않습니다.
- 진행 표기는 S00=[1/10], S05=[6/10], S09=[10/10]입니다.
- S08과 doctor는 cys의 정상 자동기동 안내(stderr)를 PowerShell 5.1 예외로 오인하지 않도록 해당 호출만 Continue로 감쌉니다. 결과는 종료 코드로 판정하며 출력은 파일에 남깁니다.
- S06은 사용자 프로필의 pack 경로, S07은 같은 프로필의 역할 정의, S08은 사용자 설치 cys, S09는 사용자 폴더의 안내·상태 파일을 사용합니다. S07의 실제 좌석 기동과 S08의 주입량은 기존 계약대로 미측정 예외입니다.

### 비관리자 CI의 판정 범위

`one-line-e2e.yml`은 새 표준 사용자를 만들고 Windows PowerShell 5.1을 그 계정과 프로필로 실행합니다. Administrators 그룹 부재와 실제 사용자 SID의 HKCU를 검사합니다.

1. `published`: README의 Windows 한 줄을 그대로 실행합니다. S00/S01 통과와 S02 로그인 경계까지만 판정하며 전체 설치 성공으로 표시하지 않습니다. v0.2.4 공개 자산이 없으면 이 잡은 실패합니다. 발행 후 다시 실행해야 합니다.
2. `post-login`: S00~S02에 `TEST_SYNTHETIC_BYPASS` 전제를 명시하고 checkout의 원본 S03~S09를 실행합니다. 실제 S02 로그인 성공을 주장하지 않으며 최종 전체 성공 상태를 거부합니다. 과거 S05의 schtasks 명령이 실제로 접근 거부되는지도 기록합니다. 대조군 미재현은 경고이며 본 설치를 중단하지 않습니다.

`Start-Process -Wait`는 자식 데몬까지 기다릴 수 있으므로 `-Credential -LoadUserProfile -PassThru`와 25분 제한 `WaitForExit`를 사용합니다. 종료 뒤 해당 CI 사용자 프로세스를 정리합니다. 신원·상태·로그·대조군·소스 해시를 artifact로 보존합니다. Windows 실측 결과는 CI 실행 후에만 확정할 수 있습니다.

S05 결과 파일은 `.wave/install/daemon-register-result`에 둡니다. 데몬 런타임의 `.wave/daemon` 경로와 분리하며 기존 런타임 파일을 덮어쓰지 않습니다. 단계 실패와 최상위 실패 로그에는 `InvocationInfo.PositionMessage`로 파일·행 위치를 함께 남깁니다. Bash S07은 좌석 수 검증에 실패하면 필수 단계 실패를 반환합니다.

비관리자 CI 36869712495에서 S03~S06 통과 뒤 S07의 `wave.ps1 --roles-file` 인자 바인딩 실패가 관측되었습니다. 래퍼에 해당 별칭을 등록하고 원본 Run-S07과 실제 래퍼를 함께 실행하는 Windows 회귀를 추가했습니다.

5e60bd7의 PS5.1 회귀에서 S07 인자 문제가 재현되어, 설치기 내부 호출은 명시적인 PowerShell 매개변수 `-RolesPath`로 전달합니다. 자식 stderr 전체와 종료 코드를 함께 기록합니다. 선택 단계는 최초 running 상태 기록도 try 범위에 포함하므로 그때의 예외도 skipped_with_reason 처리 대상입니다. 상태 파일 자체를 계속 쓸 수 없는 경우는 기록 성공으로 주장하지 않습니다.

2225 경로 가설 검증은 두 증거로 나눕니다. `daemon-natural-old-call.json`은 S04 뒤 실제 `.wave/daemon`에 구 `New-Item` 호출을 실행한 결과입니다. 접근 거부가 없으면 `not_reproduced`로 기록합니다. `daemon-locked-file-control.json`은 별도 임시 경로에서 독점 잠금한 daemon 파일에 구 호출이 접근 거부되고, 잠금을 유지한 채 ENV=0의 새 S05가 설치기 기록 파일을 만드는지 대조합니다. 후자는 `synthetic: true`로 표시하며 실PC 원인 확정을 대신하지 않습니다.

대조군은 보고 전용입니다(펄스 보강 지시). 자연 경로·합성 잠금·schtasks 대조의 실패와 증거 수집 오류는 Write-Warning으로 남기고 실제 S05~S09를 계속 실행합니다. 실제 설치 단계와 복사 무결성의 판정은 그대로 적용합니다.

S08의 identify와 doctor 외부 호출은 각각 30초로 제한합니다. doctor 내부 identify는 20초로 제한합니다. 시간 초과 시 해당 클라이언트 프로세스 종료를 시도하고 출력·종료 오류를 남기며 S08을 `unmeasured`로 기록해 S09로 진행합니다. `reason=timeout`, 호출명·제한시간이 상태에 남고 최종 상태는 `complete_with_exceptions`입니다. 호출 비정상 종료·기동 실패·doctor 결과 형식 오류도 `unmeasured`, `reason=call_failed`와 오류·실제 종료값을 남겨 계속합니다. 정상 응답에서 실제로 측정한 주입량이 한도를 넘으면 기존 테스트 계약대로 중단합니다. CI는 시간 초과 미측정을 성공 검증으로 표시하지 않고 S09 도달 여부를 검사합니다.

## v0.2.4 첫 실행 preflight 검증

비관리자 `post-login` CI는 설치된 앱의 Python과 `cys init-pack`을 사용합니다. 제품 bootstrap의 첫 단계인 `preflight --fix`를 실행한 뒤, 같은 설치 팩의 `javis_preflight.py --json` 종료값 0·`ok=true`·`fails=0`·팩 경로 일치를 별도로 요구합니다. 자동 수정이 실패해도 report JSON은 수집합니다. S00~S02의 합성 전제는 계속 표시되며 이 결과가 실제 로그인이나 마스터 전체 부트 완료를 증명하지 않습니다.

구 스텁 디렉티브 대조는 별도 팩 사본에서 실행하고 비차단 증거로 남깁니다. 라이트 검사·Windows 심링크 대체·C53 수리는 Wave Terminal 엔진에도 반영되어야 합니다. 기존 v0.1.0 앱의 init-pack은 수정한 시스템 파일을 옛 임베드 팩으로 복원할 수 있으므로 설치 ZIP만 교체해서 수리가 끝났다고 판정하지 않습니다.

### 디렉티브 정본과 라이트 프로필 공급

설치팩의 master·worker·reviewer 라이트 디렉티브는 Wave Terminal 커밋 `20ade1f5512bdb75074c8054800afacbf081f0e8`의 `cysjavis-pack/directives/` 원문과 바이트 단위로 같습니다. 각각 8,021·4,699·2,675바이트이며 `wave-pack/manifest.json`의 `directive_source`에 출처·SHA256을 기록합니다. 첫 실행 CI는 init-pack 후 설치된 파일의 크기·지문과 `.new` 부재도 확인합니다.

기존 앱은 preflight의 `--skip` 명령행 인자만 받으며 설치 후 프로필 설정이나 스킵 목록 파일을 읽지 않습니다. bootstrap은 `preflight --fix`로 고정 호출합니다. 따라서 설정 파일만 추가해서 라이트 검사·C53·Windows 링크 수리를 적용할 수 없고, 수정된 팩을 임베드한 앱을 다시 빌드해야 합니다.
