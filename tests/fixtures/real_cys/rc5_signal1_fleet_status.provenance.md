# RC5 signal 1 Windows status 녹취 출처

- [읽은 것] 원문: `/Users/kylechoi/Desktop/Ai_works/개발본부/_round/evidence/rc5-signal1-37188325110/rc-gate-table-37188325110/raw-evidence/rc-evidence-win-gates-37188325110/win/fleet-status/fleet-status.stdout.log`
- [읽은 것] 명령: `cys status --json` (원문은 설치기 `fleet-status` 조회 stdout)
- [읽은 것] 원문 SHA-256: `fac122bf8bc8c5c1bb242e51ad3ae411b4eb0c6aea59496b514f4be9ef75cd0e` · 2,999 bytes
- [잰 것] 고정본 SHA-256: `05d6ddcda5220a7c1df33330c44a46dff08a4c24bde730451a519ca1d935e54a` · 2,959 bytes
- [잰 것] 고정본 변경: 실제 `C:\Users\waverc11787` 홈 경로가 든 JSON 문자열 8곳만 `C:\Users\<HOME>`로 치환. 그 외 바이트는 원문과 동일.
- [미확인] status stdout의 개별 캡처 시각은 녹취에 없다. 동봉 run.log는 S07 실패와 증거 저장을 `2026-10-04T08:30:07Z`로 기록한다.
- [읽은 것] `G1_state.json`의 `steps.S07_INITIAL_FLEET.started_at`은 `2026-10-04T08:23:06Z`; Unix 초 `1791102186`으로 변환했다.
- [읽은 것] status 원문 master는 `surface:1`; `G4_surface_list.json`의 기록 master-ref도 `surface:1`이다.
- [읽은 것] status 원문의 `created_at`: master `1791102190.1203527`, cso `1791102238.3658855`, worker `1791102246.8321028`. 세 값 모두 시작 시각 `1791102186`보다 크다.
- 신뢰도: 실물 status 값·바이트 변환 High; 정확한 status 캡처 시각 Low(원문 미기록).
