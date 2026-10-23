"""Parse markdown documents with YAML frontmatter.

Wraps `python-frontmatter` so the rest of the codebase only sees a typed
`ParsedDoc`.
"""
from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any

import frontmatter


@dataclass(frozen=True)
class ParsedDoc:
    metadata: dict[str, Any]
    body: str


class FrontmatterError(ValueError):
    """Raised when the document cannot be parsed."""


def normalize_document(text: str) -> str:
    """Unwrap transport presentation, without guessing any research fields."""
    text = text.lstrip("\ufeff").replace("\r\n", "\n").replace("\r", "\n").strip()
    wrapped = re.fullmatch(r"(`{3,}|~{3,})(?:markdown|md)?[ \t]*\n(.*)\n\1[ \t]*", text, re.DOTALL | re.IGNORECASE)
    if wrapped and wrapped[2].lstrip().startswith("---\n"):
        text = wrapped[2].strip()
    return text


def parse(text: str) -> ParsedDoc:
    """Parse a markdown string with YAML frontmatter.

    Raises FrontmatterError on syntactic failure.
    """
    try:
        post = frontmatter.loads(normalize_document(text))
    except Exception as exc:  # frontmatter raises various errors
        raise FrontmatterError(f"failed to parse frontmatter: {exc}") from exc
    metadata: dict[str, Any] = dict(post.metadata) if post.metadata else {}
    return ParsedDoc(metadata=metadata, body=post.content)


def dumps(metadata: dict[str, Any], body: str) -> str:
    """Serialize back to a single markdown string with YAML frontmatter."""
    post = frontmatter.Post(body, **metadata)
    rendered: Any = frontmatter.dumps(post)
    if isinstance(rendered, bytes):
        return rendered.decode("utf-8")
    return str(rendered)


def document_from_parts(metadata: Any, body: Any) -> str:
    """Shared native/ZCode document boundary; duplicate wrappers are cosmetic.

    Conflicting metadata is ambiguous and still rejected. Empty prose is
    allowed: a structured experiment matrix can be the complete deliverable.
    """
    if not isinstance(metadata, dict) or not metadata:
        raise FrontmatterError("metadata must be a nonempty object")
    if not isinstance(body, str):
        raise FrontmatterError("body must be Markdown text")
    normalized = normalize_document(body)
    if normalized.startswith("---\n"):
        embedded = parse(normalized)
        if embedded.metadata:
            conflicts = [key for key in embedded.metadata if key in metadata and metadata[key] != embedded.metadata[key]]
            if conflicts:
                raise FrontmatterError("conflicting embedded metadata: " + ", ".join(conflicts))
            return dumps({**embedded.metadata, **metadata}, embedded.body)
    return dumps(metadata, body)


def close_unclosed_frontmatter(text: str) -> str:
    """Repair a narrow LLM formatting error: missing closing frontmatter fence.

    This does not change the parser's behavior for user-authored files. It is
    meant for provider output cleanup before validation, where models sometimes
    emit ``---`` + YAML + markdown body but forget the second ``---``.
    """
    stripped = text.strip()
    if not stripped.startswith("---\n"):
        return text
    if "\n---\n" in stripped[4:] or stripped.endswith("\n---"):
        return text

    lines = stripped.splitlines()
    for index, line in enumerate(lines[1:], start=1):
        if line.startswith("# ") or line.startswith("## ") or line.startswith("<!--"):
            repaired = "\n".join([*lines[:index], "---", *lines[index:]])
            return repaired + ("\n" if text.endswith("\n") else "")
    return text
