"""수강생 설치 한 줄 → 시험용 한 줄. 보증: 수강생이 치는 그 한 줄이 주소만 시험 서버로 바뀐 채 그대로 실행된다.
한 줄의 출처는 사람이 읽는 README 가 아니라 기계 계약 scripts/ci/install-lines.json 1곳이다(README 를 바꿔도 이 경로는 안 깨진다).
시험 서버는 /mac·/win 을 릴리스 파일로 307 넘긴다(serve_https.py · 게시 서버와 같은 모양)."""
import json, pathlib, re

CONTRACT = pathlib.Path("scripts/ci/install-lines.json")
START = {"mac": ("curl ",), "win": ("irm ", "powershell ")}


def contract(root):
    return json.loads((pathlib.Path(root) / CONTRACT).read_text(encoding="utf-8"))


def contract_line(root, os_name):
    """root(저장소 루트)의 계약 파일에서 해당 OS 한 줄. 공개 주소(public_base)를 담지 않았거나 명령 모양이 아니면 종료."""
    c = contract(root)
    line, public = c.get(os_name), c.get("public_base")
    if not (isinstance(line, str) and public and public.endswith("/") and public in line and line.startswith(START[os_name])):
        raise SystemExit("install-lines.json 의 %s 한 줄이 계약 모양이 아님: %r" % (os_name, line))
    return line


def rc_one_line(root, os_name, base):
    """계약 줄에서 공개 주소(public_base)만 시험 서버 주소로 치환 — 나머지 글자는 그대로."""
    if not base.endswith("/"):
        raise ValueError("base 는 / 로 끝나야 함")
    return contract_line(root, os_name).replace(contract(root)["public_base"], base)
