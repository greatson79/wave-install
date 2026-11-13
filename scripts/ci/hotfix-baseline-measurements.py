"""Record published installer behavior on fresh hosted runners; never a release gate."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import platform
import signal
import subprocess
import urllib.request


def download(url, path):
    with urllib.request.urlopen(url, timeout=60) as response:
        body = response.read()
    path.write_bytes(body)
    return {"url": url, "sha256": hashlib.sha256(body).hexdigest(), "bytes": len(body)}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("measurement", choices=("M1", "M3"))
    args = parser.parse_args()
    if os.environ.get("GITHUB_ACTIONS") != "true" or not os.environ.get("RUNNER_TEMP"):
        raise SystemExit("Fresh GitHub runner required")
    windows = args.measurement == "M1"
    if windows != (os.name == "nt") or (not windows and platform.system() != "Darwin"):
        raise SystemExit("Measurement platform mismatch")
    tag = "v0.3.4" if windows else "v0.3.5"
    root = Path(os.environ["RUNNER_TEMP"]) / ("published-" + args.measurement)
    evidence, entry, home, stubs = [root / name for name in ("evidence", "entry", "home", "stubs")]
    for directory in (evidence, entry, home, stubs):
        directory.mkdir(parents=True, exist_ok=True)
    result = {
        "measurement": args.measurement, "measurement_only": True, "release_tag": tag,
        "started_at": datetime.now(timezone.utc).isoformat(),
        "runner": {"system": platform.system(), "machine": platform.machine(), "version": platform.version()},
        "candidate_sha": os.environ.get("GITHUB_SHA"),
        "login": "STUBBED; only version/auth status; actual agent sessions not authenticated",
        "execution": "not_started", "verdict": "UNMEASURED", "assets": {},
    }
    try:
        base = "https://github.com/greatson79/wave-terminal/releases/download/" + tag + "/"
        result["assets"]["steps.json"] = download(base + "steps.json", evidence / "steps.json")
        steps = json.loads((evidence / "steps.json").read_text(encoding="utf-8-sig"))
        minimum = steps["tooling"]["claude_code_min_version"]
        if not isinstance(minimum, str) or not all(x.isdecimal() for x in minimum.split(".")) or len(minimum.split(".")) != 3:
            raise ValueError("Malformed Claude version pin")
        name = "bootstrap.ps1" if windows else "bootstrap.sh"
        result["assets"][name] = download(base + name, entry / name)
        env = dict(os.environ, HOME=str(home), USERPROFILE=str(home), WAVE_HOME=str(home / ".wave"),
                   WAVE_NO_PROGRESS="1", PATH=str(stubs) + os.pathsep + os.environ["PATH"])
        if windows:
            stub = "\r\n".join((
                "@echo off", 'if "%~1"=="--version" (', "  echo " + minimum,
                "  exit /b 0", ")", 'if "%~1 %~2"=="auth status" exit /b 0', "exit /b 99", ""))
            (stubs / "claude.cmd").write_bytes(stub.encode("ascii"))
            command = ["powershell.exe", "-NoProfile", "-NonInteractive", "-File", str(entry / name)]
        else:
            stub = '#!/bin/sh\nif [ "$1" = "--version" ]; then echo ' + minimum + '; exit 0; fi\nif [ "$1 $2" = "auth status" ]; then exit 0; fi\nexit 99\n'
            stub_path = stubs / "claude"
            stub_path.write_text(stub, encoding="ascii")
            stub_path.chmod(0o700)
            command = ["/bin/bash", str(entry / name)]
        with (evidence / "command.log").open("wb") as output:
            process = subprocess.Popen(command, cwd=entry, env=env, stdin=subprocess.DEVNULL,
                                       stdout=output, stderr=subprocess.STDOUT,
                                       start_new_session=not windows)
            try:
                result["exit_code"] = process.wait(timeout=120)
                result["execution"] = "returned"
            except subprocess.TimeoutExpired:
                result["execution"] = "timed_out_120s"
                if windows:
                    try:
                        cleanup = subprocess.run(
                            ["taskkill.exe", "/PID", str(process.pid), "/T", "/F"], check=False,
                            stdout=output, stderr=subprocess.STDOUT, timeout=20)
                        result["cleanup_exit"] = cleanup.returncode
                    except subprocess.TimeoutExpired:
                        result["cleanup_exit"] = None
                        result["cleanup_error"] = "taskkill timed out after 20 seconds"
                else:
                    try:
                        os.killpg(process.pid, signal.SIGKILL)
                        result["cleanup_exit"] = 0
                    except ProcessLookupError:
                        result["cleanup_exit"] = 0
                        result["cleanup_note"] = "process group already exited"
                try:
                    result["exit_code"] = process.wait(timeout=15)
                except subprocess.TimeoutExpired as error:
                    raise RuntimeError("Timed-out installer process survived bounded cleanup") from error
        wave = home / ".wave"
        for filename in ("install.log", "install-state.json"):
            source = wave / filename
            if source.exists():
                (evidence / filename).write_bytes(source.read_bytes())
        state_path = evidence / "install-state.json"
        if state_path.exists():
            state = json.loads(state_path.read_text(encoding="utf-8-sig"))
            result["steps"] = state.get("steps", {})
            result["s04"] = result["steps"].get("S04_INSTALL_LINK", {})
            required = [row["id"] for row in steps["steps"]]
            result["verdict"] = "PASS" if result["execution"] == "returned" and result["exit_code"] == 0 and len(required) == 10 and all(
                result["steps"].get(name, {}).get("status") == "passed" for name in required) else "FAIL"
            result["s04_verdict"] = "PASS" if result["s04"].get("status") == "passed" else "FAIL"
        else:
            result["state_missing"] = True
        if windows:
            # NSIS uses known folders; inspect only explicitly named Wave links, never recurse a real home.
            script = r"""
[Console]::OutputEncoding = [Text.UTF8Encoding]::new()
$ErrorActionPreference = 'Stop'
$shell = New-Object -ComObject WScript.Shell
$candidates = @()
$programFolders = @([Environment]::GetFolderPath('Programs'), (Join-Path $env:USERPROFILE 'AppData\Roaming\Microsoft\Windows\Start Menu\Programs'))
foreach ($folder in $programFolders) {
  if ($folder) {
    $candidates += Join-Path $folder 'Wave Terminal.lnk'
    $candidates += Join-Path $folder 'Wave Terminal\Wave Terminal.lnk'
  }
}
foreach ($folder in @([Environment]::GetFolderPath('Desktop'), (Join-Path $env:USERPROFILE 'Desktop'))) {
  if ($folder) { $candidates += Join-Path $folder 'Wave Terminal.lnk' }
}
$rows = @(foreach ($path in @($candidates | Select-Object -Unique)) {
  if (Test-Path -LiteralPath $path -PathType Leaf) {
    $link = $shell.CreateShortcut($path)
    @{path=$path;target=$link.TargetPath;arguments=$link.Arguments}
  }
})
@{capture_status=$(if ($rows.Count) {'MEASURED'} else {'UNMEASURED'});count=$rows.Count;links=$rows} | ConvertTo-Json -Depth 5
"""
            links = subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script],
                                   env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=20)
            (evidence / "shortcut-targets.json").write_bytes(links.stdout)
            (evidence / "shortcut-errors.log").write_bytes(links.stderr)
            result["shortcut_capture_exit"] = links.returncode
            result["shortcut_capture"] = json.loads(links.stdout.decode("utf-8-sig")) if links.returncode == 0 else {"capture_status": "UNMEASURED"}
    except Exception as error:
        result["measurement_error"] = str(error)
        result["verdict"] = "UNMEASURED"
    finally:
        result["completed_at"] = datetime.now(timezone.utc).isoformat()
        (evidence / "measurement.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
        print(args.measurement + "_RESULT=" + json.dumps(result, separators=(",", ":")))
    # Observed product failure is a measurement; download/setup failure is not success.
    return 1 if result.get("measurement_error") else 0


if __name__ == "__main__":
    raise SystemExit(main())
