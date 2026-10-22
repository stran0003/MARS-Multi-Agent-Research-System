"""Official ZCode file tools, bound to the run's writable code checkout."""
from __future__ import annotations

from pathlib import Path
from typing import Any
from dataclasses import asdict
from datetime import datetime, timezone
import json
from uuid import uuid4

from app.harness.tools.code import _snapshot, _write_rollback
from app.harness.tools.git_branch import current_git_branch, record_changed_files
from app.harness.tools.project_repo import load_project_repo, resolve_allowed_path
from app.harness.tools.registry import ToolContext, ToolResult, ToolExecutionRecord, _record_invocation
from app.harness.persistence import atomic_write_json

NATIVE_FILE_TOOLS = ('Read', 'Write', 'Edit', 'Glob', 'Grep')


def native_workspace(ctx: ToolContext) -> Path | None:
    branch = current_git_branch(ctx.project, ctx.run_id)
    return branch.root if branch is not None and branch.source_repo_path else None


def native_path(ctx: ToolContext, name: str, args: dict[str, Any]) -> Path:
    root = native_workspace(ctx)
    if root is None or name not in NATIVE_FILE_TOOLS:
        raise ValueError('Native file tools require an isolated research checkout')
    value = args.get('file_path') if name in {'Read', 'Write', 'Edit'} else args.get('path', str(root))
    if not isinstance(value, str) or not value:
        raise ValueError('A real file/search path is required')
    given = Path(value)
    relative = given.relative_to(root).as_posix() if given.is_absolute() else value
    if relative == '.' and name in {'Glob', 'Grep'}:
        return root
    return resolve_allowed_path(load_project_repo(ctx.project), relative,
        require_exists=False, for_write=name in {'Write', 'Edit'})


def prepare_native_write(ctx: ToolContext, name: str, args: dict[str, Any], pending: dict[str, Any]) -> None:
    target = native_path(ctx, name, args)
    if name not in {'Write', 'Edit'}:
        return
    root = native_workspace(ctx)
    assert root is not None
    relative = target.relative_to(root).as_posix()
    content = args.get('content') if name == 'Write' else args.get('new_string')
    if not isinstance(content, str):
        raise ValueError('Native write content must be text')
    if name == 'Edit':
        old = args.get('old_string')
        if not isinstance(old, str) or not old:
            raise ValueError('Edit requires the current source text; read the file first')
        original = target.read_text(encoding='utf-8')
        if old not in original:
            raise ValueError('Edit source text no longer matches; read the current file and retry')
        content = original.replace(old, content, -1 if args.get('replace_all') else 1)
    from app.harness.evolution import check_evolution_write
    check_evolution_write(root, relative, content)
    from app.harness.gates.baseline_compatibility import static_check
    decision = static_check(project=ctx.project, tool_name='code.write_file',
        args={'path': relative, 'content': content})
    if decision.blocking:
        raise ValueError(decision.reason)
    if relative not in pending:
        before = _snapshot(relative, target)
        ref = _write_rollback(ctx, 'zcode.' + name, [before])
        pending[relative] = {'before_sha256': before.sha256, 'rollback_ref': ref,
                             'tool': 'zcode.' + name, 'started_at': datetime.now(timezone.utc).isoformat()}


def finish_native_writes(ctx: ToolContext, pending: dict[str, Any]) -> list[dict[str, Any]]:
    root = native_workspace(ctx)
    if root is None:
        return []
    receipts = []
    for relative, before in list(pending.items()):
        target = native_path(ctx, 'Write', {'file_path': str(root / relative)})
        after = _snapshot(relative, target)
        if after.sha256 != before['before_sha256']:
            # The shared ledger consumes observed before/after bytes, irrespective
            # of which engine performed the edit. Do not replay native writes.
            snapshot_path = Path(before['rollback_ref'])
            snapshot = json.loads(snapshot_path.read_text(encoding='utf-8'))
            snapshot['after_snapshots'] = [asdict(after)]
            atomic_write_json(snapshot_path, snapshot)
            args = {'path': relative}
            receipt = {'path': relative, 'sha256': after.sha256, **before}
            observed_at = datetime.now(timezone.utc).isoformat()
            result = ToolResult(ok=True, status='success', output=receipt,
                                rollback_ref=before['rollback_ref'])
            _record_invocation(tool_name=before['tool'], args=args, ctx=ctx, result=result,
                record=ToolExecutionRecord(call_id=uuid4().hex, run_id=ctx.run_id,
                    project=ctx.project, agent=ctx.agent, tool=before['tool'], status='success',
                    started_at=before['started_at'], ended_at=observed_at, duration_ms=0,
                    args=args, rollback_ref=before['rollback_ref']))
            record_changed_files(ctx.project, ctx.run_id, [relative])
            receipts.append(receipt)
        del pending[relative]
    return receipts
