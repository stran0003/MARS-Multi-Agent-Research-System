"""Recognize a cancelled, cleaned-up Coding check without replaying it."""
from __future__ import annotations

from datetime import datetime
import json
from pathlib import Path

from app.harness.agent_loop.trace import digest
from app.harness.runtime.project_scope import safe_scope_path
from app.storage.run_store import RunHandle


def cancelled_check_receipt(run: RunHandle, invocation_id: str) -> bool:
    """A registry cancellation receipt is a known failure, never check success.

    The registry records cancellation only after subprocess cleanup unwinds.
    Permit a fresh Coding invocation to inspect its preserved files. Unknown
    mutations and checks without an exact terminal receipt remain blocked.
    """
    events = safe_scope_path(run.root, f'agent_traces/coding/{invocation_id}/events.jsonl', must_exist=True)
    dispatch = None
    for line in events.read_text(encoding='utf-8').splitlines():
        row = json.loads(line)
        if row.get('kind') == 'tool_dispatch':
            dispatch = row
    if dispatch is None or dispatch.get('tool') not in {'code.test_runner', 'code.lint'}:
        return False
    started = datetime.fromisoformat(dispatch['time'])
    matches = []
    for path in (run.root / 'coding/tool_applications').glob('*.json'):
        if path.name.startswith('rollback_'):
            continue
        record = json.loads(safe_scope_path(run.root, path.relative_to(run.root).as_posix(), must_exist=True).read_text(encoding='utf-8'))
        if (record.get('run_id') != run.run_id or record.get('project') != run.project
                or record.get('agent') != 'coding' or record.get('tool') != dispatch['tool']
                or record.get('status') != 'cancelled' or record.get('call_id') != path.stem):
            continue
        if (datetime.fromisoformat(record['started_at']) >= started
                and datetime.fromisoformat(record['ended_at']) >= datetime.fromisoformat(record['started_at'])
                and digest({'tool': record['tool'], 'args': record['args']}) == dispatch.get('visible_sha256')):
            matches.append(record)
    return len(matches) == 1
