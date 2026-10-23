"""Verify actual code differences before approving a handoff."""
from __future__ import annotations

import json
from typing import Any

from app.bridge.completed_code_changes import completed_code_changes
from app.harness.schema.validator import validate_document
from app.storage.run_store import RunHandle


def verify_written_code(run: RunHandle, text: str) -> bool:
    """True means the declared net changes are already present, not a patch replay.

    Git-backed projects use current net differences, independent of tool-write
    continuity. A missing actual implementation never passes as a written patch.
    The caller binds the run's repository capability before invoking this.
    """
    validation = validate_document(text, expected_schema="code_spec.v1")
    if not validation.valid or validation.metadata.get("project") != run.project:
        raise ValueError("编码方案校验未通过或不属于当前项目，未批准。")
    backend = validation.metadata.get('coding_backend')
    if isinstance(backend, dict) and backend.get('type') == 'git_commit':
        from app.bridge.git_code_delivery import verify_git_delivery
        verify_git_delivery(run, validation.metadata)
        return True
    rows: list[dict[str, Any]] = validation.metadata["files_changed"]
    declared = {row["path"]: row["type"] for row in rows}
    if len(declared) != len(rows):
        raise ValueError("编码方案存在重复的文件声明，未批准。")
    view = completed_code_changes(run, project=run.project)
    if view["warnings"]:
        raise ValueError("实际代码差异不能完整读取，请核对路径或文件后重新审核；未批准。")
    actual = {item["path"]: item["change"] for item in view["items"]}
    # Legacy unapplied patches are a separate path. Once actual tool work has
    # occurred, an empty Git diff means reuse; never replay an old patch to
    # manufacture the differences claimed by a stale document.
    from app.harness.tools.git_branch import changes_path
    known_work = view.get('source') == 'verified_git_workspace' and changes_path(run.root).is_file()
    if not actual and not view["write_records"] and not known_work:
        return not declared
    if actual != declared:
        evidence = json.dumps({"files_changed": [{"path": path, "type": kind} for path, kind in actual.items()],
                               "unchanged": view["unchanged"]}, ensure_ascii=False)
        raise ValueError("编码方案的文件清单与实际代码净改动不一致；相同内容的重写属于复用，不是新增。"
                         "请按已核验记录修正方案，不要为制造差异改写文件或重复应用补丁；未批准。" + evidence)
    return True


def coding_candidate_errors(run: RunHandle, text: str) -> list[str]:
    """Host evidence feeds the existing model correction loop before human review."""
    try:
        if not verify_written_code(run, text):
            return ["/files_changed: 尚无与方案对应的实际代码改动；请落实代码，不能只提交补丁说明。"]
    except (OSError, ValueError) as exc:
        return ["/files_changed: " + str(exc)]
    from app.execution.handoff_validation import coding_handoff_errors, execution_delivery_required, experiment_plan_required
    validation = validate_document(text, expected_schema='code_spec.v1')
    if validation.metadata.get('execution_jobs') or execution_delivery_required(run, 'coding'):
        plan = run.root / 'experiment/experiment_plan.approved.md'
        return coding_handoff_errors(plan.read_text() if plan.is_file() else '', validation.metadata,
            project=run.project, plan_required=experiment_plan_required(run, 'coding'),
            run_id=run.run_id, run_root=run.root)
    return []
