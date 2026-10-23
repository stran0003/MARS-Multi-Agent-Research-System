"""Actual net Git changes, independent of intermediate tool-write histories."""
from __future__ import annotations

import os
import re
from typing import Any

import yaml

from app.bridge.code_changes import parse_diff
from app.bridge.git_code_delivery import _repository
from app.harness.runtime.git_runtime import run_git
from app.harness.tools.git_branch import changed_files, git
from app.harness.tools.project_repo import resolve_allowed_path
from app.settings import repo_root
from app.storage.run_store import RunHandle


def workspace_code_changes(run: RunHandle, *, change_id: str | None = None) -> dict[str, Any]:
    """Read real Git differences without staging, committing, or replaying writes.

    Git is the source of change truth. Tool receipts remain audit/rollback
    evidence; their continuity is not a precondition for reviewing source.
    """
    policy = yaml.safe_load((repo_root() / 'configs/code_review.yaml').read_text())['code_review']
    items: list[dict[str, Any]] = []
    warnings: list[str] = []
    total = 0
    with _repository(run) as repo:
        branch = repo.git_branch
        assert branch is not None
        start = branch.initial_commit or branch.baseline_commit
        for path in sorted(changed_files(repo.root, start)):
            try:
                target = resolve_allowed_path(repo, path, for_write=True)
                initial = git(repo.root, 'ls-tree', '-z', start, '--', ':(literal)' + path)
                if initial and initial.split(' ', 1)[0] not in {'100644', '100755'}:
                    raise ValueError('起始版本包含非普通文件')
                options = ('--no-ext-diff', '--no-textconv', '--no-renames', '--binary', '--full-index')
                if initial:
                    result = run_git(('-C', str(repo.root), 'diff', *options, start, '--', ':(literal)' + path))
                else:
                    if not target.is_file():
                        raise ValueError('新增代码文件不存在')
                    result = run_git(('-C', str(repo.root), 'diff', '--no-index', *options,
                                      '--', os.devnull, path), check=False)
                    if result.returncode not in (0, 1):
                        raise ValueError('Git 无法读取当前新增文件差异')
                diff = result.stdout
                total += len(diff.encode('utf-8'))
                if total > int(policy['max_record_bytes']):
                    raise ValueError('当前 Git 差异超过完整核验范围，请分批提交源代码')
                files = parse_diff(diff)
                if len(files) != 1 or files[0]['path'] != path:
                    raise ValueError('Git 差异不能完整对应当前文件')
                item = files[0]
                item['change'] = 'added' if not initial else 'deleted' if not target.exists() else 'modified'
                if 'GIT binary patch' in diff or 'Binary files ' in diff:
                    item['binary'] = True
                lines = item.pop('lines')
                # Native Git blob IDs already version this diff; no extra
                # application hash chain is needed for the UI's stable key.
                index = re.search(r'^index ([0-9a-f]+)\.\.([0-9a-f]+)', diff, re.MULTILINE)
                version = ':'.join(index.groups()) if index else git(repo.root, 'rev-parse', 'HEAD')
                item.update(id=f'workspace:{version}:{path}', status='applied', source='verified_git_workspace',
                            timestamp='', truncated=len(lines) > int(policy['max_preview_lines']))
                if change_id == item['id']:
                    return {**item, 'run_id': run.run_id, 'project': run.project,
                            'lines': lines[:int(policy['max_preview_lines'])]}
                items.append(item)
            except (OSError, ValueError) as exc:
                warnings.append(f'{path} 的实际 Git 差异不可核对：{exc}')
    if change_id is not None:
        raise KeyError('代码差异已变化或不可读取，请刷新后重试')
    return {'run_id': run.run_id, 'project': run.project, 'items': items, 'warnings': warnings,
            'write_records': 0, 'unchanged': [], 'source': 'verified_git_workspace'}
