#!/usr/bin/env python3
"""C6: compare identical raw discoveries; require the applicable suite green."""
import json
from pathlib import Path
import sys


def accept(baseline, hotfix):
    before = set(baseline['failure_ids'] + baseline['error_ids'])
    after = set(hotfix['failure_ids'] + hotfix['error_ids'])
    return (baseline['tests'] > 0 and hotfix['tests'] > 0 and after <= before
            and hotfix['applicable_success'] is True and hotfix['applicable_tests'] > 0
            and hotfix['applicable_skipped'] == 0)


if __name__ == '__main__':
    baseline, hotfix = [json.loads(Path(p).read_text()) for p in sys.argv[1:]]
    print('BASELINE:', json.dumps(baseline, sort_keys=True))
    print('HOTFIX:', json.dumps(hotfix, sort_keys=True))
    raise SystemExit(0 if accept(baseline, hotfix) else 1)
