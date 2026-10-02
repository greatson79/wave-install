#!/usr/bin/env python3
"""P3 관문 판정기 — 증거 폴더를 읽어 G1~G9·H1~H5 를 PASS / FAIL / 미측정 으로 판정한다 (표준 라이브러리만).
  gate.py EVIDENCE_ROOT [--json]      exit 0 = 전부 PASS, 1 = 하나라도 FAIL 또는 미측정
증거 규약(파일 이름·PASS 조건)은 관문표.md. 규칙: 증거 파일이 없거나 원본(raw) 해시가 안 맞으면 PASS 가 될 수 없다.
"""
import hashlib, json, pathlib, sys

PASS, FAIL, NA = "PASS", "FAIL", "미측정"
ROLES = {"master", "cso", "worker"}


def load(p):
    return json.loads(pathlib.Path(p).read_text(encoding="utf-8-sig"))


def raw_ok(base, doc):
    """doc['raw'] = [{path, sha256}] — 비어 있거나 해시가 다르면 (False, 사유)."""
    raws = doc.get("raw")
    if not raws:
        return False, "원본(raw) 목록 없음"
    for r in raws:
        p = base / r["path"]
        if not p.is_file():
            return False, "원본 없음: " + r["path"]
        if hashlib.sha256(p.read_bytes()).hexdigest() != r["sha256"]:
            return False, "원본 해시 불일치: " + r["path"]
    return True, ""


def need(base, name, raw=True):
    """증거 JSON 을 읽는다. 없으면 (None, 미측정 결과). raw 필수인 계약 파일은 원본 검증까지."""
    p = base / name
    if not p.is_file():
        return None, (NA, "증거 없음: " + name)
    try:
        doc = load(p)
    except Exception as e:  # 깨진 JSON 은 통과도 미측정도 아닌 증거 훼손
        return None, (FAIL, "증거 읽기 실패: %s (%s)" % (name, type(e).__name__))
    if raw:
        ok, why = raw_ok(base, doc)
        if not ok:
            return None, (NA, why) if "없음" in why else (FAIL, why)
    return doc, None


# ── 관문 판정 함수: (증거 폴더[, 공통 폴더]) -> (verdict, 한 줄) ─────────────────
def g1(b, c=None):
    d, bad = need(b, "G1_state.json", raw=False)
    if bad: return bad
    steps = d.get("steps", {})
    st = sorted(k for k, v in steps.items() if v.get("status") != "completed")
    if len(steps) == 10 and not st and d.get("required_steps_passed") is True and d.get("status") == "completed":
        return PASS, "10/10 completed"
    return FAIL, "completed %d/10 · 미완 %s · status=%s" % (len(steps) - len(st), ",".join(st) or "-", d.get("status"))


def g2(b, c=None):
    d, bad = need(b, "G2_preflight.json", raw=False)
    if bad: return bad
    ck = d.get("checks", [])
    fails = [x["id"] for x in ck if x.get("status") == "FAIL"]
    warns = sorted(x["id"] for x in ck if x.get("status") == "WARN")
    if fails:
        return FAIL, "FAIL %d: %s" % (len(fails), ",".join(fails))
    allow = (c / "warn_allowlist.json") if c else None
    if not allow or not allow.is_file():
        return NA, "FAIL 0 · WARN %d 이지만 허용 WARN 목록(common/warn_allowlist.json) 없음" % len(warns)
    ok = set(load(allow).get(b.name if b.name in ("mac", "win") else b.parent.name, []))
    new = sorted(set(warns) - ok)
    return (FAIL, "새 WARN %d: %s" % (len(new), ",".join(new))) if new else (PASS, "FAIL 0 · WARN %d 전부 허용 목록 안" % len(warns))


def g3(b, c=None):
    d, bad = need(b, "G3_inject.json")
    if bad: return bad
    roles = d.get("roles", {})
    diff = sorted(r for r, v in roles.items() if v.get("injected_sha256") != v.get("pack_sha256"))
    mx = max([v.get("injected_bytes", 0) for v in roles.values()] or [0])
    note = " · 최대 주입 %dB (20KB 상한 존폐=결재 대기, 판정 제외)" % mx
    if not roles: return NA, "역할별 측정 없음"
    if diff or d.get("new_file_count") != 0:
        return FAIL, "원본 불일치 %s · .new %s%s" % (diff or "-", d.get("new_file_count"), note)
    return PASS, "주입=팩 원본 %d역할 · .new 0%s" % (len(roles), note)


def g4(b, c=None):
    d, bad = need(b, "G4_boot.json")
    if bad: return bad
    steps = {s["n"]: s["exit"] for s in d.get("steps", [])}
    badstep = sorted(n for n, e in steps.items() if e != 0)
    if badstep:
        return FAIL, "단계 %s 비0 종료 (%s)" % (badstep, ",".join(str(steps[n]) for n in badstep))
    if sorted(steps) != [1, 2, 3, 4, 5]: return NA, "①~⑤ 전부 측정되지 않음"
    seats = d.get("seats")
    if seats is None: return NA, "단계 exit 0 이지만 좌석 목록 없음"
    live = {s["role"] for s in seats if s.get("alive")}
    rev = sorted(r for r in live if r.startswith("reviewer"))
    if live - set(rev) != ROLES or rev:
        return FAIL, "패인 %s · 리뷰어 %s (기대: master·cso·worker + 리뷰어 0)" % (sorted(live - set(rev)), rev or 0)
    return PASS, "①~⑤ exit 0 · 패인 master·cso·worker · 리뷰어 0"


def sub(b, name, extra):
    """G5/G6: 하위 폴더에서 G2~G4 를 다시 판정하고 추가 증거를 요구한다."""
    s = b / name
    if not s.is_dir(): return NA, "증거 폴더 없음: %s/" % name
    got = [(k, f(s, b.parent / "common")) for k, f in (("G2", g2), ("G3", g3), ("G4", g4))]
    bad = [(k, r) for k, r in got if r[0] != PASS]
    e = extra(s)
    if e[0] != PASS: bad.append((name, e))
    if not bad: return PASS, "G2~G4 재통과 · " + e[1]
    worst = FAIL if any(r[0] == FAIL for _, r in bad) else NA
    return worst, "; ".join("%s=%s(%s)" % (k, r[0], r[1]) for k, r in bad)


def g5(b, c=None):
    def extra(s):
        d, bad = need(s, "G5_meta.json")
        if bad: return bad
        return (PASS, "from %s" % d["from_version"]) if d.get("from_version") == "0.2.3" else (FAIL, "from_version=%s (0.2.3 기대)" % d.get("from_version"))
    return sub(b, "G5", extra)


def g6(b, c=None):
    def extra(s):
        d, bad = need(s, "G6_claude_untouched.json")
        if bad: return bad
        same = d.get("before_sha256") == d.get("after_sha256")
        return (PASS, "~/.claude 무접촉") if same else (FAIL, "~/.claude 해시가 바뀜")
    return sub(b, "G6", extra)


def g7(b, c=None):
    d, bad = need(b, "G7_text.json")
    if bad: return bad
    lic = {"LICENSES/jarvis-install-MIT.txt", "LICENSE"} - set(d.get("license_files", []))
    if d.get("gen_check_exit") != 0: return FAIL, "gen.py --check exit %s" % d.get("gen_check_exit")
    return (FAIL, "라이선스 파일 누락: %s" % sorted(lic)) if lic else (PASS, "3곳 바이트 일치 · 라이선스 동봉")


def g8(b, c=None):
    d, bad = need(b, "G8_review.json")
    if bad: return bad
    v = d.get("verdicts", {})
    if set(v) != {"zen", "noah"}: return NA, "젠·노아 두 판정 모두 필요 (있는 것: %s)" % sorted(v)
    bad2 = sorted(k for k, x in v.items() if x.get("verdict") != "ACCEPT" or x.get("blocking") != 0)
    return (FAIL, "ACCEPT·blocking 0 아님: %s" % bad2) if bad2 else (PASS, "젠·노아 ACCEPT · blocking 0")


def g9(b, c=None):
    p = b / "real"
    docs = [(f.name, load(f)) for f in sorted(p.glob("*.json"))] if p.is_dir() else []
    if not docs: return NA, "실기 증거 없음 (real/*.json)"
    n = {"win": 0, "mac": 0}
    for name, d in docs:
        ok, why = raw_ok(p, d)
        if not ok: return (FAIL if "불일치" in why else NA), "%s: %s" % (name, why)
        hands = d.get("human_hands", {})
        live = {s for s in d.get("seats", [])}
        if live != ROLES or hands.get("other", 1) != 0 or hands.get("login_approve", 0) < 1:
            return FAIL, "%s: 패인 %s · 사람 손 %s (로그인 승인·코드 복사 외 0 기대)" % (name, sorted(live), hands)
        n[d["os"]] += 1
    if n["win"] < 2 or n["mac"] < 1: return NA, "실기 부족: win %d/2 · mac %d/1" % (n["win"], n["mac"])
    return PASS, "실기 3대 통과 (win %d · mac %d)" % (n["win"], n["mac"])


def hcheck(name, ok_fn, label):
    def f(b, c=None):
        d, bad = need(b, name)
        if bad: return bad
        ok, why = ok_fn(d)
        return (PASS, label) if ok else (FAIL, why)
    return f


h1 = hcheck("H1_help_landing.json", lambda d: (d.get("landed_s", 1e9) <= 60 and d.get("dashboard_listed") is True, "착지 %ss · 대시보드 %s" % (d.get("landed_s"), d.get("dashboard_listed"))), "막힘→60초 내 inbox 착지·대시보드 표시")
h2 = hcheck("H2_answer_shown.json", lambda d: (d.get("shown_s", 1e9) <= 120, "처방 표시 %ss" % d.get("shown_s")), "처방 파일→120초 내 설치 창 표시")
h3 = hcheck("H3_mask.json", lambda d: (bool(d.get("planted")) and all(v == 0 for v in d.get("found_in", {}).values()) and {"ledger", "dashboard", "sheet", "drive"} <= set(d.get("found_in", {})), "심은 값 검출 %s" % d.get("found_in")), "가림: 원장·대시보드·시트·드라이브 0")
h4 = hcheck("H4_failopen.json", lambda d: (d.get("server_blocked") is True and d.get("step10_ok") is True, "차단=%s · 10/10=%s" % (d.get("server_blocked"), d.get("step10_ok"))), "서버 차단에도 10/10")
h5 = hcheck("H5_dashboard_ledger.json", lambda d: (d.get("ledger_count") == d.get("dashboard_count") and d.get("status_match") is True, "원장 %s · 대시보드 %s · 상태일치 %s" % (d.get("ledger_count"), d.get("dashboard_count"), d.get("status_match"))), "대시보드=원장 건수·상태")


def h6(b, c=None):
    d, bad = need(b, "H6_concurrency.json")
    if bad: return bad
    sub_ids, got = set(d.get("submitted_ids", [])), set(d.get("received_ids", []))
    miss, qerr, n = sorted(sub_ids - got), d.get("quota_errors"), d.get("concurrent", 0)
    if n < 30 or len(sub_ids) < 30: return NA, "동시 30건 미만 측정 (동시 %s · 제출 %d)" % (n, len(sub_ids))
    if qerr is None: return NA, "쓰기 한도 오류 수(quota_errors) 기록 없음"
    if qerr or miss: return FAIL, "한도 오류 %s · 접수 누락 %d" % (qerr, len(miss))
    return PASS, "동시 %d건 · 한도 오류 0 · 접수 누락 0" % n


# (id, 제목, 적용 칸: os=맥·윈 각각 / common=한 번만, 판정 함수)
GATES = [("G1", "한 줄 설치 10/10", "os", g1), ("G2", "프리플라이트 FAIL 0 · 새 WARN 0", "os", g2),
         ("G3", "주입 바이트=팩 원본 · .new 0", "os", g3), ("G4", "선언 ①~⑤ exit 0 · 패인 3 · 리뷰어 0", "os", g4),
         ("G5", "업그레이드 v0.2.3→ 후 G2~G4", "os", g5), ("G6", "재설치 왕복 · ~/.claude 무접촉", "os", g6),
         ("G7", "문구 3곳 일치 · 라이선스 동봉", "common", g7), ("G8", "적대검수 젠·노아 blocking 0", "common", g8),
         ("G9", "실기 3대(윈2+맥1)", "common", g9),
         ("H1", "막힘→펄스 inbox 60초", "os", h1), ("H2", "처방→설치 창 2분", "os", h2),
         ("H3", "가림 시험", "os", h3), ("H4", "서버 차단 fail-open", "os", h4), ("H5", "대시보드=원장", "common", h5),
         ("H6", "동시 30건 · 시트 한도 오류 0 · 접수 누락 0", "common", h6)]


def judge(root):
    root = pathlib.Path(root)
    rows = []
    for gid, title, scope, fn in GATES:
        row = {"id": gid, "title": title}
        if scope == "os":
            for o in ("mac", "win"):
                b = root / o
                row[o] = fn(b, root / "common") if b.is_dir() else (NA, "증거 폴더 없음: %s/" % o)
        else:
            row["common"] = fn(root / "common", None) if (root / "common").is_dir() else (NA, "증거 폴더 없음: common/")
        rows.append(row)
    return rows


def render(rows):
    out = ["| 관문 | 맥 | 윈 | 비고 |", "|---|---|---|---|"]
    for r in rows:
        if "common" in r:
            v = r["common"]
            out.append("| %s %s | **%s** | (공통) | %s |" % (r["id"], r["title"], v[0], v[1]))
        else:
            out.append("| %s %s | **%s** | **%s** | 맥: %s / 윈: %s |" % (r["id"], r["title"], r["mac"][0], r["win"][0], r["mac"][1], r["win"][1]))
    return "\n".join(out)


def main(argv):
    rows = judge(argv[0])
    allv = [v[0] for r in rows for k, v in r.items() if k in ("mac", "win", "common")]
    if "--json" in argv:
        print(json.dumps(rows, ensure_ascii=False, indent=1))
    else:
        print(render(rows))
        print("\n요약: PASS %d · FAIL %d · 미측정 %d" % (allv.count(PASS), allv.count(FAIL), allv.count(NA)))
    return 0 if all(v == PASS for v in allv) else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]) if len(sys.argv) > 1 else sys.exit("usage: gate.py EVIDENCE_ROOT [--json]"))
