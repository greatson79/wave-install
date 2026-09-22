#!/usr/bin/env bash
# 사용법: scripts/sync-get.sh v0.1.3 /절대경로/homepage-worktree /절대경로/blog-worktree
# 태그 원본은 읽기만 한다. 두 대상 모두 origin/main의 깨끗한 별도 worktree여야 한다.
set -euo pipefail
if [[ $# -ne 3 ]]; then
  printf '%s\n' '사용법: scripts/sync-get.sh <tag> <homepage-worktree> <blog-worktree>' >&2
  exit 2
fi
sync_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
python3 - "$sync_root" "$@" <<'SYNC_PY'
import hashlib
import json
import pathlib
import re
import subprocess
import sys

source = pathlib.Path(sys.argv[1]).resolve()
tag = sys.argv[2]
files = ("index.html", "app.js", "styles.css", "steps.json", "steps.schema.json")

def fail(reason):
    raise SystemExit(reason)

def git(root, *args):
    return subprocess.check_output(["git", "-C", str(root), *args])

if not re.fullmatch(r"v[0-9]+\.[0-9]+\.[0-9]+", tag):
    fail("INVALID_TAG")
ref = "refs/tags/" + tag
commit = git(source, "rev-parse", "--verify", ref + "^{commit}").decode().strip()
contents = {name: git(source, "show", ref + ":site/" + name) for name in files}
steps = json.loads(contents["steps.json"])
if steps.get("version") != tag[1:] or len(steps.get("steps", [])) != 10:
    fail("TAG_VERSION_OR_STEP_COUNT_MISMATCH")
html = contents["index.html"].decode()
if "<base" in html.lower() or html.count("<head>") != 1 or "LIGHT / " + tag not in html:
    fail("UNEXPECTED_SOURCE_HTML")
html = html.replace("<head>", '<head>\n    <base href="/get/">\n    <meta name="wave-install-source-tag" content="' + tag + '">\n    <meta name="wave-install-source-commit" content="' + commit + '">', 1)
contents["index.html"] = html.encode()
app = contents["app.js"].decode()
old = '["../steps.json", "./steps.json"]'
if app.count(old) == 1:
    app = app.replace(old, '["./steps.json"]', 1)
elif app.count('["./steps.json"]') != 1 or "../steps.json" in app:
    fail("UNEXPECTED_STEPS_FETCH_PATH")
contents["app.js"] = app.encode()

# 두 대상의 상태 검사를 모두 끝낸 후에만 파일을 쓴다.
targets = []
for arg, expected in zip(sys.argv[3:], ("wave-homepage", "kylechoi-blog")):
    given = pathlib.Path(arg)
    if not given.is_absolute() or given.is_symlink():
        fail("ABSOLUTE_WORKTREE_PATH_REQUIRED")
    target = given.resolve()
    if pathlib.Path(git(target, "rev-parse", "--show-toplevel").decode().strip()).resolve() != target:
        fail("WORKTREE_ROOT_REQUIRED")
    work_git = pathlib.Path(git(target, "rev-parse", "--absolute-git-dir").decode().strip()).resolve()
    common = pathlib.Path(git(target, "rev-parse", "--path-format=absolute", "--git-common-dir").decode().strip()).resolve()
    if work_git == common:
        fail("ISOLATED_WORKTREE_REQUIRED")
    origin = git(target, "remote", "get-url", "origin").decode().strip()
    allowed = ("https://github.com/greatson79/" + expected + ".git", "https://github.com/greatson79/" + expected, "git@github.com:greatson79/" + expected + ".git")
    if origin not in allowed:
        fail("TARGET_REPOSITORY_MISMATCH")
    if git(target, "rev-parse", "HEAD") != git(target, "rev-parse", "origin/main"):
        fail("ORIGIN_MAIN_REQUIRED")
    if git(target, "status", "--porcelain"):
        fail("DIRTY_WORKTREE")
    folder = target / "public/get"
    for path in [target / "public", folder, *[folder / name for name in files]]:
        if path.is_symlink():
            fail("SYMLINK_DESTINATION_REJECTED")
    for path in (target / "public", folder):
        if path.exists() and not path.is_dir():
            fail("DESTINATION_TYPE_MISMATCH")
    for name in files:
        path = folder / name
        if path.exists() and not path.is_file():
            fail("DESTINATION_TYPE_MISMATCH")
    if folder.exists() and {x.name for x in folder.iterdir()} - set(files):
        fail("UNEXPECTED_GET_CONTENT")
    targets.append(folder)

results = []
for folder in targets:
    folder.mkdir(parents=True, exist_ok=True)
    for name, data in contents.items():
        (folder / name).write_bytes(data)
        if (folder / name).read_bytes() != data:
            fail("WRITE_VERIFICATION_FAILED")
    results.append({"target": str(folder), "status": "completed", "files": {name: {"bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()} for name, data in contents.items()}})
print(json.dumps({"source_tag": tag, "source_commit": commit, "results": results}, ensure_ascii=False, indent=2))
SYNC_PY
