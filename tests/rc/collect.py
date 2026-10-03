#!/usr/bin/env python3
"""설치 후 러너에서 gate.py 규약(관문표.md) 증거를 만든다 — 값을 지어내지 않고 원본을 복사·해시만 건다.
  collect.py g1 --out DIR [--wave-home ~/.wave]            → DIR/G1_state.json (설치기 상태 파일 원문)
  collect.py g2 --out DIR --python PY --preflight PATH     → DIR/G2_preflight.json (preflight --json 원문, --fix 없음)
  collect.py claude-hash --out DIR/G6 --phase before|after → ~/.claude 트리 해시 (G6_claude_untouched.json 에 합산)
  collect.py g3 --out DIR --manifest pack-manifest.json    → G3_inject.json (+ 훅 stdout·매니페스트 원본 복사, 펄스 결정 B: 매니페스트 일치 · 훅 stdout 부분열 포함 · .new 0)
  collect.py g4 --out DIR                                  → G4_boot.json (boot-last.json 의 ①~⑤ exit + cys status 좌석 생존 + 좌석 설정 폴더 온보딩·폴더 신뢰 키) """
import argparse, hashlib, json, os, pathlib, shutil, subprocess, sys

ap = argparse.ArgumentParser(); ap.add_argument("cmd", choices=["g1", "g2", "g3", "g4", "claude-hash"]); ap.add_argument("--out", required=True)
ap.add_argument("--wave-home", default=os.path.expanduser("~/.wave")); ap.add_argument("--python", default=sys.executable)
ap.add_argument("--preflight"); ap.add_argument("--pack", default=os.path.expanduser("~/.cys/pack")); ap.add_argument("--manifest")
ap.add_argument("--hook-dir", default=os.path.expanduser("~/.wave/verify")); ap.add_argument("--cys", default="cys"); ap.add_argument("--phase", choices=["before", "after"])
a = ap.parse_args(); out = pathlib.Path(a.out); out.mkdir(parents=True, exist_ok=True)


def _hook(t, v, tb):  # 수집 실패는 traceback 폭탄 대신 <명령>_error.txt 로 남기고 정상 종료한다 — 증거 파일이 없으면 판정기가 미측정으로 읽는다
    import traceback
    (out / (a.cmd + "_error.txt")).write_text("".join(traceback.format_exception(t, v, tb)), encoding="utf-8")
    print("[collect] %s 수집 실패(%s: %s) — %s_error.txt 에 원문" % (a.cmd, t.__name__, v, a.cmd))
    os._exit(0)


sys.excepthook = _hook


def sha(b): return hashlib.sha256(b).hexdigest()


def raw_entry(out, src, name):
    shutil.copy2(src, out / name); return {"path": name, "sha256": sha((out / name).read_bytes())}


ROLE_FILE = {"master": "MASTER_DIRECTIVE.md", "cso": "CSO_DIRECTIVE.md", "worker": "WORKER_DIRECTIVE.md"}

if a.cmd == "g1":
    shutil.copy2(pathlib.Path(a.wave_home) / "install-state.json", out / "G1_state.json")
elif a.cmd == "g2":
    # 앱은 좌석(cysd PTY 자식)마다 동봉 runtime 을 PATH 선두에 넣는다(wave-terminal src/lib.rs runtime_bin_dirs). 러너 셸은 그 PATH 를 받지 않으므로 같은 규칙으로 선두 주입하고 원문을 증거에 남긴다.
    home = pathlib.Path(os.path.expanduser("~"))
    if sys.platform == "darwin":
        rt = home / ".wave/apps/Wave Terminal.app/Contents/Resources/runtime"
        dirs = [rt / "python/bin", rt / "git/bin", rt / "uv", rt / "node/bin"]
    else:
        rt = home / ".wave/bin/runtime"
        dirs = [rt / "python", rt / "git/cmd", rt / "git/usr/bin", rt / "node"]
    dirs = [str(d) for d in dirs if d.is_dir()]
    env = dict(os.environ, PATH=os.pathsep.join(dirs + [os.environ.get("PATH", "")]), PYTHONUTF8="1", PYTHONIOENCODING="utf-8")  # 윈 기본 cp1252 에서는 한글 출력이 UnicodeEncodeError → stdout 빈 값(16차 G2 공백 근인 추정)
    (out / "G2_path.txt").write_text("runtime_dirs_prepended=%s\nPATH=%s\nuvx=%s\n" % (dirs, env["PATH"], shutil.which("uvx", path=env["PATH"])), encoding="utf-8")
    if os.name != "nt":
        (out / "G2_todo_files.txt").write_text(subprocess.run("ls -la ~/.cys/pack/round/*_TODO.md ~/.cys/pack/round 2>&1 | head -30; echo '--- pack.prev/round (init-pack 통째 교체에 밀린 곳):'; ls -la ~/.cys/pack.prev/round 2>&1 | head -30; echo '--- onboarding marker / mtimes:'; ls -la ~/.cys/.gui-onboarded 2>&1; cat ~/.cys/.gui-onboarded 2>&1 | head -3; stat -f '%Sm %N' -t '%H:%M:%S' ~/.cys/pack ~/.cys/pack.prev ~/.cys/pack/round ~/.cys/.pack-version 2>&1", shell=True, capture_output=True, text=True).stdout, encoding="utf-8")
    r = subprocess.run([a.python, a.preflight, "--json"], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=300, env=env)
    (out / "G2_preflight.stderr").write_text(r.stderr or "", encoding="utf-8")
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
                       "pack_bytes": len(body) if body and sha(body) == want else None, "hook_stdout_bytes": len(out_b),
                       # 원값 진단(정규화 금지): 설치본 sha 가 manifest 와 다를 때 줄바꿈 변환(LF→CRLF) 여부를 그대로 보인다
                       "installed_sha256": sha(body) if body else None, "installed_bytes": len(body), "installed_crlf": body.count(b"\r\n"),
                       "stdout_contains_installed": bool(body) and body in out_b,
                       "stdout_contains_crlf_variant": bool(body) and body.replace(b"\r\n", b"\n").replace(b"\n", b"\r\n") in out_b}
    new = [str(p) for r in (pack,) if r.exists()  # 활성 pack 만 — ~/.wave/backups 의 백업 .new 는 제외(W12 합의)
            for p in r.rglob("*.new")]
    (out / "G3_inject.json").write_text(json.dumps({"roles": roles, "new_file_count": len(new), "new_files": new, "raw": raws}, ensure_ascii=False), encoding="utf-8")
elif a.cmd == "g4":
    bl = pathlib.Path(os.path.expanduser("~/.cys/state/boot-last.json")); data = json.loads(bl.read_text(encoding="utf-8"))
    st = {}
    for x in data["steps"]:  # ①preflight ②ping ③claim-role ④boot ... ⑤check#N(마지막 시도가 최종)
        step = x["step"]
        n = {"①preflight": 1, "②ping": 2, "③claim-role": 3, "④boot": 4}.get(step)
        if step.startswith("⑤check#"): n = 5
        if n: st[n] = x["exit"]
    r = subprocess.run([a.cys, "status", "--json"], capture_output=True, text=True, timeout=60); r.check_returncode()
    (out / "G4_status.json").write_text(r.stdout, encoding="utf-8")
    seats = [{"role": ("worker" if str(s.get("role", "")).startswith("worker") else s.get("role")),
              "alive": s.get("exited") is False and s.get("agent_alive") is True} for s in json.loads(r.stdout)["surfaces"]]
    raws = [raw_entry(out, bl, "boot-last.json"), {"path": "G4_status.json", "sha256": sha((out / "G4_status.json").read_bytes())}]
    # 부트·첫 출력 문자열 검사 대상(판정기 QUESTION_PATTERNS): javis_bootstrap 출력(합성 master 좌석이 남긴 것) · 훅 stdout
    for src, nm in ((pathlib.Path(a.hook_dir).parent / "rc" / "bootstrap.out", "bootstrap.out"), (pathlib.Path(a.hook_dir).parent / "rc" / "bootstrap.err", "bootstrap.err"),
                    *((pathlib.Path(a.hook_dir) / ("hook_%s.out" % r), "hook_%s.out" % r) for r in ROLE_FILE)):
        if src.is_file(): raws.append(raw_entry(out, src, nm))
    # 첫기동 관문 사전 기록(설치기 S07): 좌석 설정 폴더(CLAUDE_CONFIG_DIR = CYS_ACCOUNT_DIR 또는 ~/.cys/claude)의 .claude.json 에
    #   hasCompletedOnboarding=true · 살아 있는 좌석 cwd 마다 projects.<cwd>.hasTrustDialogAccepted=true(윈은 \ · / 두 꼴) — LLM 없이 키만 본다
    cfg = pathlib.Path(os.environ.get("CYS_ACCOUNT_DIR") or os.path.expanduser("~/.cys/claude")) / ".claude.json"
    try:
        cj = json.loads(cfg.read_text(encoding="utf-8")); cfg_sha = sha(cfg.read_bytes()); cj = cj if isinstance(cj, dict) else {}
    except (OSError, ValueError):
        cj, cfg_sha = {}, None
    proj = cj.get("projects") if isinstance(cj.get("projects"), dict) else {}
    cwds = sorted({str(s.get("cwd")) for s in json.loads(r.stdout)["surfaces"] if s.get("cwd") and s.get("exited") is False
                   and str(s.get("role") or "").startswith(("master", "cso", "worker"))})
    forms = lambda c: dict.fromkeys([c, c.replace("\\", "/")] if os.name == "nt" else [c])
    trusted = lambda k: isinstance(proj.get(k), dict) and proj[k].get("hasTrustDialogAccepted") is True
    #   + 같은 폴더 settings.json remoteControlAtStartup=true(주인님 지시 — 지인 원작은 false · Wave 만 true)
    try:
        sj = json.loads((cfg.parent / "settings.json").read_text(encoding="utf-8")); sj = sj if isinstance(sj, dict) else {}
    except (OSError, ValueError):
        sj = {}
    trust = {"config": str(cfg), "config_sha256": cfg_sha, "hasCompletedOnboarding": cj.get("hasCompletedOnboarding") is True,
             "cwds": {c: {k: trusted(k) for k in forms(c)} for c in cwds},
             "remoteControlAtStartup": sj.get("remoteControlAtStartup") is True}
    (out / "G4_boot.json").write_text(json.dumps({"steps": [{"n": n, "exit": st[n]} for n in sorted(st)], "seats": seats, "raw": raws, "trust": trust}), encoding="utf-8")
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
