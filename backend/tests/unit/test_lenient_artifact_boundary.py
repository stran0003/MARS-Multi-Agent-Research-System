"""Presentation tolerance must not weaken actual execution bindings."""
from copy import deepcopy
import json

import pytest

from app.harness.agent_loop.protocol import parse_action, parse_review
from app.harness.schema.frontmatter_parser import document_from_parts, dumps, parse
from app.harness.schema.validator import validate_document
from app.harness.schema.experiment_contract import handoff_errors, delivery_execution_errors


def coding() -> dict:
    return {"schema": "code_spec.v1", "agent": "coding", "project": "test", "target_lang": "python",
        "baseline_compat": {"preserved": True}, "files_changed": [], "execution_jobs": [
            {"name": "baseline", "config": {"seed": 42, "budget_steps": 2, "command_id": "registered"}}]}


def test_bom_crlf_and_markdown_fences_are_presentation_only() -> None:
    text = dumps(coding(), "中文研究内容")
    wrapped = "\ufeff\r\n```markdown\r\n" + text.replace("\n", "\r\n") + "\r\n```\r\n"
    result = validate_document(wrapped, expected_schema="code_spec.v1")
    assert result.valid and result.metadata == coding()
    assert result.body == "中文研究内容"


def test_duplicate_frontmatter_is_merged_only_when_consistent() -> None:
    metadata = coding()
    text = document_from_parts(metadata, dumps(metadata, "完整正文"))
    assert parse(text).metadata == metadata and parse(text).body == "完整正文"
    conflicting = {**metadata, "project": "different"}
    with pytest.raises(ValueError, match="conflicting"):
        document_from_parts(metadata, dumps(conflicting, "正文"))


def test_document_notes_and_empty_prose_do_not_invent_fields() -> None:
    action = parse_action(json.dumps({"final": {"metadata": coding(), "notes": "附加说明"}}))
    assert validate_document(action["final"]).valid
    assert parse(action["final"]).metadata == coding()
    assert parse(action["final"]).body == ""
    review = parse_review('{"accept":true,"issues":[],"rationale":"checks passed","notes":"optional"}')
    assert set(review) == {"accept", "issues", "rationale"}


def test_document_hash_is_advisory_but_execution_types_are_not() -> None:
    metadata = {**coding(), "experiment_plan_sha256": "model forgot the digest"}
    result = validate_document(dumps(metadata, "正文"))
    assert result.valid and [warning.path for warning in result.warnings] == ["/experiment_plan_sha256"]
    metadata["baseline_compat"] = {"preserved": "maybe"}
    assert not validate_document(dumps(metadata, "正文")).valid


def test_short_clear_prose_does_not_fail_a_cosmetic_character_minimum() -> None:
    metadata = {"schema": "proposal.v1", "agent": "idea", "project": "test",
                "research_question": "降低误差", "hypothesis": "双分支互补", "novelty": "比较贡献"}
    result = validate_document(dumps(metadata, ""))
    assert result.valid
    assert any(item.path == "/research_question" for item in result.warnings)
    metadata["research_question"] = ""
    assert not validate_document(dumps(metadata, "")).valid


def test_handoff_compares_current_parameters_instead_of_copied_prose_digest() -> None:
    plan = {"project": "test", "ablations": [{"name": "baseline", "config": {"seed": 42, "budget_steps": 2}}],
            "estimated_runs": 1}
    text = dumps(plan, "更新文案\n")
    metadata = coding()
    metadata["experiment_plan_sha256"] = "old hash"
    assert not handoff_errors(text, metadata)
    changed = deepcopy(metadata)
    changed["execution_jobs"][0]["config"]["seed"] = 43
    assert handoff_errors(text, changed)
    changed = deepcopy(metadata)
    changed["execution_jobs"][0]["config"]["budget_steps"] = 200
    assert handoff_errors(text, changed)
    manifest = {"planned_experiments": metadata["execution_jobs"], "coding_spec_sha256": "old hash"}
    assert not delivery_execution_errors("", dumps(metadata, "正文"), manifest, project="test")
    manifest["planned_experiments"] = changed["execution_jobs"]
    assert delivery_execution_errors("", dumps(metadata, "正文"), manifest, project="test")
