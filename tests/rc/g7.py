#!/usr/bin/env python3
"""G7 증거: 문구 생성기 --check 종료코드 + 배포 패키지(설치팩 tar.gz) 파일 목록. g7.py --gen GEN.py --tar PACK.tar.gz --out DIR"""
import argparse, hashlib, json, pathlib, subprocess, sys, tarfile
ap = argparse.ArgumentParser(); ap.add_argument("--gen", required=True); ap.add_argument("--tar", required=True); ap.add_argument("--out", required=True)
a = ap.parse_args(); out = pathlib.Path(a.out); out.mkdir(parents=True, exist_ok=True)
r = subprocess.run([sys.executable, a.gen, "--check"], capture_output=True, text=True)
(out / "G7_gen_check.txt").write_text("exit=%d\n%s%s" % (r.returncode, r.stdout, r.stderr), encoding="utf-8")
names = [n.split("/", 1)[1] for n in tarfile.open(a.tar).getnames() if "/" in n]  # 최상위 폴더 이름 제거
(out / "G7_package_files.txt").write_text("\n".join(sorted(names)) + "\n", encoding="utf-8")
lic = [n for n in names if n in ("LICENSE", "LICENSES/jarvis-install-MIT.txt")]
raw = [{"path": f, "sha256": hashlib.sha256((out / f).read_bytes()).hexdigest()} for f in ("G7_gen_check.txt", "G7_package_files.txt")]
(out / "G7_text.json").write_text(json.dumps({"gen_check_exit": r.returncode, "license_files": lic, "raw": raw}), encoding="utf-8")
