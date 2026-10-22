"""Real ZCode -> real CPU job failure -> same-session repair -> real measured result.

Uses a disposable arithmetic project and a host adapter with a compatibility
entrypoint. No provider, tools, approvals or process outcomes are mocked. Explicit
auto approval applies only to this script's newly created synthetic test project.
"""
from __future__ import annotations

import argparse
import asyncio
from copy import deepcopy
from dataclasses import replace
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys

from dotenv import dotenv_values
from loguru import logger
import yaml

from app.agents.coding.agent import CodingAgent
from app.agents.execution.agent import ExecutionAgent
from app.agents.writing.agent import WritingAgent
from app.bridge.agent_registry import AgentRegistry
from app.bridge.orchestrator import Orchestrator, RunRequest
from app.harness.agent_loop.trace import atomic_json, audit_trace
from app.harness.llm.model_registry import get_agent_config
from app.harness.project_workspace import open_folder
from app.harness.runtime.state_machine import NodeState
from app.harness.schema.frontmatter_parser import parse as parse_frontmatter
from app.harness.reporting.source_refs import report_source_errors
from app.harness.tools.git_branch import git
from app.settings import repo_root, reset_settings_cache
from app.storage.run_store import RunStore
from app.reporting import read_latest_report_bundle


async def validate(args: argparse.Namespace) -> Path:
    root = repo_root() / 'runs' / (datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S') + '_coupled_validation')
    root.mkdir(parents=True)
    supplied = yaml.safe_load(Path(args.model_config).read_text(encoding='utf-8'))['coding']['model']
    key_name = supplied.get('api_key_env', '')
    if args.env_file:
        secret = dotenv_values(args.env_file).get(key_name)
        if secret:
            os.environ[key_name] = secret
    zcode = yaml.safe_load((repo_root() / 'configs/zcode.yaml').read_text(encoding='utf-8'))
    zcode['command'] = args.zcode_command
    runtime = root / 'zcode.yaml'
    runtime.write_text(yaml.safe_dump(zcode), encoding='utf-8')
    os.environ.update(MARS_CODING_BACKEND='zcode', MARS_ZCODE_CONFIG_PATH=str(runtime),
        MARS_EXECUTION_BACKEND='local_command', MARS_EXECUTION_DEVICE='cpu',
        MARS_FOLDER_PROJECTS_REGISTRY=str(root / 'registry.json'),
        PYTHONUTF8='1', PATH=str(Path(sys.executable).parent) + os.pathsep + os.environ.get('PATH', ''))
    reset_settings_cache()
    project = open_folder(str(root / 'project'), create=True)
    source = root / 'source'
    source.mkdir()
    (source / 'tests').mkdir()
    (source / '.gitignore').write_text('__pycache__/\n.pytest_cache/\n', encoding='utf-8', newline='')
    (source / 'main.py').write_text('def add(a, b):\n    return a - b\n', encoding='utf-8', newline='')
    (source / 'tests/test_main.py').write_text('from main import add\n\ndef test_add():\n'
        '    assert add(2, 3) == 5\n    assert add(-2, 3) == 1\n', encoding='utf-8', newline='')
    git(source, 'init', '-b', 'baseline')
    git(source, 'add', '.')
    git(source, '-c', 'user.name=MARS validation', '-c', 'user.email=mars@localhost',
        '-c', 'commit.gpgsign=false', 'commit', '-m', 'Synthetic arithmetic baseline')
    baseline = git(source, 'rev-parse', 'HEAD')
    (project.metadata_root / 'repo_link.yaml').write_text(yaml.safe_dump({'repo_path': str(source),
        'read_only': True, 'allowed_paths': ['main.py', 'tests/'], 'protected_paths': ['tests/'],
        'ignore_patterns': ['.git/', '.env*']}), encoding='utf-8')
    adapter = root / 'host_adapter.py'
    adapter.write_text("""import importlib.util,json,os,pathlib
request=json.loads(pathlib.Path(os.environ['MARS_JOB_REQUEST']).read_text(encoding='utf-8'))
entry=pathlib.Path(os.environ['MARS_CODE_ROOT'])/'main.py'
spec=importlib.util.spec_from_file_location('measured_module',entry)
module=importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
pairs=[(i,i+1) for i in range(20)]
observations=[module.sum_pair(a,b) for a,b in pairs]
mse=sum((observed-(a+b))**2 for observed,(a,b) in zip(observations,pairs))/len(pairs)
pathlib.Path('measurements.json').write_text(json.dumps({'pairs':pairs,'observations':observations}),encoding='utf-8')
steps=[{'step':i+1,'expected':a+b,'observed':observed,'squared_error':(observed-a-b)**2}
       for i,((a,b),observed) in enumerate(zip(pairs,observations))]
pathlib.Path('summary.json').write_text(json.dumps({'mse':mse,'count':len(steps)}),encoding='utf-8')
pathlib.Path('steps.jsonl').write_text(''.join(json.dumps(row)+'\\n' for row in steps),encoding='utf-8')
result={'schema':'local_command_result.v1','status':'completed',
 'invocation_id':request['invocation_id'],'run_id':request['run_id'],'experiment_id':request['experiment_id'],
 'metrics':{'mse':mse},'evidence_paths':['measurements.json','summary.json','steps.jsonl']}
pathlib.Path(os.environ['MARS_RESULT_PATH']).write_text(json.dumps(result),encoding='utf-8')
""", encoding='utf-8', newline='')
    execution = yaml.safe_load((repo_root() / 'configs/execution.yaml').read_text(encoding='utf-8'))
    argv = [sys.executable, str(adapter)]
    execution['execution']['local_commands'] = [{'id': 'arithmetic', 'argv': argv,
        'project_ids': [project.name], 'entrypoints': ['main.py'], 'required_metrics': ['mse']}]
    execution['code_checks'] = {'test': {'enabled': True, 'commands': [{'id': 'repo-tests',
        'argv': [sys.executable, '-m', 'pytest', '-q', 'tests'], 'label': 'Real arithmetic tests'}]}}
    path = root / 'execution.yaml'
    path.write_text(yaml.safe_dump(execution), encoding='utf-8')
    tools = yaml.safe_load((repo_root() / 'configs/tools.yaml').read_text(encoding='utf-8'))
    for name in ('execution.simulation_runner', 'execution.batch_runner'):
        tools['tools'][name]['command_allowlist'] = [argv]
    tools['tools']['code.test_runner']['command_allowlist'] = [
        [sys.executable, '-m', 'pytest', '-q', 'tests']]
    tool_path = root / 'tools.yaml'
    tool_path.write_text(yaml.safe_dump(tools), encoding='utf-8')
    os.environ.update(MARS_EXECUTION_CONFIG_PATH=str(path), MARS_TOOLS_CONFIG_PATH=str(tool_path))
    reset_settings_cache()
    original = get_agent_config('coding')
    raw = deepcopy(dict(original.raw))
    raw['loop'].update(completion_driven=False, max_model_calls=20, max_tool_steps=30)
    raw['model'] = {**supplied, 'context_window': 128000, 'max_tokens': 16384}
    selected = replace(original, model_provider=supplied['provider'], model_name=supplied['model'],
        max_tokens=16384, api_key_env=key_name, base_url=supplied.get('base_url', ''),
        raw=raw, thinking_enabled=supplied.get('thinking', {}).get('enabled', False),
        reasoning_effort=supplied.get('reasoning_effort'), request_timeout_seconds=180, max_retries=0)
    registry = AgentRegistry()
    registry.register('coding', CodingAgent(agent_config=selected))
    registry.register('execution', ExecutionAgent())
    if args.with_report:
        writing = get_agent_config('writing')
        writing_raw = deepcopy(dict(writing.raw))
        writing_raw['model'] = deepcopy(raw['model'])
        writing_raw.setdefault('loop', {}).update(max_model_calls=20, max_tool_steps=30)
        writing_raw.setdefault('debate', {})['enabled'] = False
        registry.register('writing', WritingAgent(agent_config=replace(writing,
            model_provider=selected.model_provider, model_name=selected.model_name,
            max_tokens=selected.max_tokens, api_key_env=selected.api_key_env,
            base_url=selected.base_url, raw=writing_raw, debate_enabled=False,
            thinking_enabled=selected.thinking_enabled, reasoning_effort=selected.reasoning_effort,
            request_timeout_seconds=180, max_retries=0)))
    orch = Orchestrator(run_store=RunStore(root / 'research'), registry=registry)
    task = ('Fix add(a,b) in main.py to return the correct sum. Preserve tests. Implement add only initially; '
        'do not invent additional compatibility aliases unless a real execution failure requests one. '
        'Read main.py and tests/test_main.py with native Read and fix main.py with native Edit; '
        'run code.test_runner command_id=repo-tests. '
        'Deliver accurate code_spec.v1 and exactly one execution_jobs item named arithmetic_seed42, '
        'config={command_id: arithmetic, entrypoint: main.py, seed: 42, budget_unit: steps, budget_steps: 1}. '
        'There is no external data or configuration file: the host adapter measures actual integer pairs. '
        'Required metric is mse; keep these scientific conditions fixed. MARS will run the real adapter. '
        'On actual execution feedback, add only the required compatibility entry in main.py, preserving add. '
        'Do not create another model, fake metrics or edit the host adapter. '
        'If Writing is enabled, write an evidence-backed report of this CPU arithmetic acceptance only: '
        'read admitted execution materials, explain the real failure and repair, quote measured MSE, '
        'and distinguish this check from PIM training or scientific improvement. '
        'Research and experiment design were intentionally skipped; do not invent those artifacts.')
    session = orch.create_session(RunRequest(task='zcode_coding_execution_acceptance', project=project.name,
        entrypoint='coding', user_request=task, auto_approve=True,
        extra={} if args.with_report else {'stop_after': 'execution'}))
    atomic_json(root / 'validation_started.json', {'run_root': str(session.run.root), 'run_id': session.run.run_id,
        'project': project.name, 'model': selected.model_name, 'runtime': 'official ZCode',
        'approval_scope': 'this isolated synthetic validation only'})
    logger.info('Real coupled validation running: {}', session.run.root)
    try:
        await asyncio.wait_for(orch.run(session.run.run_id), timeout=1800 if args.with_report else 1200)
        states = session.graph.all_states()
        checkpoints = list((session.run.root / 'agent_traces/coding').glob('*/checkpoint.json'))
        saved = [json.loads(p.read_text(encoding='utf-8')) for p in checkpoints]
        passed = [s for s in saved if s['status'] == 'passed']
        assert states.get('execution') == NodeState.FAILED, states
        assert any(k.startswith('execution_attempt_') and v == NodeState.DONE for k, v in states.items()), states
        assert len(passed) >= 2 and len({s['session_id'] for s in passed}) == 1
        assert all(audit_trace(p.parent)['consistent'] for p in checkpoints)
        native_receipts = [json.loads(line) for checkpoint in checkpoints
            for line in (checkpoint.parent / 'events.jsonl').read_text(encoding='utf-8').splitlines()
            if json.loads(line).get('kind') == 'native_write_receipt']
        assert native_receipts, 'No actual native ZCode file change was recorded'
        tool_events = [json.loads(line) for line in
                       (session.run.root / 'events/tool_events.jsonl').read_text(encoding='utf-8').splitlines()]
        assert any(e.get('tool') == 'code.test_runner' and e.get('ok') is True for e in tool_events)
        metrics = json.loads((session.run.root / 'execution/metrics.json').read_text(encoding='utf-8'))
        assert metrics and metrics[0]['metrics']['mse'] == 0
        assert git(source, 'rev-parse', 'baseline') == baseline
        report = session.run.root / 'writing/research_report.approved.md'
        if args.with_report:
            assert states.get('writing') == NodeState.DONE, states
            assert report.is_file(), report
            report_text = report.read_text(encoding='utf-8')
            assert parse_frontmatter(report_text).metadata['schema'] == 'report.v1'
            assert not report_source_errors(session.run.root, report_text)
            bundle = read_latest_report_bundle(session.run)
            assert bundle and bundle['current'] and bundle['metadata']['materials_saved']
            assert not bundle['metadata']['generation_errors']
            pack = json.loads((session.run.root / bundle['metadata']['data_pack']).read_text(encoding='utf-8'))
            assert any(curve['points_count'] == 20 for curve in pack['curves']), pack['curves']
        atomic_json(root / 'acceptance.json', {'status': 'passed', 'model': selected.model_name,
            'run_id': session.run.run_id, 'states': {k:v.value for k,v in states.items()}, 'metrics': metrics,
            'session_id': passed[0]['session_id'], 'coding_turns': len(passed), 'baseline_preserved': True,
            'native_write_receipts': len(native_receipts),
            'report': str(report) if args.with_report else None,
            'scope': ('real CPU coding -> failure -> same-session repair -> execution -> writing; '
                      'not PIM training or idea/experiment research acceptance') if args.with_report else
                     'real CPU arithmetic coupling; not PIM training or full research/report acceptance'})
        return root
    finally:
        await orch.shutdown_owned_runs()
        from app.bridge.tensorboard_service import shutdown_tensorboard
        await shutdown_tensorboard()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--model-config', required=True)
    parser.add_argument('--env-file')
    parser.add_argument('--with-report', action='store_true', help='Continue into real Writing and verify its source references')
    parser.add_argument('--zcode-command', nargs='+', required=True)
    result = asyncio.run(validate(parser.parse_args()))
    logger.info('Real coupled acceptance: {}', result / 'acceptance.json')
