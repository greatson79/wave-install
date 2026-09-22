# S2 릴리스 URL 치환 계약

S2 릴리스 v0.1.0의 `release` 블록 치환을 완료했다. 설치기는 자리표시자가 하나라도 남아 있으면 S03에서 중단하며, 미검증 파일을 설치 완료로 기록하지 않는다.

## 치환된 필드

`steps.json`만 수정한다. `bootstrap.sh`와 `bootstrap.ps1`은 이 블록을 읽으므로 URL·파일명·공개키를 스크립트에 중복 입력하지 않는다.

- `release.version`: `0.1.0` 유지 확인
- `release.repository`: `greatson79/wave-terminal` 유지 확인
- `release.asset_name.macos_arm64`
- `release.asset_name.macos_x64`(x64 릴리스가 없으면 명시적으로 `null`이 아닌 지원 제외 정책을 별도 결재)
- `release.asset_name.windows_x64`
- `release.asset_url.macos_arm64`
- `release.asset_url.macos_x64`
- `release.asset_url.windows_x64`
- `release.sha256.macos_arm64`
- `release.sha256.macos_x64`
- `release.sha256.windows_x64` (`null`: Windows 빌드 준비 중)
- `release.sha256sums_url`
- `release.minisig_url.macos_arm64`
- `release.minisig_url.macos_x64`
- `release.minisig_url.windows_x64` (`null`: Windows 빌드 준비 중)
- `release.minisign_public_key`(공개키만 기록; 비밀키·시드·토큰은 기록하지 않음)

## 치환 검증

S2 릴리스 산출물과 실제 필드를 대조한 뒤, 네트워크 접근 없이 먼저 정적 계약을 실행한다.

```bash
python3 tests/test_contract.py --require-resolved-release
bash -n bootstrap.sh reinstall.sh reset.sh
```

그 다음 S5가 깨끗한 macOS/Windows에서 실제 릴리스 파일을 내려받아 다음을 확인한다.

1. URL이 `https://github.com/greatson79/wave-terminal/releases/download/v0.1.0/...` 형식이고 다른 저장소·브랜치 URL이 아니다.
2. `SHA256SUMS`의 해당 asset 행과 다운로드 파일의 SHA256이 일치한다.
3. `minisign -Vm`이 S2가 제공한 서명과 공개키로 통과한다.
4. `steps.json`의 모든 `__S2_...__` 자리표시자가 사라졌고, `bootstrap.sh`/`.ps1`이 같은 JSON을 읽는다.
5. 위 네 조건 중 하나라도 실패하면 S3 상태는 `S03_DOWNLOAD_VERIFY=failed`이며 S09 완료를 기록하지 않는다.

## 2026-09-22 실측 결과

- macOS arm64·x64 asset URL과 SHA256이 GitHub Release의 `SHA256SUMS`와 각각 일치했다.
- 두 DMG의 asset별 minisign 검증이 공개키 `RWShBLhu6xe+AnzdLhOKUuXyZb6FPjuBSWG0s7SPacy3v9o4Qt8Y9mqI`로 통과했다.
- Windows asset·SHA256·minisig는 `null`이며 Windows 설치기는 준비 중이다.
- 재현 증거: `../wave-install-s5-evidence/S5_TASK1_EVIDENCE_2026-09-22.md`
