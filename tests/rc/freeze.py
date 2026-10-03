#!/usr/bin/env python3
"""G7b 증거 — 배포본 schedule.json 동결(테오 1107 · 펄스 1130 정의):
 기준 = 직전 공개 앱 판 소스의 cysjavis-pack/schedule.json git blob(맥 v0.1.1 · 윈 fa4c12b8) / 현재 = 시험 중인 앱 커밋의 같은 경로 blob. 원값(바이트) 비교 — 설치본은 증거만(데몬이 부트마다 써 넣어 변함).
  freeze.py --repo OWNER/REPO --mac-run ID --win-run ID --out DIR   (rc-inputs.json 의 freeze_baseline_ref 사용)"""
import argparse, hashlib, json, pathlib, subprocess, sys
ap = argparse.ArgumentParser(); ap.add_argument("--repo", required=True); ap.add_argument("--mac-run", required=True); ap.add_argument("--win-run", required=True); ap.add_argument("--out", required=True)
a = ap.parse_args(); out = pathlib.Path(a.out)
refs = json.load(open("tests/rc/rc-inputs.json"))["freeze_baseline_ref"]
sha = lambda b: hashlib.sha256(b).hexdigest()
def gh(*args): return subprocess.run(["gh", *args], capture_output=True, check=True).stdout
def blob(ref): return gh("api", "-H", "Accept: application/vnd.github.raw", "repos/%s/contents/cysjavis-pack/schedule.json?ref=%s" % (a.repo, ref))
for osn, run in (("mac", a.mac_run), ("win", a.win_run)):
    head = gh("run", "view", run, "--repo", a.repo, "--json", "headSha", "--jq", ".headSha").decode().strip()
    base, cur = blob(refs[osn]), blob(head)
    d = out / osn / "G5"; d.mkdir(parents=True, exist_ok=True)
    (d / "baseline_schedule.json").write_bytes(base); (d / "current_schedule.json").write_bytes(cur)
    doc = {"baseline_ref": refs[osn], "baseline_sha256": sha(base), "baseline_sha256_lf": sha(base.replace(b"\r\n", b"\n")), "baseline_crlf": base.count(b"\r\n"),
           "current_ref": head, "current_sha256": sha(cur), "current_sha256_lf": sha(cur.replace(b"\r\n", b"\n")), "current_crlf": cur.count(b"\r\n"),
           "source": "git blob cysjavis-pack/schedule.json (raw bytes, no line-ending normalization)",
           "raw": [{"path": "baseline_schedule.json", "sha256": sha(base)}, {"path": "current_schedule.json", "sha256": sha(cur)}]}
    (d / "G7b_schedule_freeze.json").write_text(json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8")
    print(osn, refs[osn], "->", head[:8], "equal" if sha(base) == sha(cur) else "DIFFERENT")
