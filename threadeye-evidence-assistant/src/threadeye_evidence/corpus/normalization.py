"""Deterministic Markdown normalization without rendering or executing document content."""

from __future__ import annotations

import re

_FENCE = re.compile(r"^\s*(`{3,}|~{3,})")


def normalize_markdown(text: str) -> str:
    """Normalize line endings and unnecessary blank space while preserving Markdown structure."""

    text = text.replace("\r\n", "\n").replace("\r", "\n")
    output: list[str] = []
    in_fence = False
    fence_marker = ""
    previous_blank = False
    for raw_line in text.split("\n"):
        fence = _FENCE.match(raw_line)
        if fence:
            marker = fence.group(1)
            if not in_fence:
                in_fence = True
                fence_marker = marker[0]
            elif marker[0] == fence_marker:
                in_fence = False
                fence_marker = ""
            output.append(raw_line.rstrip())
            previous_blank = False
            continue

        if in_fence:
            output.append(raw_line)
            previous_blank = False
            continue

        line = raw_line.rstrip()
        if not line:
            if output and not previous_blank:
                output.append("")
            previous_blank = True
            continue
        output.append(line)
        previous_blank = False

    while output and not output[-1]:
        output.pop()
    while output and not output[0]:
        output.pop(0)
    return "\n".join(output) + ("\n" if output else "")
