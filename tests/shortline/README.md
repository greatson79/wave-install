# Windows PowerShell 5.1 짧은 한 줄 CI

## 작업 계획과 상태

- [x] `9a841ae`에서 `feat/win-short-line-ci` 별도 가지·worktree 생성.
- [x] 설계 §7의 loopback fixture·PS5.1 runner·워크플로 추가.
- [x] 정상·SHA 변조·bootstrap 404·전송 중단·자식 exit 7 fixture 검산.
- [x] 로컬 서버 종료·포트 닫힘 검사.
- [ ] 펄스가 가지 push 후 Windows CI 실측 PASS 확인.

적용 스킬: `using-git-worktrees`, `verification-before-completion`.
원천: `output/WaveAI/프로젝트/WaveInstall/설계_짧은한줄_설치명령.md` §4·§7.

## 실행과 보장 범위

Windows CI는 `shell: powershell`에서 5.1을 단언하고 `run_ps51.py`를 실행한다.
runner는 Windows의 실제 `System32/WindowsPowerShell/v1.0/powershell.exe`를 실행한다.
명령은 `irm http://127.0.0.1:<임시포트>/win | iex`이며 운영 사용자 명령에서 URL만 바꾼다.
ASCII·BOM 없는 stub은 설계 §4 원문에서 bootstrap URL만 치환한다.
한국어 bootstrap은 UTF-8 BOM 바이트를 그대로 `-OutFile`에 저장한 뒤 실제 `powershell.exe -File`로 실행한다.
한글 리터럴의 코드포인트를 고정 정수 배열과 대조하며 콘솔의 한글 표시 상태로 판정하지 않는다.
SHA 기대값은 고정 리터럴이며 `/corrupt`는 제공 payload만 변조한다.

다섯 경우 모두 파이프 종료값·요청 경로·완료 마커·임시 폴더 정리를 검사한다.
정상 경우는 PS5.1 자식·파일 모드·BOM·한글·SHA·완료 마커가 모두 필요하다.
실패 네 경우는 비정상 종료와 완료 마커 부재가 필요하다.
404·중단에서는 bootstrap 실행 마커와 payload 요청도 없어야 한다.
자식 exit 7은 상위 오류에 7이 포함되어야 한다(상위 PowerShell 자체 종료값이 7이라는 요구는 아니다).

진짜 설치기·팩·로그인·앱은 실행하지 않는다. 자식 HOME/USERPROFILE/TEMP/TMP/APPDATA/LOCALAPPDATA와 cwd는 임시 경로다.
서버는 runner 내부 thread이며 loopback 임시 포트만 연다. `finally`에서 서버 close·thread join·포트 닫힘을 검사한다.
서브프로세스에는 60초 timeout이 있으며 별도 상주 서버 프로세스는 만들지 않는다.

## 로컬 검산 증거 (2026-10-03)

- `python3 -m py_compile tests/shortline/serve_fixture.py tests/shortline/run_ps51.py`: exit 0.
- `cys run -- python3 tests/shortline/test_fixture.py`: 5 tests PASS·exit 0.
  마지막 실행 scoped PID 80187; cys 회수·등록 해제 반환 확인.
  각 테스트 tearDown은 thread 종료·포트 닫힘도 검사한다.
- macOS에서 `python3 tests/shortline/run_ps51.py`: 예상 exit 1,
  `Windows required; pwsh is not a PS5.1 substitute`로 차단됨.

위 결과는 fixture 자체 검산이며 **Windows PS5.1 PASS 증거가 아니다**.
Windows run URL·결과는 펄스 push 이후 별도 기록한다. 운영 HTTPS·실제 설치 인증도 이 fixture CI 범위 밖이다.

CI 원시 관찰과 판정은 `shortline-ps51-results.json` artifact에 남긴다.
실패 시에도 이미 수집한 case별 종료값·명령·출력·서버 요청 이력을 보존한다.

## Windows 첫 실행에서 발견한 결함과 수정

`9736f8f` run `37105649016`은 정상·변조·404를 통과했지만 전송 중단에서 실패했다.
Windows PowerShell `5.1.26100.33438`의 `Invoke-WebRequest -OutFile`은 선언된 Content-Length보다 짧은
8바이트를 저장하고도 오류를 전파하지 않았고, 부분 스크립트가 exit 0을 반환했다.
원시 증거: https://github.com/greatson79/wave-install/actions/runs/37105649016
따라서 exit code만으로 다운로드 완결성을 가정하지 않는다.

`scripts/render_win_start.py`는 최종 BOM bootstrap의 SHA256을 ASCII stub에 고정한다.
stub은 다운로드한 파일의 SHA가 일치한 경우에만 `powershell.exe -File`로 넘긴다.
fixture도 이 renderer를 사용하며, 완전한 원본 SHA를 고정한 다음 HTTP 응답만 자른다.
`BOOTSTRAP_SHA_MISMATCH`를 발생시키고 부분 파일 실행을 막아야 CI가 통과한다.
이 SHA는 bootstrap 전달 무결성을 검사한다. 최초 stub 전달의 신뢰를 대신하지 않는다.

## 실제 릴리스 반영 책임과 순서

- 담당: 릴리스 조립 담당자가 bootstrap을 최종 생성한 직후 renderer를 실행하고,
  펄스가 두 자산의 URL·SHA 결속을 검수한 뒤 함께 발행한다.
- 생성 위치: 기존 `scripts/make-release.sh`가 만든 출력 폴더의 **최종 `bootstrap.ps1` 바이트**.
  소스 bootstrap이나 SHA 자리표시자가 남은 파일로 stub을 생성하지 않는다.
- 명령: `python3 scripts/render_win_start.py --bootstrap <출력폴더>/bootstrap.ps1 --url https://github.com/greatson79/wave-install/releases/download/<승인태그>/bootstrap.ps1 --output <출력폴더>/win-start.ps1`
- 변경 규칙: bootstrap 내용·BOM·줄바꿈 중 하나라도 바뀌면 stub을 다시 생성한다.
  stub의 URL은 승인된 같은 릴리스 태그로 고정한다. latest URL로 bootstrap을 받지 않는다.
- 조립 뒤 두 파일을 SHA256SUMS에 포함하고 동일 릴리스 자산으로 제출한다.
  이 CI 가지는 기존 make-release.sh·발행 워크플로를 바꾸거나 실제 자산을 발행하지 않는다.
  따라서 **발행 조립에 renderer 호출 연결은 릴리스 담당자의 남은 통합 작업**이다.

초기 사용자 명령은 그대로 `irm https://waveainetworks.com/win | iex`다.
CI는 해당 URL만 loopback fixture로 치환한다. 운영 HTTPS·실제 설치·인증 시험은 별도다.
