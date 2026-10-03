#!/usr/bin/env python3
"""판정 입력 폴더에 다른 잡의 증거가 섞이지 않았는지 단정 — check_evidence_mix.py <증거 루트>
①win·winkr·mac 아래에 noboot·nonhome·ctrlc 폴더가 없어야 하고 ②그 아래 모든 증거 문서(raw 목록)의 파일이 실제로 있고 sha256 이 같아야 한다.
③루트 identity.json 이 win/G4_status.json 과 같은 사용자인지도 본다. 같은 win/ 경로로 올린 잡들이 합쳐지면(예: win-gates 의 hook_master.out + win-nonhome 의 G3_inject.json) ②가 깨진다 — 판정기가 「원본 해시 불일치」로 FAIL 하기 전에 원인을 분명히 말한다."""
import hashlib, json, pathlib, sys

def judge(root):
    root, bad = pathlib.Path(root), []
    for os_dir in ("win", "winkr", "mac"):
        base = root / os_dir
        if not base.is_dir(): continue
        for forbidden in ("noboot", "nonhome", "ctrlc"):
            if (base / forbidden).exists(): bad.append("%s/%s 가 판정 입력에 섞임" % (os_dir, forbidden))
        for doc in sorted(base.rglob("*.json")):
            if len(doc.relative_to(base).parts) > 3: continue
            try: d = json.loads(doc.read_text(encoding="utf-8-sig"))
            except ValueError: continue
            if not isinstance(d, dict) or not isinstance(d.get("raw"), list): continue
            for r in d["raw"]:
                try: p, want = doc.parent / r["path"], r["sha256"]
                except (KeyError, TypeError): continue
                if not p.is_file(): bad.append("%s: 원본 없음 %s" % (doc.relative_to(root), r["path"]))
                elif hashlib.sha256(p.read_bytes()).hexdigest() != want: bad.append("%s: %s 해시 불일치 — 다른 잡 증거가 섞였을 수 있음" % (doc.relative_to(root), r["path"]))
    # ③루트 identity.json(win-gates 잡의 일반 사용자)이 win/G4_status.json 의 master 좌석 cwd(홈)와 같은 사용자여야 한다 — 다른 잡 것이면 섞임
    ident, status = root / "identity.json", root / "win" / "G4_status.json"
    if ident.is_file() and status.is_file():
        try:
            profile = json.loads(ident.read_text(encoding="utf-8-sig"))["profile"]
            cwds = {s.get("cwd") for s in json.loads(status.read_text(encoding="utf-8-sig"))["surfaces"] if s.get("role") == "master"}
            norm = lambda x: str(x).rstrip("\\/").replace("\\", "/").casefold()
            if cwds and norm(profile) not in {norm(c) for c in cwds}: bad.append("identity.json 사용자(%s) ≠ win/G4_status.json master cwd(%s) — 다른 잡 증거가 섞임" % (profile, ", ".join(sorted(map(str, cwds)))))
        except (ValueError, KeyError, TypeError): pass
    return (1, "; ".join(bad)) if bad else (0, "섞임 없음")

if __name__ == "__main__":
    rc, msg = judge(sys.argv[1]); print("[evidence-mix] %s (rc=%d)" % (msg, rc)); sys.exit(rc)
