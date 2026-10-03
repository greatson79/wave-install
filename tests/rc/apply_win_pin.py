#!/usr/bin/env python3
"""윈 앱 핀 갱신 — apply_win_pin.py <설치기 트리> <setup.exe 경로> <게시 태그 예: v0.3.0-rc.4>
exe 의 실측 sha256·바이트로 steps.json(url 태그·bytes·sha256·windows_sha256sums_url)·tests/test_release_mapping.py(WIN_BASE·sha·bytes)·README.md 의 rc 태그를 한 번에 바꾼다.
이전 값은 파일에서 읽어 정확히 1곳씩 치환한다(0곳·2곳 이상이면 중단)."""
import hashlib, json, pathlib, re, sys
root, exe, tag = pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2]), sys.argv[3]
data = exe.read_bytes(); new_sha, new_n = hashlib.sha256(data).hexdigest(), len(data)
st = root / "steps.json"; txt = st.read_text(encoding="utf-8")
rel = json.loads(txt)["release"]; old_sha, old_n = rel["sha256"]["windows_x64"], rel["bytes"]["windows_x64"]
old_tag = re.search(r"/download/(v[\w.\-]+)/", rel["asset_url"]["windows_x64"]).group(1)
assert exe.name == rel["asset_name"]["windows_x64"], "자산 파일명이 steps.json 과 다르다: %s != %s" % (exe.name, rel["asset_name"]["windows_x64"])
def sub(path, pairs):
    t = path.read_text(encoding="utf-8")
    for old, new, want in pairs:
        assert t.count(old) == want, "%s: %r %d곳(기대 %d)" % (path.name, old, t.count(old), want)
        t = t.replace(old, new)
    path.write_text(t, encoding="utf-8")
sub(st, [(old_sha, new_sha, 1), ('"windows_x64": %d' % old_n, '"windows_x64": %d' % new_n, 1), ("/download/%s/wave-terminal" % old_tag, "/download/%s/wave-terminal" % tag, 1), ("/download/%s/SHA256SUMS" % old_tag, "/download/%s/SHA256SUMS" % tag, 1)])
sub(root / "tests/test_release_mapping.py", [(old_sha, new_sha, 1), ("windows_x64\": %d" % old_n, "windows_x64\": %d" % new_n, 1), ("/download/%s\"" % old_tag, "/download/%s\"" % tag, 1)])
sub(root / "README.md", [("`%s`" % old_tag, "`%s`" % tag, 1)])
print("sha256 %s -> %s\nbytes %d -> %d\ntag %s -> %s" % (old_sha[:8], new_sha[:8], old_n, new_n, old_tag, tag))
