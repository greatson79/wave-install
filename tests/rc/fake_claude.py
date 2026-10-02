#!/usr/bin/env python3
"""합성 claude(Windows 판 · LLM·로그인 없음 — 「합성」 표기, 관문 미산입). fake-claude.sh 와 같은 계약.
경로의 디렉터리 이름이 claude 여야 cysd 의 agent_alive(명령줄 토큰/경로 세그먼트 매칭)에 잡힌다: <...>\\claude\\fake_claude.py"""
import glob, json, os, subprocess, sys, time

a = sys.argv[1:]
if a[:1] == ["--version"]: print("2.1.300 (Claude Code)"); sys.exit(0)
if a[:1] in (["auth"], ["update"]): sys.exit(0)
home = os.path.expanduser("~"); rc = os.path.join(home, ".wave", "rc"); vf = os.path.join(home, ".wave", "verify"); os.makedirs(rc, exist_ok=True); os.makedirs(vf, exist_ok=True)
role = os.environ.get("CYS_ROLE", "none")
cmd = ""
cands = [os.path.join(os.environ.get("CLAUDE_CONFIG_DIR", os.path.join(home, ".claude")), "settings.json")]
cands += glob.glob(os.path.join(home, ".claude*", "settings.json")) + glob.glob(os.path.join(home, ".cys", "**", "settings.json"), recursive=True)
for p in cands:
    try: d = json.load(open(p, encoding="utf-8-sig"))
    except Exception: continue
    for e in d.get("hooks", {}).get("SessionStart", []):
        for h in e.get("hooks", []):
            if "session-start.sh" in h.get("command", "") and not cmd: cmd = h["command"]
open(os.path.join(rc, "hook_command_%s.txt" % role), "w", encoding="utf-8").write(cmd + "\n")
if cmd and role != "none":
    r = subprocess.run(cmd, shell=True, input=('{"source":"startup","cwd":%s}\n' % json.dumps(os.getcwd())).encode(), capture_output=True)
    open(os.path.join(rc, "hook_%s.out" % role), "wb").write(r.stdout); open(os.path.join(vf, "hook_%s.out" % role), "wb").write(r.stdout)
    open(os.path.join(rc, "hook_%s.err" % role), "wb").write(r.stderr)
    open(os.path.join(rc, "hook_%s.rc" % role), "w").write(str(r.returncode))
if role == "master":
    import shutil
    open(os.path.join(rc, "preflight_path.txt"), "w", encoding="utf-8").write("PATH=%s\nuvx=%s\npython3=%s\n" % (os.environ.get("PATH", ""), shutil.which("uvx"), shutil.which("python3")))
    pack = os.environ.get("CYS_PACK_DIR") or os.path.join(home, ".cys", "pack")
    r = subprocess.run([sys.executable, os.path.join(pack, "bin", "javis_bootstrap.py")], capture_output=True)
    open(os.path.join(rc, "bootstrap.out"), "wb").write(r.stdout); open(os.path.join(rc, "bootstrap.err"), "wb").write(r.stderr)
    open(os.path.join(rc, "bootstrap.rc"), "w").write(str(r.returncode))
sys.stdout.write("\n❯ \n"); sys.stdout.flush()  # agents.json ready_marker — launch-agent 가 이 표지를 볼 때까지 대기한다
while True: time.sleep(3600)
