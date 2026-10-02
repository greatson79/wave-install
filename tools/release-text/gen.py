#!/usr/bin/env python3
"""릴리스 문구 생성기 — manifest.json 한 장에서 README·/get·설치기 화면 조각을 만든다 (표준 라이브러리만).
  gen.py            out/ 에 조각 3개를 쓴다
  gen.py --check    out/ 이 manifest 와 같은지 + 세 조각의 정본 문자열이 바이트 일치하는지 (exit 0/1)
  gen.py --against ROOT   ROOT(wave-install 작업 트리)의 현행 README·site·steps.json 이 정본과 얼마나 다른지 표로 (exit 0/1)
"""
import html, json, pathlib, re, sys

HERE = pathlib.Path(__file__).resolve().parent
OUT = HERE / "out"
FILES = {"readme": "readme.install.md", "get": "get.install.html", "screen": "screen.txt"}


def canon(m):
    """정본 문자열 — 세 곳이 모두 이 값을 그대로 담는다."""
    base = "https://github.com/%s/releases/download/%s" % (m["installer"]["repo"], m["installer"]["tag"])
    h = m["help"]
    return {
        "tag": m["installer"]["tag"],
        "mac": 'curl -fsSL %s/bootstrap.sh -o "$HOME/install-wave.sh" && bash "$HOME/install-wave.sh"' % base,
        "win": ("powershell -NoProfile -ExecutionPolicy Bypass -Command \"irm %s/bootstrap.ps1 -OutFile "
                "([Environment]::GetFolderPath('UserProfile')+'\\install-wave.ps1'); powershell -NoProfile "
                "-ExecutionPolicy Bypass -File ([Environment]::GetFolderPath('UserProfile')+'\\install-wave.ps1')\"") % base,
        "origin": "Wave Terminal 은 {a}(MIT)을, 설치 도우미는 {b}(MIT)을 바탕으로 합니다".format(
            a=m["origin"][0]["name"], b=m["origin"][1]["name"]),
        "origin_urls": [o["url"] for o in m["origin"]],
        "help": "%s %s %s 으로 보내 주세요." % (h["retry"], h["contact"].rstrip("."), h["email"]),
    }


def render(m):
    c = canon(m)
    a, b = m["origin"]
    readme = (
        "## 설치 (macOS) — 명령 한 줄\n\n```bash\n%s\n```\n\n"
        "## 설치 (Windows) — 명령 한 줄\n\n```powershell\n%s\n```\n\n"
        "## 막혔을 때\n\n%s\n\n"
        "## 출처\n\nWave Terminal 은 [%s](%s)(MIT)을, 설치 도우미는 [%s](%s)(MIT)을 바탕으로 합니다\n"
    ) % (c["mac"], c["win"], c["help"], a["name"], a["url"], b["name"], b["url"])
    e = html.escape
    get = (
        '<code id="install-command-mac">%s</code>\n<code id="install-command-windows">%s</code>\n'
        '<p class="help-line">%s</p>\n'
        '<p class="origin-line">Wave Terminal 은 <a href="%s" target="_blank" rel="noreferrer">%s</a>(MIT)을, '
        '설치 도우미는 <a href="%s" target="_blank" rel="noreferrer">%s</a>(MIT)을 바탕으로 합니다</p>\n'
    ) % (e(c["mac"], quote=False), e(c["win"], quote=False), e(c["help"], quote=False),
         a["url"], a["name"], b["url"], b["name"])
    screen = "Wave Terminal 설치 도우미 %s\n다시 실행: %s\n%s\n%s (%s · %s)\n" % (
        c["tag"], c["mac"] + "  |  " + c["win"], c["help"], c["origin"], a["url"], b["url"])
    return {"readme": readme, "get": get, "screen": screen}


def decode(kind, text):
    """각 조각에서 정본 문자열을 다시 꺼낸다 (HTML 은 unescape, 마크다운 링크는 이름만)."""
    if kind == "get":
        text = html.unescape(re.sub(r"<[^>]+>", "", text))
    if kind == "readme":
        text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    return text


def check_cross(parts, m):
    c = canon(m)
    bad = []
    for kind, text in parts.items():
        t = decode(kind, text)
        for key in ("mac", "win", "origin", "help"):
            if c[key] not in t:
                bad.append("%s 조각에 정본 %s 없음" % (kind, key))
    return bad


def check(m):
    parts = render(m)
    bad = check_cross(parts, m)
    for kind, name in FILES.items():
        p = OUT / name
        if not p.exists() or p.read_text(encoding="utf-8") != parts[kind]:
            bad.append("out/%s 가 manifest 와 다름 — gen.py 를 다시 돌릴 것" % name)
    return bad


def against(m, root):
    """현행 파일 vs 정본. 같지 않은 항목을 [(파일, 항목, 상태)] 로."""
    c, root, rows = canon(m), pathlib.Path(root), []
    read = lambda p: (root / p).read_text(encoding="utf-8")
    steps = json.loads(read("steps.json"))
    rel = steps["release"]
    rows.append(("steps.json", "installer 판", "ok" if steps["version"] == c["tag"].lstrip("v") else "다름: %s" % steps["version"]))
    rows.append(("steps.json", "app mac/win 판", "ok" if (rel["macos_version"], rel["version"]) == (m["app"]["macos"], m["app"]["windows"]) else "다름"))
    fp = m["fingerprints"]
    got = {"macos_arm64_sha256": rel["sha256"]["macos_arm64"], "macos_x64_sha256": rel["sha256"]["macos_x64"], "windows_x64_sha256": rel["sha256"]["windows_x64"]}
    rows.append(("steps.json", "지문 3개", "ok" if got == fp else "다름"))
    for f, text in (("README.md", read("README.md")), ("site/index.html", html.unescape(read("site/index.html"))), ("site/app.js", read("site/app.js").replace('\\\\', '\\').replace('\\"', '"').replace("\\'", "'"))):
        for key in ("mac", "win", "origin", "help"):
            if (f == "site/app.js" and key in ("origin", "help")) or (f == "site/index.html" and key == "win"):
                continue  # app.js 는 명령만, index.html 은 mac 명령만 담는다(win 은 app.js 가 채움)
            rows.append((f, key, "ok" if c[key] in text else "없음/다름"))
    return rows


def main(argv):
    m = json.loads((HERE / "manifest.json").read_text(encoding="utf-8"))
    if "--check" in argv:
        bad = check(m)
        print("\n".join(bad) or "OK: 세 조각 바이트 일치 · out/ 최신")
        return 1 if bad else 0
    if "--against" in argv:
        rows = against(m, argv[argv.index("--against") + 1])
        for r in rows:
            print("| %s | %s | %s |" % r)
        return 1 if any(r[2] != "ok" for r in rows) else 0
    OUT.mkdir(exist_ok=True)
    for kind, text in render(m).items():
        (OUT / FILES[kind]).write_text(text, encoding="utf-8")
    print("wrote", ", ".join(FILES.values()))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
