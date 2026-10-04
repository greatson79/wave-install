# RC5 신호 1 Windows 상태 고정본 출처

- 원본 파일은 사건 증거 묶음의 `evidence/rc5-signal1-37188325110/rc-gate-table-37188325110/raw-evidence/rc-evidence-win-gates-37188325110/win/fleet-status/fleet-status.stdout.log`이다.
- 녹취 명령은 `cys status --json`이며, 설치기가 저장한 `fleet-status` 표준 출력이다.
- 원문 SHA-256은 `fac122bf8bc8c5c1bb242e51ad3ae411b4eb0c6aea59496b514f4be9ef75cd0e`, 크기는 2,999 bytes다.
- 고정본 SHA-256은 `05d6ddcda5220a7c1df33330c44a46dff08a4c24bde730451a519ca1d935e54a`, 크기는 2,959 bytes다.
- 원문에서 Windows 사용자 홈 경로가 포함된 8곳만 `C:\Users\<HOME>`으로 바꿨으며, 나머지 바이트는 원문과 같다.
- 상태 출력에는 녹취 자체의 시각이 없다. 인접 run.log는 S07 실패와 증거 저장 시각을 `2026-10-04T08:30:07Z`로 기록한다.
- `G1_state.json`의 `steps.S07_INITIAL_FLEET.started_at`은 `2026-10-04T08:23:06Z`이며, Unix 초 `1791102186`으로 변환된다.
- 상태 원문의 master는 `surface:1`이고 `G4_surface_list.json`의 master 참조도 같다. `created_at`은 master `1791102190.1203527`, cso `1791102238.3658855`, worker `1791102246.8321028`로 S07 시작 시각보다 모두 늦다.
- 녹취 값과 바이트 치환의 신뢰도는 높음이다. 정확한 상태 출력 시각의 신뢰도는 낮음이며, 원문에 시각이 기록되지 않았다.
