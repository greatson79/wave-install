#!/usr/bin/env python3
"""판정 표(gate-result.json)에 FAIL 이 하나라도 있으면 실패 — check_gate_table.py <gate-result.json> […]
미측정(G8·G9·H 처럼 RC 에서 측정 안 하는 칸)은 실패가 아니다. gate.py 는 미측정이 항상 있어 종료값 1 이라 판정 잡이 `| tee` 로 종료값을 버렸고, 그래서 FAIL 이 있어도 잡이 success 였다."""
import json, sys

def judge(path):
    try: table = json.load(open(path, encoding="utf-8-sig"))
    except (OSError, ValueError) as e: return 1, "판정 표를 못 읽음: %s (%s)" % (path, type(e).__name__)
    fails = ["%s %s: %s" % (g.get("id"), k, str(g[k][1])[:90]) for g in table for k in ("mac", "win", "common") if k in g and g[k][0] == "FAIL"]
    if fails: return 1, "FAIL %d건 — %s" % (len(fails), "; ".join(fails))
    return 0, "FAIL 0건 (미측정 %d칸은 실패 아님)" % sum(1 for g in table for k in ("mac", "win", "common") if k in g and g[k][0] not in ("PASS", "FAIL"))

if __name__ == "__main__":
    rcs = []
    for p in sys.argv[1:]:
        rc, msg = judge(p); print("[gate-table] %s: %s (rc=%d)" % (p, msg, rc)); rcs.append(rc)
    sys.exit(1 if any(rcs) or not rcs else 0)
