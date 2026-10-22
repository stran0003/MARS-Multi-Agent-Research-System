"""Normalize presentation details of textual diffs, never invent source content."""
from __future__ import annotations

import re


def normalize_patch(text: str) -> str:
    lines = text.replace('\r\n', '\n').splitlines()
    if lines and lines[0].startswith('```') and lines[-1] == '```':
        lines = lines[1:-1]
    result: list[str] = []
    index = 0
    while index < len(lines):
        line = lines[index]
        match = re.fullmatch(r'@@ -(\d+)(?:,\d+)? \+(\d+)(?:,\d+)? @@(.*)', line)
        if not match:
            result.append(line)
            index += 1
            continue
        body: list[str] = []
        index += 1
        while index < len(lines):
            current = lines[index]
            if (current.startswith(('@@', 'diff --git ')) or
                    current.startswith('--- ') and index + 1 < len(lines) and lines[index + 1].startswith('+++ ')):
                break
            # Empty context lines are often emitted without their leading space.
            body.append(current if current else ' ')
            index += 1
        before = sum(line.startswith((' ', '-')) for line in body)
        after = sum(line.startswith((' ', '+')) for line in body)
        result.append(f'@@ -{match[1]},{before} +{match[2]},{after} @@{match[3]}')
        result.extend(body)
    return '\n'.join(result) + '\n' if result else ''
