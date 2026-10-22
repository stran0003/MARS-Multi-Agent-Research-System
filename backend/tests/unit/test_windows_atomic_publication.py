"""Real Windows handles and real filesystem replacements; no OS-call stubs."""
from __future__ import annotations

import os
import hashlib
from pathlib import Path
import threading
import time

import pytest

from app.harness.persistence import atomic_write_text, replace_complete_file, rename_path


def test_atomic_unicode_write_preserves_exact_bytes(tmp_path: Path) -> None:
    target = tmp_path / "研究代码" / "训练.py"
    atomic_write_text(target, "# 中文\r\nprint('你好')\r\n")
    assert target.read_bytes() == "# 中文\r\nprint('你好')\r\n".encode()
    atomic_write_text(target, "# 第二版\n")
    assert target.read_bytes() == "# 第二版\n".encode()
    assert not list(target.parent.glob("*.tmp"))


def test_bound_code_and_archive_reads_preserve_crlf_and_binary_bytes(tmp_path: Path) -> None:
    from app.harness.discovery.code_materialization import _sha256_file, _read_regular_file
    from app.execution.adapters.process import _copy_bound_regular_file
    from app.bridge.results_export import _bounded_file
    # CRLF, CTRL-Z and NUL must not be translated by the Windows CRT.
    payload = b"PK\r\n\x1a\x00\xff\n"
    source, destination = tmp_path / "archive.zip", tmp_path / "copied.zip"
    source.write_bytes(payload)
    expected = "sha256:" + hashlib.sha256(payload).hexdigest()
    assert _sha256_file(source) == expected
    assert _read_regular_file(source, label="archive", max_bytes=100) == payload
    assert _bounded_file(source, 100) == payload
    _copy_bound_regular_file(source, destination, label="archive", expected_sha256=expected,
                             expected_size=len(payload), max_bytes=100)
    assert destination.read_bytes() == payload


@pytest.mark.skipif(os.name != "nt", reason="requires actual Windows file-sharing semantics")
def test_reader_temporarily_preventing_replace_can_finish(tmp_path: Path) -> None:
    from app.harness.windows_read import file_descriptor
    target = tmp_path / "中文.py"
    target.write_bytes(b"original")
    started = threading.Event()
    failures: list[Exception] = []

    def write() -> None:
        started.set()
        try:
            atomic_write_text(target, "更新后\n")
        except Exception as exc:
            failures.append(exc)

    with file_descriptor(tmp_path, target.name) as descriptor:
        worker = threading.Thread(target=write)
        worker.start()
        assert started.wait(5)
        time.sleep(0.25)
        assert worker.is_alive(), "writer should still wait on the actual reader lock"
        assert os.read(descriptor, 20) == b"original"
    worker.join(timeout=8)
    assert not worker.is_alive() and not failures
    assert target.read_text(encoding="utf-8") == "更新后\n"
    assert not list(tmp_path.glob("*.tmp"))


@pytest.mark.skipif(os.name != "nt", reason="requires actual Windows file-sharing semantics")
def test_permanent_lock_never_moves_original_away(tmp_path: Path) -> None:
    from app.harness.windows_read import file_descriptor
    target, prepared = tmp_path / "target", tmp_path / "prepared"
    target.write_bytes(b"original")
    prepared.write_bytes(b"replacement")
    with file_descriptor(tmp_path, target.name):
        with pytest.raises(OSError) as error:
            replace_complete_file(prepared, target, timeout=0.1)
        assert error.value.winerror in {5, 32, 33}
        assert target.read_bytes() == b"original"
        assert prepared.read_bytes() == b"replacement"
    replace_complete_file(prepared, target)
    assert target.read_bytes() == b"replacement" and not prepared.exists()


@pytest.mark.skipif(os.name != "nt", reason="requires actual Windows directory junctions")
def test_materialization_rejects_junctions_before_touching_outside_files(tmp_path: Path) -> None:
    import _winapi
    from app.harness.discovery.code_materialization import (
        _assert_no_symlink_components, _fix_published_modes, _inventory_workspace, MaterializationError,
    )
    root, outside = tmp_path / "workspace", tmp_path / "outside"
    root.mkdir()
    outside.mkdir()
    (root / "main.py").write_bytes(b"PASS = True\n")
    original = outside / "private.py"
    original.write_bytes(b"PRIVATE\n")
    junction = root / "linked"
    getattr(_winapi, "CreateJunction")(str(outside), str(junction))
    try:
        with pytest.raises(MaterializationError, match="symlink"):
            _assert_no_symlink_components(junction / "private.py", label="candidate")
        with pytest.raises(MaterializationError, match="symlink"):
            _inventory_workspace(root)
        with pytest.raises(MaterializationError, match="symlink"):
            _fix_published_modes(root)
        assert original.read_bytes() == b"PRIVATE\n"
    finally:
        junction.rmdir()


@pytest.mark.skipif(os.name != "nt", reason="requires actual Windows file-sharing semantics")
def test_renaming_a_locked_source_preserves_it_until_released(tmp_path: Path) -> None:
    from app.harness.windows_read import file_descriptor
    source, destination = tmp_path / "target.py", tmp_path / "temporary.py"
    source.write_bytes(b"original")
    with file_descriptor(tmp_path, source.name):
        with pytest.raises(OSError):
            rename_path(source, destination, timeout=0.1)
        assert source.read_bytes() == b"original" and not destination.exists()
    rename_path(source, destination)
    assert not source.exists() and destination.read_bytes() == b"original"
