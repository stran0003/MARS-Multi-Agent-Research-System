"""Authored wire fixtures and real SDK serialization, not a substitute model."""
from __future__ import annotations

import json
from typing import Any

import pytest
from openai.types.chat import ChatCompletion

from app.harness.agent_loop.zcode.gateway import completion_payload, stream_envelope
from app.harness.llm.openai_provider import OpenAIProvider
from app.harness.llm.provider_base import LLMCompletionError, LLMConfig, Message, model_request_timeout


def provider() -> OpenAIProvider:
    return OpenAIProvider(api_key="parser-only-not-a-credential")


def body(events: list[dict[str, Any]], *, done: bool = True) -> str:
    return "\ufeff: heartbeat\r\n\r\n" + "".join(
        "data: " + json.dumps(event, ensure_ascii=False) + "\r\n\r\n" for event in events
    ) + ("data: [DONE]\r\n\r\n" if done else "")


def test_nonstream_is_explicit_even_in_plain_gateway_mode() -> None:
    p = provider()
    config = LLMConfig(provider="custom", model="intranet", extra={
        "gateway_plain_request": True, "template_family": "qwen38_instruct"})
    request = p._request_kwargs([Message("user", "公开答复")], config)
    assert request["stream"] is False and request["timeout"] >= 720
    assert "extra_body" not in request
    assert p._request_kwargs([Message("user", "公开答复")], config, stream=True)["stream"] is True
    wire = completion_payload({"stream": True, "stream_options": {"include_usage": True}}, config)
    assert wire["stream"] is False and "stream_options" not in wire
    assert "thinking" not in wire
    assert p._client is None


@pytest.mark.parametrize("transport", ["dict", "json", "sdk", "sse"])
@pytest.mark.parametrize("reasoning_field", ["reasoning", "reasoning_content"])
def test_reasoning_is_not_a_final_answer(transport: str, reasoning_field: str) -> None:
    p = provider()
    config = LLMConfig(provider="custom", model="intranet")
    payload: dict[str, Any] = {"id": "parser-fixture", "created": 0, "object": "chat.completion",
        "model": "intranet", "choices": [{"index": 0, "finish_reason": "stop", "message": {
            "role": "assistant", "content": "公开结果", reasoning_field: "private-fixture"}}]}
    value: Any = payload
    if transport == "json":
        value = json.dumps(payload)
    elif transport == "sdk":
        value = ChatCompletion.model_validate(payload)
    elif transport == "sse":
        value = body([{"model": "intranet", "choices": [{"delta": {reasoning_field: "private-fixture"}}]},
                      {"model": "intranet", "choices": [{"delta": {"content": "公开结果"}, "finish_reason": "stop"}]}])
    result = p._completion_from_response(value, config)
    assert result.text == "公开结果" and "private-fixture" not in repr(result)
    assert p._client is None


def test_forced_sse_done_without_redundant_finish_reason_is_accepted() -> None:
    p = provider()
    events = [{"choices": [{"delta": {"content": "完整公开答复"}}]}]
    assert p._completion_from_response(body(events), LLMConfig("custom", "intranet")).text == "完整公开答复"
    with pytest.raises(LLMCompletionError, match="incomplete_stream"):
        p._completion_from_response(body(events, done=False), LLMConfig("custom", "intranet"))


@pytest.mark.parametrize("transport", ["json", "sse"])
def test_reasoning_only_or_length_limited_reply_is_never_success(transport: str) -> None:
    p = provider()
    for reason, content in [("stop", None), ("length", "partial")]:
        key = "delta" if transport == "sse" else "message"
        payload = {"choices": [{key: {"content": content, "reasoning": "private-fixture"}, "finish_reason": reason}]}
        value = body([payload]) if transport == "sse" else json.dumps(payload)
        with pytest.raises(LLMCompletionError) as error:
            p._completion_from_response(value, LLMConfig("custom", "intranet"))
        assert "private-fixture" not in str(error.value)
        with pytest.raises(LLMCompletionError):
            p._wire_from_response(value, {}, LLMConfig("custom", "intranet"))


def test_zcode_forced_sse_preserves_tool_call_and_private_wire_continuation() -> None:
    p = provider()
    events = [{"model": "intranet", "choices": [{"delta": {
        "reasoning": "private-fixture", "tool_calls": [{"index": 0, "id": "call", "function": {
            "name": "read_file", "arguments": '{"path":'}}]}}]},
        {"model": "intranet", "choices": [{"delta": {"tool_calls": [{"index": 0, "function": {
            "arguments": '"中文.py"}'}}]}, "finish_reason": "tool_calls"}]}]
    config = LLMConfig("custom", "intranet", tools=({"type": "function"},))
    wire = p._wire_from_response(body(events), {"tools": list(config.tools)}, config)
    message = wire["choices"][0]["message"]
    assert json.loads(message["tool_calls"][0]["function"]["arguments"]) == {"path": "中文.py"}
    assert message["reasoning"] == "private-fixture"
    # The native caller and the public MARS trace must only receive public data.
    assert "private-fixture" not in repr(p._completion_from_response(wire, config))
    assert "private-fixture" not in repr(p._completion_from_response(stream_envelope(wire), config))


@pytest.mark.parametrize("value,expected", [(None, 720), (120, 720), (720, 720), (3600, 3600)])
def test_deployment_timeouts_migrate_without_reducing_existing_settings(value: Any, expected: float) -> None:
    assert model_request_timeout(value) == expected


@pytest.mark.parametrize("value", [0, -1, float("nan"), float("inf")])
def test_invalid_timeout_is_not_silently_infinite(value: float) -> None:
    with pytest.raises(ValueError):
        model_request_timeout(value)
