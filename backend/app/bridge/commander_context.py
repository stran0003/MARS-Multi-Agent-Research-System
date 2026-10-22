"""Classify bounded source observations separately from expendable tool logs."""
from __future__ import annotations

import json

from app.bridge.commander_session import ChatMessage, CommanderSession
from app.harness.context.runtime_pack import Material, message_key
from app.harness.llm.provider_base import Message


def observation_message(message: ChatMessage) -> Message:
    return Message('user', f'[observation tool={message.tool_name}] '
                   + json.dumps(message.tool_result, ensure_ascii=False))


def pending_observation_keys(session: CommanderSession) -> set[str]:
    """Keep every result of the last model decision until its next decision.

    A parallel/batched list, search and read are all unread observations. Keeping
    only the last result can evict the directory before the model ever sees it.
    This is not a cache: after another decision, older results are compactable.
    """
    completed = next((activity for activity in reversed(session.activities)
                      if activity.kind == 'model' and activity.status == 'completed'
                      and activity.turn_id == session.active_turn_id and activity.ended_at), None)
    if completed is None or session.active_turn_id is None:
        return set()
    return {message_key(observation_message(message)) for message in session.context_messages()
            if message.role == 'tool' and message.turn_id == session.active_turn_id
            and message.timestamp >= str(completed.ended_at)}


def commander_materials(messages: list[Message], *, pending: set[str] | None = None) -> dict[str, Material]:
    materials: dict[str, Material] = {}
    for message in messages:
        content = message.content
        if content.startswith('[observation tool='):
            code_observation = content.startswith('[observation tool=code.repo_')
            source_read = content.startswith('[observation tool=code.repo_read_lines]')
            materials[message_key(message)] = Material(
                'code' if code_observation else 'tool',
                ('repository source' if source_read else 'repository index')
                if code_observation else 'commander observation',
                '"ok": false' in content or message_key(message) in (pending or set()),
            )
        elif message.role == 'assistant':
            materials[message_key(message)] = Material('history', 'commander completed reply', False)
        elif content.startswith('[reference background:'):
            materials[message_key(message)] = Material('background', 'project background', False)
    return materials
