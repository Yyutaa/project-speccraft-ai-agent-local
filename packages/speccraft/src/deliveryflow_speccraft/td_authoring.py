"""Read the TD authoring pack and provide the deterministic teaching author."""

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from deliveryflow_contracts.model_tasks import ModelTaskInput, ModelTaskOutput, TdTaskData
from deliveryflow_contracts.td import (
    TD_SECTION_TITLES,
    TdSectionId,
)

from deliveryflow_speccraft.model_boundary import validate_task_input


@dataclass(frozen=True)
class TdAuthoringPack:
    template: str
    guide: str
    self_check: str


def load_td_authoring_pack(directory: Path) -> TdAuthoringPack:
    pack = TdAuthoringPack(
        template=(directory / "template.md").read_text(encoding="utf-8"),
        guide=(directory / "authoring-guide.md").read_text(encoding="utf-8"),
        self_check=(directory / "self-check.md").read_text(encoding="utf-8"),
    )
    headings = tuple(
        line.removeprefix("## ") for line in pack.template.splitlines() if line.startswith("## ")
    )
    if headings != tuple(TD_SECTION_TITLES.values()):
        raise ValueError("TD template chapters do not match the public Blueprint")
    return pack


class TdAuthor(Protocol):
    def author(self, task: ModelTaskInput) -> ModelTaskOutput: ...


_PLACEHOLDERS = {
    TdSectionId.DOCUMENT_INFO: "document_meta",
    TdSectionId.CONTEXT: "context",
    TdSectionId.REPOSITORY_CONSTRAINTS: "repository_constraints",
    TdSectionId.ARCHITECTURE_FLOW: "architecture_flow",
    TdSectionId.CHANGE_SCOPE: "change_scope",
    TdSectionId.DOMAIN_DATA_STATE: "domain_data_state",
    TdSectionId.BACKEND: "backend",
    TdSectionId.FRONTEND: "frontend",
    TdSectionId.API_EVENTS_ERRORS: "api_events_errors",
    TdSectionId.CONSISTENCY: "consistency",
    TdSectionId.DEPENDENCIES: "dependencies",
    TdSectionId.FAILURE_RECOVERY: "failure_recovery",
    TdSectionId.PERFORMANCE_SECURITY_OBSERVABILITY: "performance_security_observability",
    TdSectionId.TESTING_ACCEPTANCE: "testing_acceptance",
    TdSectionId.RELEASE_RISK: "release_risk",
    TdSectionId.TRACEABILITY: "traceability",
}


class FakeTdAuthor:
    """Fills the unified template from cited authority without judging quality."""

    def author(self, task: ModelTaskInput) -> ModelTaskOutput:
        task = validate_task_input(task)
        if not isinstance(task.payload, TdTaskData):
            raise ValueError("TD Author requires a TD task")
        blueprint = task.payload.blueprint
        authority = task.payload.authority
        obligations = task.payload.obligations
        pack = task.resources
        repository_constraints = tuple(
            f"{entry.path}: {entry.selection_reason}\n{entry.content}"
            for entry in task.typed_context_entries
        )
        decisions = task.payload.decisions
        authority_by_id = {item.authority_id: item for item in authority.items}
        obligation_by_id = {item.obligation_id: item for item in obligations}
        if set(authority_by_id) != set(blueprint.authority_ids):
            raise ValueError("TD author authority input must match the Blueprint")
        if set(obligation_by_id) != set(blueprint.obligation_ids):
            raise ValueError("TD author obligation input must match the Blueprint")

        bodies: dict[TdSectionId, str] = {}
        for section in blueprint.sections:
            lines = [
                f"- Authority `{item_id}`：{authority_by_id[item_id].statement}"
                for item_id in section.authority_ids
            ]
            lines += [
                f"- PRD 义务 `{item_id}`：{obligation_by_id[item_id].statement}"
                for item_id in section.obligation_ids
            ]
            if section.section_id is TdSectionId.DOCUMENT_INFO:
                lines = [
                    f"绑定 PRD r{blueprint.prd_revision}，SHA-256 `{blueprint.prd_content_hash}`。"
                ]
            elif section.section_id is TdSectionId.REPOSITORY_CONSTRAINTS:
                lines = [f"- {constraint}" for constraint in repository_constraints]
            elif section.section_id is TdSectionId.TRACEABILITY:
                lines += [
                    f"- 技术决定 `{decision.request_id}`：{decision.answer}"
                    for decision in decisions
                ]
            bodies[section.section_id] = (
                "\n".join(lines) or "不适用：当前权威输入没有该类技术变更。"
            )

        content = pack.template.replace(
            "{{ title }}", f"基于 PRD r{blueprint.prd_revision} 的技术方案"
        )
        for section_id, placeholder in _PLACEHOLDERS.items():
            content = content.replace(f"{{{{ {placeholder} }}}}", bodies[section_id])
        if "{{" in content or "}}" in content:
            raise ValueError("TD template has unresolved placeholders")
        return ModelTaskOutput(
            task_kind="td_author",
            input_binding=task.input_binding,
            cited_ids=blueprint.authority_ids + blueprint.obligation_ids,
            content=content,
            obligations=obligations,
        )
