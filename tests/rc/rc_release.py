#!/usr/bin/env python3
"""RC 러너용 시험 릴리스 조립 — 코드 파일은 건드리지 않고 '복사본'에서 앱 핀만 시험 자산으로 치환한다.
  rc_release.py --os mac|win --asset FILE --base https://127.0.0.1:8443/ --out DIR [--cdhash HEX] [--repo ROOT]
산출(--out): 한 줄 설치가 받는 bootstrap.sh/.ps1 · 설치팩 tar.gz/zip · 앱 자산 · SHA256SUMS, 그리고 rc-release.json(한 줄 명령·지문).
설치기는 minisign 을 쓰지 않는다(SHA256 + codesign/CDHash · Authenticode) — 시험 서명키는 필요 없고, 비밀값은 만들지도 기록하지도 않는다."""
import argparse, hashlib, json, pathlib, re, shutil, subprocess, sys, tempfile

ap = argparse.ArgumentParser()
ap.add_argument("--os", choices=["mac", "win"], required=True)
ap.add_argument("--asset", required=True)
ap.add_argument("--base", required=True, help="https:// 로 끝나는 시험 서버 주소(설치기가 https 만 허용)")
ap.add_argument("--out", required=True)
ap.add_argument("--cdhash", default=None, help="mac: 앱의 CDHash(codesign -dvvv). 없으면 null(설치기는 건너뜀)")
ap.add_argument("--repo", default=str(pathlib.Path(__file__).resolve().parents[2]))
a = ap.parse_args()
if not a.base.startswith("https://") or not a.base.endswith("/"):
    sys.exit("--base 는 https://…/ 형식이어야 함")
repo, out, asset = pathlib.Path(a.repo), pathlib.Path(a.out).resolve(), pathlib.Path(a.asset)
out.mkdir(parents=True, exist_ok=True)
sha = hashlib.sha256(asset.read_bytes()).hexdigest()
stage = pathlib.Path(tempfile.mkdtemp(prefix="rc-stage-"))
files = subprocess.run(["git", "-C", str(repo), "ls-files"], capture_output=True, text=True, check=True).stdout.splitlines()
for f in files:
    d = stage / f; d.parent.mkdir(parents=True, exist_ok=True); shutil.copy2(repo / f, d)

steps_p = stage / "steps.json"; steps = json.loads(steps_p.read_text(encoding="utf-8")); rel = steps["release"]
ver = steps["version"]
if a.os == "mac":
    name = asset.name
    for k in ("macos_arm64", "macos_x64"):
        rel["asset_name"][k] = name; rel["asset_url"][k] = a.base + name; rel["sha256"][k] = sha
        rel["cdhash"][k] = a.cdhash
else:
    name = "wave-terminal-%s-windows-x64-setup.exe" % rel["version"]  # ps1 은 이 이름만 인정
    rel["asset_name"]["windows_x64"] = name; rel["asset_url"]["windows_x64"] = a.base + name; rel["sha256"]["windows_x64"] = sha
    rel["windows_sha256sums_url"] = a.base + "SHA256SUMS"
    ps = stage / "bootstrap.ps1"; t = ps.read_text(encoding="utf-8-sig")
    for pat, new in ((r"(\$WaveWinBytes = )\d+", r"\g<1>%d" % asset.stat().st_size), (r"(\$WaveWinSha256 = ')[a-f0-9]{64}(')", r"\g<1>%s\g<2>" % sha)):
        t, n = re.subn(pat, new, t, count=1)
        if n != 1: sys.exit("ps1 핀 줄을 찾지 못함: " + pat)
    ps.write_bytes(b"\xef\xbb\xbf" + t.encode("utf-8"))
steps_p.write_text(json.dumps(steps, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

subprocess.run(["bash", str(stage / "scripts/make-release.sh"), ver, a.base, str(out)], check=True, stdout=subprocess.DEVNULL)
shutil.copy2(asset, out / name)
with open(out / "SHA256SUMS", "a", encoding="utf-8") as f:  # make-release 가 쓴 줄 뒤에 자산 줄 추가(자산 줄은 정확히 1개)
    f.write("%s  %s\n" % (sha, name))

readme = (stage / "README.md").read_text(encoding="utf-8").splitlines()
line = next(l for l in readme if (l.startswith("curl -fsSL https://github.com/greatson79/wave-install/releases/download/") if a.os == "mac" else l.startswith("powershell ") and "install-wave.ps1" in l))
one = re.sub(r"https://github\.com/greatson79/wave-install/releases/download/v[0-9.]+/", a.base, line)
(out / "rc-release.json").write_text(json.dumps({"os": a.os, "installer_version": ver, "asset": name, "asset_sha256": sha, "cdhash": a.cdhash,
                                                 "one_line": one, "readme_line": line}, ensure_ascii=False, indent=1), encoding="utf-8")
shutil.rmtree(stage)
print(one)
