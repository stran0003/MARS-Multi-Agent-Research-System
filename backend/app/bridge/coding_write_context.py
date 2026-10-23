"""Read actual task changes before asking for another code draft."""
from __future__ import annotations

import json

from app.bridge.completed_code_changes import completed_code_changes
from app.storage.run_store import RunHandle


def coding_write_context(run: RunHandle) -> str | None:
    """Supply complete bounded evidence, never an inferred or truncated manifest."""
    instruction = (
        '按本任务 Git 起始版本到当前工作目录的实际净改动填写 files_changed；'
        '前轮保留的改动也必须列出，不能只列本轮新写文件。'
        'unchanged 属于复用，不声明新增。该清单不是批准或仿真成功。'
        '存在 warnings 或 complete=false 时证据不完整、不可声称核验通过；'
        '工具记录用于审计与回滚，不要求每次中间写入形成连续哈希链。'
        '不要为匹配清单而重写相同内容或编造改动。'
    )
    try:
        # Git-backed projects read the actual net diff, not a replay of receipts.
        view = completed_code_changes(run, project=run.project)
        if not view['write_records'] and not view['items'] and not view['warnings']:
            return None
        warnings = list(view['warnings'])
        payload = {
            'schema': 'coding_written_code_manifest.v1', 'run_id': run.run_id,
            'project': run.project, 'complete': not warnings, 'verified': not warnings,
            'files_changed': [{'path': item['path'], 'type': item['change']} for item in view['items']],
            'unchanged': view['unchanged'], 'warnings': warnings,
            'write_records': view['write_records'], 'instruction': instruction,
            'source': view.get('source', 'verified_tool_writes'),
        }
    except (OSError, ValueError, KeyError, TypeError) as exc:
        # Exceeding the existing evidence budget must not silently advertise a
        # partial list or turn a readable context into a new workflow hard stop.
        payload = {
            'schema': 'coding_written_code_manifest.v1', 'run_id': run.run_id,
            'project': run.project, 'complete': False, 'verified': False,
            'warnings': [str(exc)], 'instruction': instruction,
        }
    return json.dumps(payload, ensure_ascii=False, separators=(',', ':'))
