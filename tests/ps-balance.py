#!/usr/bin/env python3
"""Early PowerShell delimiter check, adapted from oogisoogi/jarvis-install (MIT).

Not a parser: string interpolation is opaque. Native PS 5.1/7 parsing remains
required in CI. Both quoted strings may span lines; unclosed quotes/comments fail.
"""
from pathlib import Path
import sys

PAIRS = {')': '(', '}': '{', ']': '['}


def check(path):
    text = Path(path).read_text(encoding='utf-8-sig')
    stack, errors = [], []
    i, line, quote, here, block = 0, 1, None, None, 0
    start_line = 1
    while i < len(text):
        char = text[i]
        pair = text[i:i+2]
        if char == '\n':
            line += 1
        if here:
            if (i == 0 or text[i-1] == '\n') and pair == here+'@':
                here = None
                i += 2
            else:
                i += 1
            continue
        if block:
            if pair == '<#':
                block += 1
                i += 2
            elif pair == '#>':
                block -= 1
                i += 2
            else:
                i += 1
            continue
        if quote:
            if quote == '"' and char == '`':
                if text[i+1:i+2] == '\n':
                    line += 1
                i += 2
            elif char == quote:
                if text[i+1:i+2] == quote:
                    i += 2
                else:
                    quote = None
                    i += 1
            else:
                i += 1
            continue
        if pair == '<#':
            block, start_line = 1, line
            i += 2
        elif char == '#':
            end = text.find('\n', i)
            i = len(text) if end == -1 else end
        elif char == '`':
            if text[i+1:i+2] == '\n':
                line += 1
            i += 2
        elif pair in ("@'", '@"') and not text[i+2:].split('\n', 1)[0].strip():
            here, start_line = pair[1], line
            i += 2
        elif char in "'\"":
            quote, start_line = char, line
            i += 1
        else:
            if char in PAIRS.values():
                stack.append((char, line))
            elif char in PAIRS:
                if not stack or stack[-1][0] != PAIRS[char]:
                    errors.append(f'{path}:{line}: unmatched {char}')
                else:
                    stack.pop()
            i += 1
    errors.extend(f'{path}:{ln}: unclosed {char}' for char, ln in stack)
    if quote or here or block:
        errors.append(f'{path}:{start_line}: unclosed string or block comment')
    return errors


def main():
    if len(sys.argv) < 2:
        print('usage: ps-balance.py file.ps1 [...]', file=sys.stderr)
        return 2
    errors = []
    for path in sys.argv[1:]:
        try:
            problems = check(path)
        except (OSError, UnicodeError) as exc:
            problems = [f'{path}: {exc}']
        errors.extend(problems)
        if not problems:
            print(f'PASS: {path} delimiter balance (native parsing still required)')
    for message in errors:
        print(message, file=sys.stderr)
    return int(bool(errors))

if __name__ == '__main__':
    sys.exit(main())
