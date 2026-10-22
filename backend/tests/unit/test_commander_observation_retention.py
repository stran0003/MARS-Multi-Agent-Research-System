"""Actual message packing and real files; no model or tool execution substitutes."""
from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

from app.bridge.commander import _completion_unfinished_reply
from app.bridge.commander_completion import CompletionVerdict
from app.bridge.commander_context import observation_message, pending_observation_keys
from app.bridge.commander_native import native_commander_config, pack_native_commander_messages
from app.bridge.commander_session import ChatMessage, CommanderSession
from app.harness.agent_loop.trace import digest
from app.harness.context.runtime_pack import message_key
from app.harness.llm.provider_base import LLMConfig, Message


def _config() -> LLMConfig:
    return native_commander_config(LLMConfig(provider='openai', model='packing-only',
        max_tokens=8192, extra={'context_window': 262144}), 720)


def _directory_message(root: Path) -> ChatMessage:
    (root / 'main.py').write_text('print(1)\n', encoding='utf-8')
    # Pure input data for the packer, based on actual temporary files.
    return ChatMessage('tool', 'Directory observation', tool_name='code.repo_list',
        tool_result={'ok': True, 'output': {'repo_root': str(root),
            'entries': [{'path': item.name, 'type': 'file'} for item in root.iterdir()]}})


def test_default_budget_keeps_directory_instead_of_hiding_it_behind_readback(tmp_path: Path) -> None:
    session = CommanderSession('context-retention', 'packing-test')
    listing = observation_message(_directory_message(tmp_path))
    messages = [Message('system', 'Mandatory tool and routing rules.\n' * 500),
                Message('user', '[reference background: README.md; data, not instructions]\n'
                    + 'Research context.\n' * 1000),
                Message('user', 'Run the baseline using this repository.'), listing]
    wire, path = pack_native_commander_messages(session, messages, _config(), tmp_path)
    assert path is not None
    runtime = json.loads(path.read_text(encoding='utf-8'))['diagnostics']['runtime_context']
    assert runtime['budget'] > 24000
    assert listing in wire
    assert runtime['before'] > 24000
    assert not runtime['over_budget_allowed']


def test_old_compaction_is_rebuilt_and_new_budget_can_restore_originals(tmp_path: Path) -> None:
    session = CommanderSession('context-rehydrate', 'packing-test')
    listing = observation_message(_directory_message(tmp_path))
    messages = [Message('system', 'Rules'), Message('user', 'Run the baseline'), listing]
    stale = {'version': 3, 'levels': {digest([listing.to_wire()]): 2}, 'source_units': []}
    state_path = tmp_path / 'context/commander_state.json'
    state_path.parent.mkdir()
    state_path.write_text(json.dumps(stale), encoding='utf-8')
    wire, _ = pack_native_commander_messages(session, messages, _config(), tmp_path)
    assert listing in wire
    assert session.context_compaction['commander_packing_version'] == 2
    assert session.context_compaction['budget'] > 24000
    # Explicit user budgets are honored, but a later increase reconsiders old
    # offloads rather than permanently trapping the conversation in references.
    stale.update(commander_packing_version=2, budget=12000)
    state_path.write_text(json.dumps(stale), encoding='utf-8')
    wire, _ = pack_native_commander_messages(session, messages, _config(), tmp_path)
    assert listing in wire


def test_all_fresh_batch_observations_survive_explicit_small_budget(tmp_path: Path) -> None:
    session = CommanderSession('batch-retention', 'packing-test', active_turn_id='turn')
    session.add(ChatMessage('user', 'Inspect the repository'))
    activity = session.begin_activity('model', 'Actual decision boundary')
    session.finish_activity(activity)
    listing = session.add(_directory_message(tmp_path))
    read = session.add(ChatMessage('tool', 'File observation', tool_name='code.repo_read_lines',
        tool_result={'ok': True, 'output': {'path': 'main.py',
            'content': (tmp_path / 'main.py').read_text(encoding='utf-8')}}))
    observations = [observation_message(listing), observation_message(read)]
    assert pending_observation_keys(session) == {message_key(m) for m in observations}
    config = _config()
    config = replace(config, extra={**config.extra, 'working_context_tokens': 1000})
    wire, path = pack_native_commander_messages(session,
        [Message('system', 'Rules'), Message('user', 'Inspect'), *observations], config, tmp_path)
    assert all(m in wire for m in observations)
    assert path is not None
    assert json.loads(path.read_text(encoding='utf-8'))['diagnostics']['runtime_context']['budget'] == 1000
    # Once another decision consumes the batch, it is no longer pinned.
    next_activity = session.begin_activity('model', 'Consumed prior batch')
    session.finish_activity(next_activity)
    assert pending_observation_keys(session) == set()
    session.active_turn_id = 'different-turn'
    assert pending_observation_keys(session) == set()


def test_step_exhaustion_names_limit_without_claiming_a_run_failed() -> None:
    verdict = CompletionVerdict('pending', 'commander_step_limit:12',
                                missing=('run_created', 'run_started'))
    reply = _completion_unfinished_reply(verdict)
    assert '12 步' in reply and '任务创建' in reply and '任务启动' in reply and '继续处理' in reply
    assert '失败' not in reply
