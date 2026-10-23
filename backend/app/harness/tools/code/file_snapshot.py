"""Exact, portable snapshots for source text and binary research artifacts."""
from __future__ import annotations

import base64
from dataclasses import dataclass
import hashlib
from typing import Any

FileContent = str | bytes | None


@dataclass(frozen=True)
class FileSnapshot:
    path: str
    existed: bool
    sha256: str
    content: str
    encoding: str = 'utf-8'

    @classmethod
    def capture(cls, path: str, raw: bytes) -> FileSnapshot:
        digest = 'sha256:' + hashlib.sha256(raw).hexdigest()
        try:
            text = raw.decode('utf-8')
            if '\x00' not in text:
                return cls(path, True, digest, text)
        except UnicodeDecodeError:
            pass
        return cls(path, True, digest, base64.b64encode(raw).decode('ascii'), 'base64')


def content_bytes(value: str | bytes) -> bytes:
    return value.encode('utf-8') if isinstance(value, str) else value


def snapshot_content(snapshot: dict[str, Any]) -> FileContent:
    content, existed = snapshot.get('content'), snapshot.get('existed')
    if not isinstance(content, str) or type(existed) is not bool:
        raise ValueError('Invalid file snapshot')
    encoding = snapshot.get('encoding', 'utf-8')
    if encoding == 'base64':
        value: str | bytes = base64.b64decode(content, validate=True)
    elif encoding == 'utf-8':
        value = content
    else:
        raise ValueError('Unsupported snapshot encoding')
    expected = 'sha256:' + hashlib.sha256(content_bytes(value)).hexdigest() if existed else ''
    if snapshot.get('sha256') != expected:
        raise ValueError('Snapshot content fingerprint differs')
    return value if existed else None
