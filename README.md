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
