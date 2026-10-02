#!/usr/bin/env python3
"""P0 측정 폴더(구판 팩 d7b354d · v0.1.1 DMG)를 증거 규약으로 옮긴다 — 값은 만들지 않고 원본을 복사·해시만 건다.
  adapt_p0.py P0_DIR OUT_ROOT"""
import hashlib, json, pathlib, shutil, sys

p0, out = pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2])
win_art = p0 / "run-37029862538" / "artifact"
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()


def j(p): return json.loads(p.read_text(encoding="utf-8-sig"))


w, m = out / "win", out / "mac"
w.mkdir(parents=True, exist_ok=True); m.mkdir(exist_ok=True); (out / "common").mkdir(exist_ok=True)
# 윈 G2 = preflight --json 원문 그대로 / 맥 G2 = 래퍼 JSON 의 stdout(--fix 전 격리 홈 측정)
shutil.copy(win_art / "preflight-after.stdout", w / "G2_preflight.json")
(m / "G2_preflight.json").write_text(j(p0 / "raw-macos" / "preflight.json")["stdout"], encoding="utf-8")
# 윈 G4 = 개별 단계 exit (선행 실패 뒤에도 진단용으로 직접 실행한 값 — 실제 사슬은 ①에서 exit 2 로 중단)
ex = {e["label"]: e["exit_code"] for f in ("executions.json", "surface-executions.json") for e in j(win_art / f)}
order = ["phase-1-preflight-fix", "phase-2-ping", "phase-3-claim-role", "phase-4-boot", "phase-5-check"]
raws = []
for f in ("executions.json", "surface-executions.json"):
    shutil.copy(win_art / f, w / f)
    raws.append({"path": f, "sha256": sha(w / f)})
(w / "G4_boot.json").write_text(json.dumps({"steps": [{"n": i + 1, "exit": ex[k]} for i, k in enumerate(order)],
                                            "chain_exit": ex["bootstrap-chain"], "raw": raws}, ensure_ascii=False), encoding="utf-8")
print("wrote", out)
