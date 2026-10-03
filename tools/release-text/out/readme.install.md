## 설치 (macOS) — 명령 한 줄

```bash
curl -fsSL https://github.com/greatson79/wave-install/releases/download/v0.3.0/bootstrap.sh -o "$HOME/install-wave.sh" && bash "$HOME/install-wave.sh"
```

## 설치 (Windows) — 명령 한 줄

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -Command "irm https://github.com/greatson79/wave-install/releases/download/v0.3.0/bootstrap.ps1 -OutFile ([Environment]::GetFolderPath('UserProfile')+'\install-wave.ps1'); powershell -NoProfile -ExecutionPolicy Bypass -File ([Environment]::GetFolderPath('UserProfile')+'\install-wave.ps1')"
```

## 다시 설치

설치 상태를 백업하고 처음부터 다시 실행합니다. 앱·팩·사용자 파일 전체 삭제는 하지 않습니다.

```bash
curl -fsSL https://github.com/greatson79/wave-install/releases/download/v0.3.0/bootstrap.sh -o "$HOME/install-wave.sh" && bash "$HOME/install-wave.sh" --reinstall
```

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -Command "irm https://github.com/greatson79/wave-install/releases/download/v0.3.0/bootstrap.ps1 -OutFile ([Environment]::GetFolderPath('UserProfile')+'\install-wave.ps1'); powershell -NoProfile -ExecutionPolicy Bypass -File ([Environment]::GetFolderPath('UserProfile')+'\install-wave.ps1') -Reinstall"
```

## 막혔을 때

같은 한 줄을 다시 붙여넣으세요. 이미 끝난 단계는 건너뜁니다. 그래도 멈추면 컴퓨터 종류·화면 사진·오류 코드를 보내 주세요 waveacademy@waveainetworks.com 으로 보내 주세요.

## 출처

Wave Terminal 은 [idoforgod/cys-terminal](https://github.com/idoforgod/cys-terminal)(MIT)을, 설치 도우미는 [oogisoogi/jarvis-install](https://github.com/oogisoogi/jarvis-install)(MIT)을 바탕으로 합니다
