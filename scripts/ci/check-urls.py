#!/usr/bin/env python3
"""게시 전 URL 검사: steps.json · README.md · site/(/get 사본) 안의 모든 http(s) 주소를 뽑아 HTTP 코드 표를 내고, 404(410)가 하나라도 있으면 실패한다.
두 방식 — 게시 전: --pending-tag vX.Y.Z-rc.N (그 태그 주소만 「예외」로 표시: 게시 전이라 404 가 정상) · 게시 후: --after-publish (예외 0).
종료값: 0 통과 · 1 404/410 있음 · 3 측정 못 한 주소 있음(네트워크 오류 — 통과로 치지 않는다) · 2 사용법.
표: 코드 | 분류 | 주소 | 위치(파일:줄). 비밀값·토큰은 다루지 않는다(주소 문자열만)."""
import argparse
import html
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_FILES = ["steps.json", "README.md", "site/index.html", "site/app.js", "site/steps.json"]
URL = re.compile(r"https?://[^\s\"'<>`\\)\]}]+")
LOOPBACK = re.compile(r"^https?://(127\.0\.0\.1|localhost|\[::1\])([:/]|$)")
TRIM = ".,;:"


def extract_urls(text):
    """[(줄 번호, 주소)] — 따옴표·괄호·역슬래시에서 끊고 끝의 문장부호를 뗀다."""
    found = []
    for number, line in enumerate(text.splitlines(), 1):
        for match in URL.finditer(html.unescape(line)):
            url = match.group(0).rstrip(TRIM)
            if url.endswith("/") is False and url[-1:] in TRIM:
                url = url.rstrip(TRIM)
            found.append((number, url))
    return found


def collect(files, root=ROOT, include_loopback=False):
    """주소 → [파일:줄 …] (등장 순서 유지)."""
    where = {}
    for name in files:
        text = (Path(root) / name).read_text(encoding="utf-8")
        for number, url in extract_urls(text):
            if LOOPBACK.match(url) and not include_loopback:
                continue
            where.setdefault(url, []).append("%s:%d" % (name, number))
    return where


def fetch_status(url, timeout=20):
    """HTTP 코드 또는 None(측정 실패). HEAD 가 막히면 1바이트 GET 으로 다시."""
    def call(method):
        request = urllib.request.Request(url, method=method, headers={"User-Agent": "wave-install-url-check", "Range": "bytes=0-0"} if method == "GET" else {"User-Agent": "wave-install-url-check"})
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return response.status
        except urllib.error.HTTPError as error:
            return error.code
    for attempt in range(3):
        try:
            code = call("HEAD")
            if code in (403, 405, 501):
                code = call("GET")
            if code in (429, 500, 502, 503, 504) and attempt < 2:
                continue
            return code
        except (urllib.error.URLError, TimeoutError, OSError):
            if attempt == 2:
                return None
    return None


def is_pending(url, tags):
    return any(("/releases/download/%s/" % tag) in url or ("/releases/tag/%s" % tag) in url or ("/archive/refs/tags/%s." % tag) in url for tag in tags)


def classify(code, url, tags):
    """분류: OK · 예외(게시 전 대기 태그) · 404 · 측정실패 · 기타(코드 그대로 보고하되 실패는 아님)."""
    if code is None:
        return "측정실패"
    if code in (404, 410):
        return "예외" if is_pending(url, tags) else "404"
    if 200 <= code < 400:
        return "OK(이미 게시됨)" if is_pending(url, tags) else "OK"
    return "기타"


def run(files, fetch=fetch_status, tags=(), root=ROOT, include_loopback=False, out=sys.stdout):
    where = collect(files, root, include_loopback)
    rows = []
    for url, places in where.items():
        code = fetch(url)
        rows.append((code, classify(code, url, tags), url, places))
    out.write("코드 | 분류 | 주소 | 위치\n")
    for code, kind, url, places in rows:
        out.write("%s | %s | %s | %s\n" % ("-" if code is None else code, kind, url, ", ".join(places[:4]) + (" …" if len(places) > 4 else "")))
    bad = [r for r in rows if r[1] == "404"]
    unmeasured = [r for r in rows if r[1] == "측정실패"]
    pending = [r for r in rows if r[1] == "예외"]
    out.write("합계: 주소 %d개 · 404 %d개 · 예외(게시 전 대기 태그) %d개 · 측정 실패 %d개\n" % (len(rows), len(bad), len(pending), len(unmeasured)))
    return 1 if bad else (3 if unmeasured else 0)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--pending-tag", action="append", help="게시 전: 이 태그의 주소만 404 를 예외로 표시(여러 번 가능)")
    mode.add_argument("--after-publish", action="store_true", help="게시 후: 예외 없이 모든 주소가 열려야 함")
    parser.add_argument("--files", nargs="+", default=DEFAULT_FILES)
    parser.add_argument("--root", default=str(ROOT))
    parser.add_argument("--include-loopback", action="store_true", help="시험용: 127.0.0.1 주소도 검사")
    args = parser.parse_args(argv)
    return run(args.files, tags=tuple(args.pending_tag or ()), root=args.root, include_loopback=args.include_loopback)


if __name__ == "__main__":
    sys.exit(main())
