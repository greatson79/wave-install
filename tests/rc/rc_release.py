#!/usr/bin/env python3
"""RC 러너용 시험 릴리스 조립 — 코드 파일은 건드리지 않고 '복사본'에서 앱 핀만 시험 자산으로 치환한다.
  rc_release.py --os mac|win --asset FILE --base https://127.0.0.1:8443/ --out DIR [--cdhash HEX] [--repo ROOT]
산출(--out): 한 줄 설치가 받는 bootstrap.sh/.ps1 · 설치팩 tar.gz/zip · 앱 자산 · SHA256SUMS, 그리고 rc-release.json(한 줄 명령·지문).
설치기는 minisign 을 쓰지 않는다(SHA256 + codesign/CDHash · Authenticode) — 시험 서명키는 필요 없고, 비밀값은 만들지도 기록하지도 않는다."""
import argparse, hashlib, json, os, pathlib, re, shutil, subprocess, sys, tempfile

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
m_ver = re.search(r"(\d+\.\d+\.\d+)", asset.name)  # 앱 산출 이름 'Wave Terminal_0.1.2_aarch64.dmg' 의 버전 — 실제 릴리스 규약 이름으로 바꿔 서빙(바이트 불변)
app_ver = m_ver.group(1) if m_ver else sys.exit("자산 이름에서 버전을 찾지 못함: " + asset.name)
if a.os == "mac":
    name = "wave-terminal-%s-macos-arm64.dmg" % app_ver; rel["macos_version"] = app_ver
    for k in ("macos_arm64", "macos_x64"):
        rel["asset_name"][k] = name; rel["asset_url"][k] = a.base + name; rel["sha256"][k] = sha
        rel["cdhash"][k] = a.cdhash
else:
    name = "wave-terminal-%s-windows-x64-setup.exe" % app_ver; rel["version"] = app_ver  # 설치기는 steps.json release 핀(version·bytes·sha256·asset_name)이 단일 정본
    rel["asset_name"]["windows_x64"] = name; rel["asset_url"]["windows_x64"] = a.base + name; rel["sha256"]["windows_x64"] = sha
    rel["bytes"]["windows_x64"] = asset.stat().st_size
    rel["windows_sha256sums_url"] = a.base + "SHA256SUMS"
steps_p.write_text(json.dumps(steps, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

BASH = r"C:\Program Files\Git\bin\bash.exe" if os.name == "nt" else "bash"  # 윈도우 CreateProcess 는 PATH 보다 System32 를 먼저 봐 WSL 의 bash.exe(배포판 없음)를 집는다 — Git bash 를 명시
mr = subprocess.run([BASH, (stage / "scripts/make-release.sh").as_posix(), ver, a.base, out.as_posix()], capture_output=True, encoding="utf-8", errors="replace")  # 윈도우 기본 cp1252 로는 한글 stderr 를 못 읽는다 · 윈도우 git-bash 는 역슬래시 경로에서 dirname 이 깨진다 → 슬래시 경로
if mr.returncode:
    sys.stderr.write("make-release.sh exit %d\n--- stdout\n%s\n--- stderr\n%s\n" % (mr.returncode, (mr.stdout or "")[-3000:], (mr.stderr or "")[-3000:])); sys.exit(1)
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
