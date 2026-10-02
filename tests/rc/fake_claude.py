#!/usr/bin/env python3
"""합성 claude(맥·Windows 공용 · LLM·로그인 없음 — 「합성」 표기, 관문 미산입). fake-claude.sh 와 같은 계약.
맥: ~/.local/bin/claude 로 설치 — SIP 보호 바이너리(/bin/bash 등)가 아니라 python 인터프리터 프로세스여야 cysd 가 명령줄(…/claude)을 읽는다(8차: bash 판은 agent_alive 미매칭). 경로의 디렉터리 이름이 claude 여야 cysd 의 agent_alive(명령줄 토큰/경로 세그먼트 매칭)에 잡힌다: <...>\\claude\\fake_claude.py"""
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
    diag = "PATH=%s\nuvx=%s\npython3=%s\n" % (os.environ.get("PATH", ""), shutil.which("uvx"), shutil.which("python3"))
    if os.name != "nt":
        link = os.path.join(home, ".wave", "bin", "cysd")
        diag += "cysd_link=%s\n" % (os.readlink(link) if os.path.islink(link) else None)
        diag += subprocess.run("ps -axo pid,command | grep '[c]ysd' | head -5", shell=True, capture_output=True, text=True).stdout
    open(os.path.join(rc, "preflight_path.txt"), "w", encoding="utf-8").write(diag)
    pack = os.environ.get("CYS_PACK_DIR") or os.path.join(home, ".cys", "pack")
    r = subprocess.run([sys.executable, os.path.join(pack, "bin", "javis_bootstrap.py")], capture_output=True)
    open(os.path.join(rc, "bootstrap.out"), "wb").write(r.stdout); open(os.path.join(rc, "bootstrap.err"), "wb").write(r.stderr)
    open(os.path.join(rc, "bootstrap.rc"), "w").write(str(r.returncode))
    if os.name != "nt":  # 10차: 첫 설치 직후 G2 에서 C10(TODO 파일 4개 부재)이 FAIL — 부트 직후 시점의 실제 목록을 남긴다
        open(os.path.join(rc, "todo_files_after_bootstrap.txt"), "w", encoding="utf-8").write(subprocess.run("ls -la ~/.cys/pack/round/*_TODO.md ~/.cys/pack/round 2>&1 | head -30", shell=True, capture_output=True, text=True).stdout)
sys.stdout.write("\n❯ \n"); sys.stdout.flush()  # agents.json ready_marker — launch-agent 가 이 표지를 볼 때까지 대기한다
if os.name != "nt":
    # 9차 확정(ps_claude_*.txt + sysinfo 0.33.1 소스): cysd 워치독은 refresh_processes() 를 쓰는데 이 호출은 명령줄(cmd)을 갱신하지 않는다
    # → 프로세스 이름(comm)으로만 에이전트를 찾는다. python 스크립트는 comm 이 "Python" 이라 ps 에는 …/claude 가 보여도 agent_alive=False.
    # 해법: 마지막에 파일 이름이 claude 인 네이티브 실행파일(sleep 복사본)로 exec — comm 이 "claude" 가 된다.
    # 해법: 파일 이름이 claude 인 **네이티브** 실행파일로 exec — comm 이 "claude" 가 된다. (복사한 /bin/sleep 은 arm64e 플랫폼 바이너리라 SIGKILL(137),
    # 심링크는 커널이 실제 파일 이름(python3.12)을 comm 으로 써서 안 된다 → 러너에 있는 clang 으로 아주 작은 대기 프로그램을 claude 라는 이름으로 컴파일)
    # 역할마다 따로 컴파일한다: 같은 경로를 덮어쓰면 먼저 뜬 좌석(cso)의 실행파일이 교체되어 cysd 가 그 프로세스의 이름을 못 읽는다(10차: cso 만 agent_alive=False)
    _d = os.path.join(rc, "bin_" + role); os.makedirs(_d, exist_ok=True)
    _bin = os.path.join(_d, "claude"); _src = os.path.join(_d, "claude_idle.c")
    open(_src, "w").write("#include <unistd.h>\nint main(void){for(;;)sleep(3600);}\n")
    if subprocess.run(["cc", "-O0", "-o", _bin, _src], capture_output=True).returncode == 0:
        subprocess.Popen("sleep 8; ps -axo pid,ppid,ucomm,command | grep -i '[c]laude' | head -20 > %s" % os.path.join(rc, "ps_claude_%s.txt" % role), shell=True, start_new_session=True)
        sys.stdout.flush(); os.execv(_bin, [_bin])
while True: time.sleep(3600)
