"""Review real native/formatter changes without fabricating tool-write histories."""
from __future__ import annotations

from collections.abc import Iterator
import json
from pathlib import Path
import subprocess
import sys

import pytest
import yaml

from app.bridge.coding_approval import verify_written_code
from app.bridge.completed_code_changes import completed_code_changes
from app.bridge.research_branch import research_branch_scope
from app.harness.project_workspace import open_folder
from app.harness.schema.frontmatter_parser import dumps
from app.harness.tools.git_branch import git, receipt_path
from app.harness.tools.project_repo import load_project_repo
from app.harness.tools.registry import ToolContext, get_registry
from app.settings import reset_settings_cache
from app.storage.artifact_store import ArtifactStore
from app.storage.run_store import RunStore, RunHandle


@pytest.fixture
def workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[tuple[RunHandle, Path]]:
    monkeypatch.setenv('MARS_FOLDER_PROJECTS_REGISTRY', str(tmp_path / 'projects.json'))
    reset_settings_cache()
    project = open_folder(str(tmp_path / 'project'), create=True)
    source = tmp_path / 'source'
    source.mkdir()
    git(source, 'init', '-b', 'main')
    (source / 'main.py').write_text('VALUE = 1\n')
    (source / 'baseline.py').write_text('PRESERVE = True\n')
    git(source, 'add', '.')
    git(source, '-c', 'user.name=Test', '-c', 'user.email=test@localhost', '-c', 'commit.gpgsign=false',
        'commit', '-m', 'baseline')
    (project.metadata_root / 'repo_link.yaml').write_text(yaml.safe_dump({'repo_path': str(source),
        'read_only': True, 'allowed_paths': [''], 'protected_paths': ['baseline.py'], 'ignore_patterns': ['.git/']}))
    run = RunStore(tmp_path / 'runs').create(task='native-workspace', project=project.name)
    try:
        yield run, source
    finally:
        reset_settings_cache()


@pytest.mark.asyncio
async def test_git_net_changes_accept_native_files_and_cleanup_despite_broken_write_chain(
    workspace: tuple[RunHandle, Path],
) -> None:
    run, source = workspace
    with research_branch_scope(run, 'coding'):
        root = load_project_repo(run.project).root
        ctx = ToolContext(run_id=run.run_id, project=run.project, agent='coding', extra={'run_root': str(run.root)})
        result = await get_registry().dispatch('code.write_file', {'path': 'main.py', 'content': 'VALUE = 2\n'}, ctx)
        assert result.ok and result.rollback_ref
        # Actual external process changes source and generates a temporary output.
        subprocess.run([sys.executable, '-c', 'from pathlib import Path; '
            'Path("main.py").write_text("VALUE = 3\\n"); Path("probe.txt").write_text("diagnostic")'],
            cwd=root, check=True, timeout=30)
        (root / 'probe.txt').unlink()
        (root / 'empty.txt').touch()
        (root / '新 文件.py').write_text('NEW = True\n', encoding='utf-8')
        (root / 'result.png').write_bytes(b'\x89PNG\r\n\x1a\n\x00\xff\x80')
        # A damaged old rollback is not usable for restore, but cannot erase
        # independently verified Git differences or require synthetic writes.
        Path(result.rollback_ref).write_text('{}')
        view = completed_code_changes(run, project=run.project)
        assert view['source'] == 'verified_git_workspace' and not view['warnings']
        assert {row['path']: row['change'] for row in view['items']} == {
            'main.py': 'modified', 'empty.txt': 'added', '新 文件.py': 'added', 'result.png': 'added'}
        binary = next(row for row in view['items'] if row['path'] == 'result.png')
        assert binary['binary']
        main = next(row for row in view['items'] if row['path'] == 'main.py')
        detail = completed_code_changes(run, project=run.project, change_id=main['id'])
        assert any(row['kind'] == 'add' and row['text'] == 'VALUE = 3' for row in detail['lines'])
    assert (source / 'main.py').read_text() == 'VALUE = 1\n'
    ledger = json.loads((run.root / 'input/research_changes.json').read_text())
    assert ledger['schema_id'] == 'research.git_changes.v2' and ledger['files'] == {'main.py': None}


def test_native_changes_need_actual_manifest_approval_not_a_tool_ledger(workspace: tuple[RunHandle, Path]) -> None:
    run, source = workspace
    with research_branch_scope(run, 'coding'):
        root = load_project_repo(run.project).root
        (root / 'main.py').write_text('VALUE = 4\n')
        text = dumps({'schema': 'code_spec.v1', 'project': run.project, 'agent': 'coding', 'target_lang': 'python',
            'baseline_compat': {'preserved': True}, 'files_changed': [{'path': 'main.py', 'type': 'modified'}]},
            'Human-authored review of actual native changes; no execution result is asserted.')
        assert verify_written_code(run, text)
        store = ArtifactStore(run)
        store.approve(store.write(text=text))
    # Explicit approval checkpoints actual current code even without tool receipts.
    with research_branch_scope(run, 'execution'):
        assert git(root, 'show', 'HEAD:main.py') == 'VALUE = 4'
    assert (source / 'main.py').read_text() == 'VALUE = 1\n'
    assert not (run.root / 'execution/jobs').exists()


def test_protected_native_changes_are_visible_blockers(workspace: tuple[RunHandle, Path]) -> None:
    run, source = workspace
    with research_branch_scope(run, 'coding'):
        root = load_project_repo(run.project).root
        (root / 'baseline.py').write_text('PRESERVE = False\n')
        view = completed_code_changes(run, project=run.project)
        assert not view['items'] and any('baseline.py' in message for message in view['warnings'])
    assert (source / 'baseline.py').read_text() == 'PRESERVE = True\n'
    assert receipt_path(run.root).exists()
