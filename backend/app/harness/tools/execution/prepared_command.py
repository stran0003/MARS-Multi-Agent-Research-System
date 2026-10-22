"""Run-local Python launch records prepared by Coding, never global registrations."""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Any

import yaml

from app.harness.persistence import atomic_write_json
from app.harness.tools.git_branch import current_git_branch
from app.harness.tools.project_repo import load_project_repo, resolve_allowed_path
from app.harness.tools.registry import ToolContext, ToolResult
from app.harness.tools.config import load_execution_config


def prepared_commands(run_root: Path, project: str, run_id: str) -> list[dict[str, Any]]:
    path = run_root / 'coding/prepared_commands.json'
    if not path.is_file():
        return []
    value = json.loads(path.read_text(encoding='utf-8'))
    if value.get('project') != project or value.get('run_id') != run_id:
        raise ValueError('Prepared execution belongs to another task')
    rows = value.get('commands')
    if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
        raise ValueError('Invalid prepared command records')
    return rows


async def prepare_execution_tool(args: dict[str, Any], ctx: ToolContext) -> ToolResult:
    """Record a real adapter; validation and formal training use the existing runner."""
    try:
        branch = current_git_branch(ctx.project, ctx.run_id)
        if branch is None or not branch.source_repo_path:
            raise ValueError('Execution preparation requires this run\'s isolated research checkout')
        repo = load_project_repo(ctx.project)
        entry = resolve_allowed_path(repo, str(args['entrypoint']), require_exists=True)
        if entry.suffix != '.py' or not entry.is_file():
            raise ValueError('Prepare an actual Python adapter in the research checkout')
        compile(entry.read_text(encoding='utf-8-sig'), str(entry), 'exec')
        config = resolve_allowed_path(repo, str(args['config_path']), require_exists=True)
        if not config.is_file() or not isinstance(yaml.safe_load(config.read_text(encoding='utf-8')), dict):
            raise ValueError('config_path must contain a real YAML configuration object')
        entry_name, config_name = (path.relative_to(repo.root).as_posix() for path in (entry, config))
        root = Path(str(ctx.extra['run_root'])).resolve(strict=True)
        key = hashlib.sha256(f'{ctx.project}/{ctx.run_id}/{entry_name}/{config_name}'.encode()).hexdigest()[:20]
        command_id = 'prepared_' + key
        policy = load_execution_config()['execution']
        timeout = float(args.get('timeout_seconds', policy.get('prepared_command_timeout_seconds', 86400)))
        if not math.isfinite(timeout) or timeout <= 0:
            raise ValueError('Training timeout must be positive and finite')
        record = {'id': command_id, 'label': 'Coding prepared research adapter',
            'argv': ['python', '{code_root}/' + entry_name],
            'timeout_seconds': timeout,
            'project_ids': [ctx.project], 'entrypoints': [entry_name], 'config_paths': [config_name],
            'consumes_data_path': True, 'required_metrics': args.get('required_metrics', []),
            'validation': {'environment': {'MARS_VALIDATE_ONLY': '1'}, 'timeout_seconds': 60}}
        rows = [row for row in prepared_commands(root, ctx.project, ctx.run_id) if row['id'] != command_id]
        atomic_write_json(root / 'coding/prepared_commands.json', {'schema': 'prepared_commands.v1',
            'project': ctx.project, 'run_id': ctx.run_id, 'commands': [*rows, record]})
        return ToolResult(ok=True, output={'command_id': command_id, 'entrypoint': entry_name,
            'config_path': config_name, 'timeout_seconds': timeout, 'training_started': False,
            'instruction': 'Use this command_id in execution_jobs. MARS will run the actual no-training preflight; fix its feedback before delivery. This receipt is not training success.'})
    except (OSError, ValueError, KeyError, SyntaxError) as exc:
        return ToolResult(ok=False, error=str(exc))
