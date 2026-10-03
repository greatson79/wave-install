#!/usr/bin/env python3
"""Make the CI judge job fail if a saved gate table contains a FAIL cell."""
import json
from pathlib import Path
import sys


def main(paths):
    failures = []
    for name in paths:
        try:
            rows = json.loads(Path(name).read_text(encoding='utf-8'))
            if not isinstance(rows, list):
                raise ValueError('gate table must be a list')
            for row in rows:
                if not isinstance(row, dict) or not isinstance(row.get('id'), str):
                    raise ValueError('invalid gate row')
                for axis in ('mac', 'win', 'common'):
                    if axis not in row:
                        continue
                    cell = row[axis]
                    if not isinstance(cell, list) or not cell or not isinstance(cell[0], str):
                        raise ValueError('invalid gate cell')
                    if cell[0] == 'FAIL':
                        failures.append(f"{row['id']}.{axis}=FAIL")
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            print(f'gate table unreadable: {name}: {exc}', file=sys.stderr)
            return 2
    if failures:
        print('gate verdict FAIL: ' + ', '.join(failures), file=sys.stderr)
        return 1
    print('gate verdict tables contain no FAIL cells')
    return 0


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print('usage: fail-on-verdict.py gate-result.json [...]', file=sys.stderr)
        sys.exit(2)
    sys.exit(main(sys.argv[1:]))
