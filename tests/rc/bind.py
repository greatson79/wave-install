#!/usr/bin/env python3
"""어느 설치기 판을 쟀는지 결속 — 체크아웃의 설치기 파일이 rc-inputs.json 의 installer_sha 와 바이트 동일한지 증거로 남긴다.
  bind.py --out DIR   (exit 1 이어도 증거는 남긴다. 판정은 사람이 읽는다)"""
import argparse, json, pathlib, subprocess, sys
ap = argparse.ArgumentParser(); ap.add_argument("--out", required=True); a = ap.parse_args()
g = lambda *c: subprocess.run(["git", *c], capture_output=True, text=True)
want = json.load(open("tests/rc/rc-inputs.json"))["installer_sha"]
head = g("rev-parse", "HEAD").stdout.strip()
anc = g("merge-base", "--is-ancestor", want, "HEAD").returncode == 0
diff = g("diff", "--name-only", want, "HEAD", "--", "bootstrap.sh", "bootstrap.ps1", "steps.json", "install-state.json", "reinstall.sh", "reinstall.ps1", "reset.sh", "reset.ps1", "wave-pack", "scripts").stdout.split()
doc = {"installer_sha": want, "checkout_head": head, "installer_sha_is_ancestor": anc, "installer_files_differing": diff, "bound": anc and not diff}
out = pathlib.Path(a.out); out.mkdir(parents=True, exist_ok=True); (out / "installer_binding.json").write_text(json.dumps(doc, indent=1), encoding="utf-8")
print(json.dumps(doc)); sys.exit(0 if doc["bound"] else 1)
