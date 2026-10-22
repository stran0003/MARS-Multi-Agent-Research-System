"""Real isolated files/processes for Coding-owned preparation; no execution doubles."""
from __future__ import annotations

from contextlib import contextmanager
import json
import os
from pathlib import Path
from typing import Iterator

import pytest
import yaml

from app.bridge.research_branch import research_branch_scope
from app.harness.agent_loop.zcode.workspace import native_path, prepare_native_write, finish_native_writes
from app.harness.agent_loop.executor import LoopInput
from app.harness.agent_loop.policy import AgentLoopPolicy
from app.harness.agent_loop.trace import LoopTrace
from app.harness.agent_loop.zcode.config import ZCodeConfig
from app.harness.agent_loop.zcode.executor import ZCodeLoopExecutor
from app.harness.agent_loop.zcode.gateway import ZCodeGateway, protocol_tool_name
from app.harness.llm.openai_provider import LocalVllmProvider
from app.harness.llm.provider_base import LLMConfig
from app.harness.project_workspace import open_folder
from app.harness.tools.code import apply_patch_tool, write_file_tool
from app.harness.tools.execution.local_command import LocalCommandJob, _command, command_request, run_local_command
from app.harness.tools.execution.command_preflight import run_command_preflight
from app.harness.tools.execution.prepared_command import prepare_execution_tool, prepared_commands
from app.harness.tools.git_branch import git
from app.harness.tools.project_repo import load_project_repo
from app.harness.tools.registry import ToolContext, get_registry
from app.storage.run_store import RunHandle
from app.settings import reset_settings_cache


@contextmanager
def environment(values: dict[str, str]) -> Iterator[None]:
    saved = {key: os.environ.get(key) for key in values}
    os.environ.update(values)
    reset_settings_cache()
    try:
        yield
    finally:
        for key, value in saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        reset_settings_cache()


@contextmanager
def checkout(tmp: Path) -> Iterator[tuple[ToolContext, Path, Path]]:
    execution = tmp / 'execution.yaml'
    execution.write_text('execution:\n  local_commands: []\n  command_timeout_seconds: 30\n')
    with environment({'MARS_FOLDER_PROJECTS_REGISTRY': str(tmp / 'registry.json'),
                      'MARS_EXECUTION_CONFIG_PATH': str(execution), 'MARS_EXECUTION_BACKEND': 'local_command'}):
        project = open_folder(str(tmp / 'project'), create=True)
        source = project.root / 'source'; source.mkdir()
        (source / 'main.py').write_bytes(b'VALUE = 1\nTAIL = 2\n')
        (source / 'config.yaml').write_text('samples: [1, 2, 4]\n')
        git(source, 'init', '-b', 'baseline'); git(source, 'add', '.')
        git(source, '-c', 'user.name=Test', '-c', 'user.email=test@localhost',
            '-c', 'commit.gpgsign=false', 'commit', '-m', 'Actual arithmetic files')
        (project.metadata_root / 'repo_link.yaml').write_text(yaml.safe_dump({
            'repo_path': str(source), 'read_only': True, 'allowed_paths': ['*']}))
        run_root = project.root / 'runs/test-coding'; run_root.mkdir(parents=True)
        run = RunHandle('test-coding', run_root, project.name, 'actual check', 'coding', '2026-10-23T00:00:00Z')
        with research_branch_scope(run, 'coding'):
            yield ToolContext(run.run_id, project.name, 'coding', extra={'run_root': str(run_root)}), load_project_repo(project.name).root, source


@pytest.mark.asyncio
async def test_patch_recounts_short_context_missing_newline_and_local_patch_file(tmp_path: Path) -> None:
    with checkout(tmp_path) as (ctx, root, source):
        # Model supplied wrong counts and omitted the final newline; no source text is invented.
        diff = '--- a/main.py\n+++ b/main.py\n@@ -1,6 +1,7 @@\n VALUE = 1\n+MIDDLE = 3'
        result = await get_registry().dispatch('code.apply_patch', {'diff': diff}, ctx)
        assert result.ok, result.error
        assert (root / 'main.py').read_text() == 'VALUE = 1\nMIDDLE = 3\nTAIL = 2\n'
        from app.bridge.completed_code_changes import completed_code_changes
        actual = completed_code_changes(RunHandle(ctx.run_id, Path(ctx.extra['run_root']), ctx.project,
            'normalized patch', 'coding', '2026-10-23T00:00:00Z'), project=ctx.project)
        assert not actual['warnings'] and actual['items'][0]['change'] == 'modified'
        patch = '--- a/main.py\n+++ b/main.py\n@@ -1 +1 @@\n-VALUE = 1\n+VALUE = 4\n'
        assert (await write_file_tool({'path': 'change.diff', 'content': patch}, ctx)).ok
        assert (await apply_patch_tool({'patch_path': 'change.diff'}, ctx)).ok
        before = (root / 'main.py').read_bytes()
        denied = await apply_patch_tool({'diff': patch.replace('VALUE = 1', 'MISSING = 9')}, ctx)
        assert not denied.ok and (root / 'main.py').read_bytes() == before
        assert (source / 'main.py').read_text() == 'VALUE = 1\nTAIL = 2\n'


@pytest.mark.asyncio
async def test_cleanup_is_allowed_and_native_write_has_real_receipt(tmp_path: Path) -> None:
    with checkout(tmp_path) as (ctx, root, source):
        pending: dict = {}
        args = {'file_path': str(root / 'main.py'), 'old_string': '1', 'new_string': '3'}
        prepare_native_write(ctx, 'Edit', args, pending)
        # This exercises filesystem accounting, not a simulated ZCode execution.
        (root / 'main.py').write_text('VALUE = 3\nTAIL = 2\n')
        receipts = finish_native_writes(ctx, pending)
        assert receipts[0]['path'] == 'main.py' and receipts[0]['rollback_ref']
        from app.bridge.completed_code_changes import completed_code_changes
        run = RunHandle(ctx.run_id, Path(ctx.extra['run_root']), ctx.project, 'write accounting', 'coding', '2026-10-23T00:00:00Z')
        actual = completed_code_changes(run, project=ctx.project)
        assert actual['write_records'] == 1 and not actual['warnings']
        assert [(item['path'], item['change']) for item in actual['items']] == [('main.py', 'modified')]
        # A later identical MARS write must not erase the earlier native edit.
        assert (await get_registry().dispatch('code.write_file', {'path': 'main.py', 'content': (root / 'main.py').read_bytes().decode()}, ctx)).ok
        actual = completed_code_changes(run, project=ctx.project)
        assert not actual['warnings'] and actual['items'][0]['change'] == 'modified'
        with pytest.raises(ValueError):
            native_path(ctx, 'Write', {'file_path': str(source / 'main.py')})
        result = await get_registry().dispatch('code.delete_file', {'path': 'main.py'}, ctx)
        assert result.ok and result.rollback_ref and not (root / 'main.py').exists()
        assert (source / 'main.py').exists()


@pytest.mark.asyncio
async def test_no_global_registration_preflight_then_real_arithmetic_process(tmp_path: Path) -> None:
    with checkout(tmp_path) as (ctx, root, source):
        adapter = '''import os,json,pathlib,yaml
r=json.loads(pathlib.Path(os.environ['MARS_JOB_REQUEST']).read_text())
cfg=yaml.safe_load((pathlib.Path(os.environ['MARS_CODE_ROOT'])/r['config']['config_path']).read_text())
values=cfg['samples']
assert all(isinstance(x,int) for x in values)
base={k:r[k] for k in ('invocation_id','run_id','experiment_id')}
if os.environ.get('MARS_VALIDATE_ONLY')=='1':
    out=dict(base,schema='local_command_validation.v1',status='ready',checks=[{'name':'integer samples','ready':True}])
else:
    total=sum(values)
    pathlib.Path('measured.json').write_text(json.dumps({'values':values,'sum':total}))
    out=dict(base,schema='local_command_result.v1',status='completed',metrics={'sum':total},evidence_paths=['measured.json'])
pathlib.Path(os.environ['MARS_RESULT_PATH']).write_text(json.dumps(out))
'''
        assert (await write_file_tool({'path': 'job.py', 'content': adapter}, ctx)).ok
        prepared = await get_registry().dispatch('code.prepare_execution', {'entrypoint': 'job.py', 'config_path': 'config.yaml', 'timeout_seconds': 7200}, ctx)
        assert prepared.ok, prepared.error
        config = {**prepared.output, 'seed': 42, 'budget_steps': 1}
        run_root = Path(ctx.extra['run_root'])
        job = LocalCommandJob(ctx.run_id, 'sum', ctx.project, run_root, config=config, command_id=config['command_id'])
        assert Path(_command(job, 'execution.simulation_runner')[0][-1]) == root / 'job.py'
        assert _command(job, 'execution.simulation_runner')[2] == 7200
        actual = run_command_preflight(job, 'actual-current-input')
        assert actual['status'] == 'passed', actual
        result = await run_local_command(job)
        assert result.status == 'completed' and result.metrics['sum'] == 7
        assert not prepared_commands(run_root / 'other', ctx.project, 'other')
        with pytest.raises(ValueError, match='another task'):
            prepared_commands(run_root, ctx.project, 'other')
        selected = source.parent / 'uploaded.json'; selected.write_text('[2,3,5]')
        (run_root / 'input').mkdir(exist_ok=True)
        (run_root / 'input/selected_data_source.json').write_text(json.dumps({'project': ctx.project, 'stored_path': str(selected)}))
        job.config['data_path'] = 'missing_old_sample.mat'
        assert command_request(job, 'binding-check', run_root)['config']['data_path'] == str(selected)


@pytest.mark.asyncio
async def test_native_path_error_is_actual_tool_feedback_and_loop_stays_running(tmp_path: Path) -> None:
    with checkout(tmp_path) as (ctx, root, source):
        async def validate(text: str, history: list[dict]) -> list[str]:
            raise AssertionError('This test does not submit model candidates')

        request = LoopInput(messages=[], provider=LocalVllmProvider(base_url='http://127.0.0.1:1'),
            config=LLMConfig('local_vllm', 'unavailable'), registry=get_registry(), tool_context=ctx,
            tools=(), policy=AgentLoopPolicy(), trace_root=Path(ctx.extra['run_root']) / 'trace', validate=validate)
        config = ZCodeConfig.load()
        state = ZCodeLoopExecutor(config)._state(request, 'file-boundary')
        gateway = ZCodeGateway(request, config, 'local-test', state, LoopTrace(request.trace_root, 'full'))
        # Pure validation of a supplied tool-call envelope; no provider call or execution is simulated.
        call = {'id': 'bad-path', 'function': {'name': 'Write',
            'arguments': json.dumps({'file_path': str(source / 'main.py'), 'content': 'wrong'})}}
        gateway.prepare_native_calls({'choices': [{'message': {'tool_calls': [call]}}]})
        assert call['function']['name'] == protocol_tool_name('mars_file_feedback')
        actual = await gateway.call_tool('mars_file_feedback', {'call_id': 'bad-path'})
        assert actual['isError'] and not json.loads(actual['content'][0]['text'])['executed']
        assert state['status'] == 'running' and state['counts']['model_responses'] == 0
        assert (source / 'main.py').read_text() == 'VALUE = 1\nTAIL = 2\n'
        permission = await gateway.native_permission({'toolName': 'Edit',
            'input': {'file_path': str(root / 'main.py'), 'old_string': '1', 'new_string': '2'}})
        assert permission['decision'] == 'allow'
        await request.provider.close()
