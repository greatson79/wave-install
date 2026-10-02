#!/usr/bin/env python3
"""설치 후 러너에서 gate.py 규약(관문표.md) 증거를 만든다 — 값을 지어내지 않고 원본을 복사·해시만 건다.
  collect.py g1 --out DIR [--wave-home ~/.wave]            → DIR/G1_state.json (설치기 상태 파일 원문)
  collect.py g2 --out DIR --python PY --preflight PATH     → DIR/G2_preflight.json (preflight --json 원문, --fix 없음)
  collect.py claude-hash --out DIR/G6 --phase before|after → ~/.claude 트리 해시 (G6_claude_untouched.json 에 합산)
  collect.py g3 --out DIR --manifest pack-manifest.json    → G3_inject.json (+ 훅 stdout·매니페스트 원본 복사, 펄스 결정 B: 매니페스트 일치 · 훅 stdout 부분열 포함 · .new 0)
  collect.py g4 --out DIR                                  → G4_boot.json (boot-last.json 의 ①~⑤ exit + cys status 좌석 생존) """
import argparse, hashlib, json, os, pathlib, shutil, subprocess, sys

ap = argparse.ArgumentParser(); ap.add_argument("cmd", choices=["g1", "g2", "g3", "g4", "claude-hash"]); ap.add_argument("--out", required=True)
ap.add_argument("--wave-home", default=os.path.expanduser("~/.wave")); ap.add_argument("--python", default=sys.executable)
ap.add_argument("--preflight"); ap.add_argument("--pack", default=os.path.expanduser("~/.cys/pack")); ap.add_argument("--manifest")
ap.add_argument("--hook-dir", default=os.path.expanduser("~/.wave/rc")); ap.add_argument("--cys", default="cys"); ap.add_argument("--phase", choices=["before", "after"])
a = ap.parse_args(); out = pathlib.Path(a.out); out.mkdir(parents=True, exist_ok=True)


def sha(b): return hashlib.sha256(b).hexdigest()


def raw_entry(out, src, name):
    shutil.copy2(src, out / name); return {"path": name, "sha256": sha((out / name).read_bytes())}


ROLE_FILE = {"master": "MASTER_DIRECTIVE.md", "cso": "CSO_DIRECTIVE.md", "worker": "WORKER_DIRECTIVE.md"}

if a.cmd == "g1":
    shutil.copy2(pathlib.Path(a.wave_home) / "install-state.json", out / "G1_state.json")
elif a.cmd == "g2":
    r = subprocess.run([a.python, a.preflight, "--json"], capture_output=True, text=True, timeout=300)
    json.loads(r.stdout)  # 깨진 JSON 이면 여기서 실패 — 증거를 만들지 않는다
    (out / "G2_preflight.json").write_text(r.stdout, encoding="utf-8")
    (out / "G2_preflight.exit").write_text(str(r.returncode))
elif a.cmd == "g3":
    pack, hd = pathlib.Path(a.pack), pathlib.Path(a.hook_dir)
    files = json.loads(pathlib.Path(a.manifest).read_text(encoding="utf-8"))["files"]
    raws, roles = [raw_entry(out, a.manifest, "pack-manifest.json")], {}
    for role, fn in ROLE_FILE.items():
        f = pack / "directives" / fn; want = files.get("directives/" + fn)
        body = f.read_bytes() if f.is_file() else b""
        o = hd / ("hook_%s.out" % role); out_b = o.read_bytes() if o.is_file() else b""
        if o.is_file(): raws.append(raw_entry(out, o, o.name))
        # injected = 훅 stdout 에서 설치된 지침 본문이 그대로 들어 있는 구간(없으면 stdout 전체 → 해시 불일치)
        seg = body if body and body in out_b else out_b
        roles[role] = {"injected_sha256": sha(seg), "pack_sha256": want, "injected_bytes": len(seg),
                       "pack_bytes": len(body) if body and sha(body) == want else None, "hook_stdout_bytes": len(out_b)}
    new = [str(p) for r in (pack, pathlib.Path(a.wave_home)) if r.exists() for p in r.rglob("*.new")]
    (out / "G3_inject.json").write_text(json.dumps({"roles": roles, "new_file_count": len(new), "new_files": new, "raw": raws}, ensure_ascii=False), encoding="utf-8")
elif a.cmd == "g4":
    bl = pathlib.Path(os.path.expanduser("~/.cys/state/boot-last.json")); data = json.loads(bl.read_text(encoding="utf-8"))
    st = {}
    for x in data["steps"]:  # ①preflight ②ping ③claim-role ④boot ... ⑤check#N(마지막 시도가 최종)
        n = "①②③④⑤".find(x["step"][0]) + 1
        if n: st[n] = x["exit"]
    r = subprocess.run([a.cys, "status", "--json"], capture_output=True, text=True, timeout=60); r.check_returncode()
    (out / "G4_status.json").write_text(r.stdout, encoding="utf-8")
    seats = [{"role": ("worker" if str(s.get("role", "")).startswith("worker") else s.get("role")),
              "alive": s.get("exited") is False and s.get("agent_alive") is True} for s in json.loads(r.stdout)["surfaces"]]
    raws = [raw_entry(out, bl, "boot-last.json"), {"path": "G4_status.json", "sha256": sha((out / "G4_status.json").read_bytes())}]
    (out / "G4_boot.json").write_text(json.dumps({"steps": [{"n": n, "exit": st[n]} for n in sorted(st)], "seats": seats, "raw": raws}), encoding="utf-8")
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
