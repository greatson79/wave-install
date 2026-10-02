#!/usr/bin/env python3
"""설치 후 러너에서 gate.py 규약(관문표.md) 증거를 만든다 — 값을 지어내지 않고 원본을 복사·해시만 건다.
  collect.py g1 --out DIR [--wave-home ~/.wave]            → DIR/G1_state.json (설치기 상태 파일 원문)
  collect.py g2 --out DIR --python PY --preflight PATH     → DIR/G2_preflight.json (preflight --json 원문, --fix 없음)
  collect.py claude-hash --out DIR/G6 --phase before|after → ~/.claude 트리 해시 (G6_claude_untouched.json 에 합산)
G3·G4 는 측정 방법 확정 대기(펄스 질의 중) — 여기서는 만들지 않는다."""
import argparse, hashlib, json, os, pathlib, shutil, subprocess, sys

ap = argparse.ArgumentParser(); ap.add_argument("cmd", choices=["g1", "g2", "claude-hash"]); ap.add_argument("--out", required=True)
ap.add_argument("--wave-home", default=os.path.expanduser("~/.wave")); ap.add_argument("--python", default=sys.executable)
ap.add_argument("--preflight"); ap.add_argument("--phase", choices=["before", "after"])
a = ap.parse_args(); out = pathlib.Path(a.out); out.mkdir(parents=True, exist_ok=True)

if a.cmd == "g1":
    shutil.copy2(pathlib.Path(a.wave_home) / "install-state.json", out / "G1_state.json")
elif a.cmd == "g2":
    r = subprocess.run([a.python, a.preflight, "--json"], capture_output=True, text=True, timeout=300)
    json.loads(r.stdout)  # 깨진 JSON 이면 여기서 실패 — 증거를 만들지 않는다
    (out / "G2_preflight.json").write_text(r.stdout, encoding="utf-8")
    (out / "G2_preflight.exit").write_text(str(r.returncode))
else:
    root = pathlib.Path(os.path.expanduser("~/.claude")); h = hashlib.sha256(); rows = []
    for p in sorted(root.rglob("*")) if root.exists() else []:
        if p.is_file() and not p.is_symlink():
            rows.append("%s  %s" % (hashlib.sha256(p.read_bytes()).hexdigest(), p.relative_to(root)))
    mf = out / ("claude_tree_%s.txt" % a.phase); mf.write_text("\n".join(rows) + "\n", encoding="utf-8")
    f = out / "G6_claude_untouched.json"; d = json.loads(f.read_text()) if f.exists() else {"raw": []}
    d[a.phase + "_sha256"] = hashlib.sha256(mf.read_bytes()).hexdigest()  # 원본 목록 파일의 해시 = raw 와 동일
    d["raw"] = [r for r in d["raw"] if r["path"] != mf.name] + [{"path": mf.name, "sha256": d[a.phase + "_sha256"]}]
    f.write_text(json.dumps(d))
