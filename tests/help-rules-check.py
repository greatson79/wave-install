#!/usr/bin/env python3
"""TSV is canonical; check embedded installer data, generated docs and dispatch."""
import argparse
import csv
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
CATEGORIES = {'AV', 'NET', 'RM', 'PATH', 'LOGIN', 'PERM', 'DISK', 'VER', 'DL', 'UNK', 'HOME', 'PS32'}


def render(rows):
    text = '# Windows 설치 진단 코드\n\n'
    text += '`tests/help-rules.tsv` 정본에서 생성합니다. `python3 tests/help-rules-check.py --write`로 갱신하세요.\n\n'
    text += '12범주·19세부 코드입니다. 원본 TSV의 18행에 설치기가 사용하던 PS32를 포함했습니다. 사례 열은 우리 코드·회귀 검체의 근거이며, 실기 관측과 구별합니다.\n'
    for row in rows:
        text += f"\n<a id=\"{row['code'].lower()}\"></a>\n\n## {row['code']} — {row['symptom']}\n\n1. {row['action1']}\n2. {row['action2']}\n\n근거: {row['case']} · OS: {row['os']}\n"
    return text


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', type=Path, default=ROOT)
    parser.add_argument('--write', action='store_true', help='generate docs only; installer drift remains an error')
    args = parser.parse_args()
    rows = list(csv.DictReader((args.root/'tests/help-rules.tsv').open(encoding='utf-8'), delimiter='\t'))
    codes = [r['code'] for r in rows]
    assert len(codes) == len(set(codes)), 'duplicate codes'
    assert {c.split('-')[1] for c in codes} == CATEGORIES, '12-category mismatch'
    assert all(re.fullmatch(r'J-[A-Z0-9]+-\d{2}', c) for c in codes)
    assert codes[-1] == 'J-UNK-00', 'fallback must be last'
    for row in rows:
        assert all(row.values()) and row['os'] == 'win', 'incomplete row'
    source = (args.root/'bootstrap.ps1').read_text(encoding='utf-8-sig')
    match = re.search(r"\$HelpRulesJson = @'\n(.*?)\n'@", source, re.S)
    assert match, 'embedded help rules absent'
    assert json.loads(match[1]) == rows, 'installer differs from canonical TSV (including patterns/actions)'
    assert set(re.findall(r'J-[A-Z0-9]+-\d{2}', source)) == set(codes), 'installer/table code-set drift'
    path = args.root/'docs/help-codes.md'
    if args.write:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(render(rows), encoding='utf-8')
    assert path.read_text(encoding='utf-8') == render(rows), 'docs drift: run --write'
    print(f'PASS: table / installer / docs: {len(codes)} codes, 12 categories')

if __name__ == '__main__':
    try:
        main()
    except (AssertionError, OSError, ValueError) as e:
        print(f'FAIL: {e}', file=sys.stderr)
        sys.exit(1)
