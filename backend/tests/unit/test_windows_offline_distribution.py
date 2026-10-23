"""Real binary files, ZIP members and Windows reconstruction; no runtime doubles."""
from __future__ import annotations

import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import zipfile

import pytest

ROOT = Path(__file__).resolve().parents[3]
SPEC = importlib.util.spec_from_file_location('windows_distribution', ROOT / 'scripts/release/prepare_windows_distribution.py')
assert SPEC is not None and SPEC.loader is not None
DISTRIBUTION = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(DISTRIBUTION)


def _package(root: Path) -> dict[str, bytes]:
    bundle = root / 'dependencies/offline'
    files = {name: b'integrity fixture, never an executable' for name in (
        'uv.zip', 'node.zip', 'git.zip', 'python.zip', 'zcode.zip', 'npm-cache.zip',
        'vc_redist.x64.exe', 'requirements.windows.txt')}
    files['wheelhouse/large.whl'] = bytes(range(256)) * 3
    records = []
    for name, content in files.items():
        path = bundle / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        records.append({'path': name, 'bytes': len(content), 'sha256': hashlib.sha256(content).hexdigest()})
    manifest = bundle / 'manifest.json'
    manifest.write_text(json.dumps({'schema': 'mars.windows.dependencies.v1', 'files': records}), encoding='utf-8')
    (root / 'WINDOWS-OFFLINE.json').write_text(json.dumps({'schema': 'mars.windows.offline.v1',
        'manifest_sha256': DISTRIBUTION.digest(manifest), 'dependency_directory': 'dependencies/offline'}), encoding='utf-8')
    return files


def test_real_binary_pieces_reconstruct_original_bytes_and_keep_receipt(tmp_path: Path) -> None:
    files = _package(tmp_path)
    DISTRIBUTION.split_dependencies(tmp_path, piece_bytes=64)
    bundle = tmp_path / 'dependencies/offline'
    marker = json.loads((tmp_path / 'WINDOWS-OFFLINE.json').read_text())
    assert marker['manifest_sha256'] == DISTRIBUTION.digest(bundle / 'manifest.json')
    manifest = json.loads((bundle / 'manifest.json').read_text())
    for entry in manifest['files']:
        if 'parts' in entry:
            assert not (bundle / entry['path']).exists()
            data = b''.join((bundle / part['path']).read_bytes() for part in entry['parts'])
            assert all(part['bytes'] <= 64 for part in entry['parts'])
            assert data == files[entry['path']]
        else:
            assert (bundle / entry['path']).read_bytes() == files[entry['path']]


@pytest.mark.skipif(os.name != 'nt', reason='Requires actual Windows PowerShell and .NET IO')
def test_windows_launcher_restores_pieces_and_refuses_corrupt_part(tmp_path: Path) -> None:
    files = _package(tmp_path)
    DISTRIBUTION.split_dependencies(tmp_path, piece_bytes=64)
    driver = tmp_path / 'verify.ps1'
    driver.write_text(
        "param([string]$Source,[string]$Package)\n"
        ". (Join-Path $Source 'deploy/windows-native/Common.ps1')\n"
        ". (Join-Path $Source 'deploy/windows-native/Offline.ps1')\n"
        "$null = Read-MarsOfflineBundle $Package\n", encoding='utf-8')
    command = [shutil.which('powershell.exe') or 'powershell.exe', '-NoProfile', '-File', str(driver),
               '-Source', str(ROOT), '-Package', str(tmp_path)]
    environment = {key: value for key, value in os.environ.items() if key.casefold() != 'psmodulepath'}
    environment['PSModulePath'] = ''
    result = subprocess.run(command, capture_output=True, env=environment, timeout=30)
    assert result.returncode == 0, result.stderr.decode(errors='replace')
    target = tmp_path / 'dependencies/offline/wheelhouse/large.whl'
    assert target.read_bytes() == files['wheelhouse/large.whl']
    target.unlink()
    piece = next((tmp_path / 'dependencies/offline/file-parts').rglob('*.part'))
    piece.write_bytes(b'corrupt piece')
    result = subprocess.run(command, capture_output=True, env=environment, timeout=30)
    assert result.returncode != 0
    assert not target.exists()


def test_publication_refuses_path_escape_and_oversized_piece_setting(tmp_path: Path) -> None:
    archive = tmp_path / 'bad.zip'
    with zipfile.ZipFile(archive, 'w') as package:
        package.writestr('MARS-Product/../escape', b'outside')
    with pytest.raises(ValueError, match='Invalid package member'):
        DISTRIBUTION.prepare(archive, tmp_path / 'publication')
    assert not (tmp_path / 'escape').exists()
    with pytest.raises(ValueError, match='piece size'):
        DISTRIBUTION.split_dependencies(tmp_path, piece_bytes=100 * 1024 * 1024)
