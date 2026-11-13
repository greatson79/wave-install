"""M2: real published S04 failure followed by candidate, same injected profile."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
import urllib.request


def main():
    if os.name != "nt" or os.environ.get("GITHUB_ACTIONS") != "true":
        raise SystemExit("Fresh Windows GitHub runner required")
    repo = Path(__file__).resolve().parents[2]
    evidence = Path(os.environ["RUNNER_TEMP"]) / "m2-recovery"
    evidence.mkdir()
    profile = evidence / "profile"
    profile.mkdir()
    wave = profile / ".wave"
    stubs = profile / "stubs"
    stubs.mkdir()
    release = "https://github.com/greatson79/wave-terminal/releases/download/v0.3.5/"
    metadata = evidence / "published-steps.json"
    urllib.request.urlretrieve(release + "steps.json", metadata)
    minimum = json.loads(metadata.read_text(encoding="utf-8-sig"))["tooling"]["claude_code_min_version"]
    if not all(part.isdigit() for part in minimum.split(".")) or len(minimum.split(".")) != 3:
        raise SystemExit("Invalid published Claude version")
    stub = ['@echo off', 'if "%~1"=="--version" (', 'echo ' + minimum,
            'exit /b 0', ')', 'if "%~1 %~2"=="auth status" exit /b 0',
            'echo M2: Claude auth is STUBBED; other commands unsupported 1>&2', 'exit /b 99']
    (stubs / "claude.cmd").write_bytes(("\r\n".join(stub) + "\r\n").encode("ascii"))
    entry = evidence / "published-entry"
    entry.mkdir()
    published = entry / "bootstrap.ps1"
    urllib.request.urlretrieve(release + "bootstrap.ps1", published)
    env = dict(os.environ, USERPROFILE=str(profile), HOME=str(profile), WAVE_HOME=str(wave),
               WAVE_NO_PROGRESS="1", PATH=str(stubs) + os.pathsep + os.environ["PATH"])
    powershell = str(Path(os.environ["SystemRoot"]) / "System32/WindowsPowerShell/v1.0/powershell.exe")

    def execute(label, source):
        start = time.time()
        timed_out = False
        cleanup_exit = None
        with (evidence / (label + ".log")).open("wb") as log:
            process = subprocess.Popen([powershell, "-NoProfile", "-NonInteractive", "-ExecutionPolicy",
                                        "Bypass", "-File", str(source)], env=env, stdout=log, stderr=subprocess.STDOUT)
            try:
                code = process.wait(timeout=150)
            except subprocess.TimeoutExpired:
                timed_out = True
                try:
                    cleanup = subprocess.run(["taskkill.exe", "/T", "/F", "/PID", str(process.pid)],
                                             stdout=log, stderr=subprocess.STDOUT, check=False, timeout=20)
                    cleanup_exit = cleanup.returncode
                except subprocess.TimeoutExpired:
                    cleanup_exit = "taskkill_timed_out"
                try:
                    code = process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    code = None
        snapshot = {}
        state = wave / "install-state.json"
        if state.exists():
            shutil.copyfile(state, evidence / (label + "-state.json"))
            snapshot = json.loads(state.read_text(encoding="utf-8-sig"))
        install_log = wave / "install.log"
        if install_log.exists():
            shutil.copyfile(install_log, evidence / (label + "-install.log"))
        app_paths = sorted(str(p) for p in profile.rglob("wave-app.exe") if p.is_file())
        return {"exit_code": code, "timed_out": timed_out, "elapsed_seconds": round(time.time()-start, 2),
                "steps": snapshot.get("steps", {}), "canonical_gui_paths": app_paths,
                "parent_termination_confirmed": process.poll() is not None,
                "tree_cleanup_confirmed": not timed_out or cleanup_exit == 0, "cleanup_exit": cleanup_exit}

    result = {"measurement": "M2", "published_tag": "v0.3.5", "candidate_sha": os.environ["GITHUB_SHA"],
              "published_entry_sha256": hashlib.sha256(published.read_bytes()).hexdigest(),
              "same_wave_home": str(wave), "login": "STUBBED auth/status only; no real Claude agent authentication",
              "scope": "One fresh runner; same injected .wave/bin; GUI path count, not registry/running-app adoption"}
    result["published"] = execute("published", published)
    if not (result["published"]["parent_termination_confirmed"] and result["published"]["tree_cleanup_confirmed"]):
        result["measurement_error"] = "Published process termination unconfirmed; candidate not started"
        (evidence / "result.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
        print("M2_RESULT=" + json.dumps(result, ensure_ascii=True))
        return 1
    result["candidate"] = execute("candidate", repo / "bootstrap.ps1")
    published_s04 = result["published"]["steps"].get("S04_INSTALL_LINK", {})
    candidate_s04 = result["candidate"]["steps"].get("S04_INSTALL_LINK", {})
    paths = result["candidate"]["canonical_gui_paths"]
    result["published_s04_failed"] = published_s04.get("status") == "failed"
    result["same_folder_single_canonical_gui"] = len(paths) == 1 and Path(paths[0]).parent == wave / "bin"
    result["candidate_s05_s09"] = {key: value.get("status") for key, value in result["candidate"]["steps"].items()
                                    if key.startswith(tuple("S0" + str(n) + "_" for n in range(5, 10)))}
    expected = ["S05_DAEMON_REGISTER", "S06_PACK_INSTALL", "S07_INITIAL_FLEET", "S08_VERIFY", "S09_COMPLETE"]
    result["all_s05_s09_passed"] = all(result["candidate_s05_s09"].get(key) == "passed" for key in expected)
    result["recovery_verdict"] = "PASS" if (result["published_s04_failed"] and
        candidate_s04.get("status") == "passed" and result["same_folder_single_canonical_gui"] and
        result["all_s05_s09_passed"] and result["candidate"]["exit_code"] == 0 and
        not result["candidate"]["timed_out"]) else "FAIL_OR_UNMEASURED"
    (evidence / "result.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print("M2_RESULT=" + json.dumps(result, ensure_ascii=True))
    # A recorded failure is measurement evidence, not a claim that recovery is safe.
    return 0


if __name__ == "__main__":
    sys.exit(main())
