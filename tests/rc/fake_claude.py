#!/usr/bin/env python3
"""합성 claude(맥·Windows 공용 · LLM·로그인 없음 — 「합성」 표기, 관문 미산입). fake-claude.sh 와 같은 계약.
맥: ~/.local/bin/claude 로 설치 — SIP 보호 바이너리(/bin/bash 등)가 아니라 python 인터프리터 프로세스여야 cysd 가 명령줄(…/claude)을 읽는다(8차: bash 판은 agent_alive 미매칭). 경로의 디렉터리 이름이 claude 여야 cysd 의 agent_alive(명령줄 토큰/경로 세그먼트 매칭)에 잡힌다: <...>\\claude\\fake_claude.py"""
import glob, json, os, subprocess, sys, time

a = sys.argv[1:]
if a[:1] == ["--version"]: print("2.1.300 (Claude Code)"); sys.exit(0)
if a[:1] in (["auth"], ["update"]): sys.exit(0)
home = os.path.expanduser("~"); rc = os.path.join(home, ".wave", "rc"); vf = os.path.join(home, ".wave", "verify"); os.makedirs(rc, exist_ok=True); os.makedirs(vf, exist_ok=True)
role = os.environ.get("CYS_ROLE", "none")
def _tl(msg):  # 20차 대기: 윈 ④ boot 가 느려 S07 420초 안에 못 끝나는지 가리려는 시각 기록(로직 단계별)
    try: open(os.path.join(rc, "timeline_%s.txt" % role), "a", encoding="utf-8").write("%.2f %s\n" % (time.time(), msg))
    except Exception: pass
_tl("logic start pid=%d" % os.getpid())
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
    _tl("hook start")
    r = subprocess.run(cmd, shell=True, input=('{"source":"startup","cwd":%s}\n' % json.dumps(os.getcwd())).encode(), capture_output=True)
    open(os.path.join(rc, "hook_%s.out" % role), "wb").write(r.stdout); open(os.path.join(vf, "hook_%s.out" % role), "wb").write(r.stdout)
    open(os.path.join(rc, "hook_%s.err" % role), "wb").write(r.stderr)
    open(os.path.join(rc, "hook_%s.rc" % role), "w").write(str(r.returncode))
    _tl("hook done rc=%s" % r.returncode)
if role == "master":
    import shutil
    if os.name != "nt":
        # 13차: round/ 의 *_TODO.md 가 어떤 run 은 0개(11차)·4개(12차)·1개(13차: CSO 만)로 달랐다 — 생성·삭제 순서를 0.3초 간격으로 기록한다(부트 시작 전부터 180초)
        _w = ("import os,time,glob,subprocess\n"
              "d=os.path.expanduser('~/.cys/pack/round');pv=os.path.expanduser('~/.cys/pack.prev/round');mk=os.path.expanduser('~/.cys/.gui-onboarded');o=os.path.expanduser('~/.wave/rc/todo_watch.txt');prev=None;t0=time.time()\n"
              "def ls(x): return sorted(os.path.basename(f) for f in glob.glob(x+'/*_TODO.md'))\n"
              "def ip(): return sorted(l.strip()[:140] for l in subprocess.run(\"ps -axo pid,command | grep 'init-pack' | grep -v grep | grep -v 'python'\",shell=True,capture_output=True,text=True).stdout.splitlines())\n"
              "while time.time()-t0<180:\n s=(ls(d),ls(pv),os.path.exists(mk),ip())\n if s!=prev:\n  open(o,'a').write('%.1f round=%s pack.prev/round=%s gui_onboarded=%s init_pack_procs=%s\\n'%((time.time()-t0,)+s));prev=s\n time.sleep(0.3)\n")
        subprocess.Popen([sys.executable, "-c", _w], start_new_session=True)
    diag = "PATH=%s\nuvx=%s\npython3=%s\n" % (os.environ.get("PATH", ""), shutil.which("uvx"), shutil.which("python3"))
    if os.name != "nt":
        link = os.path.join(home, ".wave", "bin", "cysd")
        diag += "cysd_link=%s\n" % (os.readlink(link) if os.path.islink(link) else None)
        diag += subprocess.run("ps -axo pid,command | grep '[c]ysd' | head -5", shell=True, capture_output=True, text=True).stdout
    open(os.path.join(rc, "preflight_path.txt"), "w", encoding="utf-8").write(diag)
    pack = os.environ.get("CYS_PACK_DIR") or os.path.join(home, ".cys", "pack")
    _tl("bootstrap start")
    # rc4: ~/.wave/rc-skip-bootstrap 이 있으면 부트 점검을 건너뛴다(실기 master 가 산문 지침만 읽고 표지를 못 쓴 경우의 합성). rc/ 밖에 둔 이유 = Reset-Fleet 이 rc/ 를 지운다
    r = subprocess.CompletedProcess([], "skipped", b"", b"") if os.path.exists(os.path.join(home, ".wave", "rc-skip-bootstrap")) else subprocess.run([sys.executable, os.path.join(pack, "bin", "javis_bootstrap.py")], capture_output=True)
    _tl("bootstrap done rc=%s" % r.returncode)
    open(os.path.join(rc, "bootstrap.out"), "wb").write(r.stdout); open(os.path.join(rc, "bootstrap.err"), "wb").write(r.stderr)
    open(os.path.join(rc, "bootstrap.rc"), "w").write(str(r.returncode))
    if os.name != "nt":  # 10차: 첫 설치 직후 G2 에서 C10(TODO 파일 4개 부재)이 FAIL — 부트 직후 시점의 실제 목록을 남긴다
        open(os.path.join(rc, "todo_files_after_bootstrap.txt"), "w", encoding="utf-8").write(subprocess.run("ls -la ~/.cys/pack/round/*_TODO.md ~/.cys/pack/round 2>&1 | head -30", shell=True, capture_output=True, text=True).stdout)
        # 11차: ① 이 READY 인데 round/ 에 TODO 가 없다 — 부트 직후 같은 환경(좌석)에서 preflight --json(수정 없음) 결과와 CYS_*/PACK env 를 남겨 G2 수집기와 대조
        _pf = subprocess.run([sys.executable, os.path.join(pack, "bin", "javis_preflight.py"), "--json"], capture_output=True)
        open(os.path.join(rc, "preflight_after_bootstrap.json"), "wb").write(_pf.stdout)
        open(os.path.join(rc, "seat_env_cys.txt"), "w", encoding="utf-8").write("\n".join("%s=%s" % (k, v) for k, v in sorted(os.environ.items()) if k.startswith(("CYS_", "WAVE_", "AITERM"))) + "\n")
if os.name != "nt":
    # 진단(맥): 시작 8초 뒤 전체 프로세스 트리·claude 프로세스, cysd 가 보는 agent_alive 시계열, 100초 뒤 데몬 이벤트 원문 — 모두 좌석과 분리된 백그라운드로
    _ts = os.path.join(rc, "alive_series_%s.txt" % role)
    _py = "import json,sys;[print(s.get('surface_ref'),s.get('role'),'agent=',s.get('agent'),'alive=',s.get('agent_alive')) for s in json.load(sys.stdin)['surfaces'] if s.get('role') in('cso','worker')]"
    subprocess.Popen("sleep 8; ps -axo pid,ppid,ucomm,command > %s; ps -axo pid,ppid,ucomm,command | grep -i '[c]laude' | head -20 > %s; for t in 0 12 25 45 90; do sleep $t; echo \"t+$t $(date +%%T)\" >> %s; cys status --json 2>&1 | %s -c \"%s\" >> %s 2>&1; done" % (os.path.join(rc, "ps_full_%s.txt" % role), os.path.join(rc, "ps_claude_%s.txt" % role), _ts, sys.executable, _py.replace('"', '\\"'), _ts), shell=True, start_new_session=True)
    _ev = os.path.join(rc, "events_%s.txt" % role)
    _code = "import subprocess,sys;\ntry:\n r=subprocess.run(['cys','events','--after-seq','0'],capture_output=True,text=True,timeout=8);o=r.stdout\nexcept subprocess.TimeoutExpired as e:\n o=(e.stdout or b'').decode('utf-8','replace') if isinstance(e.stdout,bytes) else (e.stdout or '')\nL=[l for l in o.splitlines() if any(k in l for k in ('tick_panic','agent.','watchdog.','zombie'))]\nopen(sys.argv[1],'w').write('lines_total=%d\\n'%len(o.splitlines())+'\\n'.join(L[-60:])+'\\n')"
    subprocess.Popen("sleep 100; %s -c \"%s\" %s" % (sys.executable, _code.replace('"', '\\"'), _ev), shell=True, start_new_session=True)
# 맥: ❯ 출력과 대기는 네이티브 런처(claude_launcher.c)가 맡는다 — 처음부터 프로세스 이름이 claude 여야 cysd 가 잡는다(sysinfo 는 이름을 처음 본 순간 한 번만 기록).
if "--logic-only" in a: sys.exit(0)
sys.stdout.write("\n❯ \n"); sys.stdout.flush()  # agents.json ready_marker — launch-agent 가 이 표지를 볼 때까지 대기한다 (윈도우 판)
while True: time.sleep(3600)
