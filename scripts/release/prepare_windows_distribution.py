"""Prepare a verified offline ZIP for a normal Git branch, without LFS."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import zipfile


def digest(path: Path) -> str:
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def split_dependencies(root: Path, *, piece_bytes: int = 48 * 1024 * 1024) -> None:
    """Preserve logical checksums while keeping every committed blob below 50 MiB."""
    if piece_bytes < 1 or piece_bytes > 48 * 1024 * 1024:
        raise ValueError('Invalid Git dependency piece size')
    bundle = root / 'dependencies/offline'
    marker_path = root / 'WINDOWS-OFFLINE.json'
    marker = json.loads(marker_path.read_text(encoding='utf-8'))
    manifest_path = bundle / 'manifest.json'
    if digest(manifest_path) != marker['manifest_sha256']:
        raise ValueError('Offline manifest differs from the verified archive')
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    for entry in manifest['files']:
        relative = PurePosixPath(entry['path'])
        if relative.is_absolute() or '..' in relative.parts or '\\' in entry['path']:
            raise ValueError('Invalid offline dependency path')
        source = bundle.joinpath(*relative.parts)
        if source.is_symlink() or not source.resolve().is_relative_to(bundle.resolve()):
            raise ValueError('Invalid offline dependency location')
        if source.stat().st_size != entry['bytes'] or digest(source) != entry['sha256']:
            raise ValueError('Offline dependency checksum mismatch: ' + entry['path'])
        if source.stat().st_size <= piece_bytes:
            continue
        directory = bundle / 'file-parts' / entry['sha256']
        directory.mkdir(parents=True, exist_ok=False)
        parts = []
        with source.open('rb') as stream:
            index = 0
            while True:
                remaining = min(piece_bytes, entry['bytes'] - stream.tell())
                if not remaining:
                    break
                part = directory / f'{index:04d}.part'
                with part.open('xb') as output:
                    while remaining:
                        chunk = stream.read(min(1024 * 1024, remaining))
                        if not chunk:
                            raise ValueError('Dependency changed while splitting')
                        output.write(chunk)
                        remaining -= len(chunk)
                parts.append({'path': part.relative_to(bundle).as_posix(),
                              'bytes': part.stat().st_size, 'sha256': digest(part)})
                index += 1
        entry['parts'] = parts
        source.unlink()
    manifest_path.write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')
    marker['manifest_sha256'] = digest(manifest_path)
    marker['dependency_storage'] = 'git-binary-pieces-v1'
    marker_path.write_text(json.dumps(marker, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    (root / '.gitattributes').write_bytes(b'* -text\n')


def prepare(archive: Path, output: Path, *, piece_bytes: int = 48 * 1024 * 1024) -> None:
    if output.exists():
        raise ValueError('Publication directory must be new')
    with zipfile.ZipFile(archive) as package:
        for item in package.infolist():
            relative = PurePosixPath(item.filename)
            if (relative.is_absolute() or len(relative.parts) < 2 or relative.parts[0] != 'MARS-Product'
                    or any(part in {'.', '..', '.git'} for part in relative.parts)
                    or '\\' in item.filename or ':' in item.filename):
                raise ValueError('Invalid package member')
            if item.is_dir():
                continue
            target = output.joinpath(*relative.parts[1:])
            target.parent.mkdir(parents=True, exist_ok=True)
            with package.open(item) as source, target.open('xb') as destination:
                while chunk := source.read(1024 * 1024):
                    destination.write(chunk)
    split_dependencies(output, piece_bytes=piece_bytes)
    if any(path.stat().st_size > piece_bytes for path in output.rglob('*') if path.is_file()):
        raise ValueError('Publication contains an oversized Git blob')


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archive', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    prepare(args.archive, args.output)


if __name__ == '__main__':
    main()
