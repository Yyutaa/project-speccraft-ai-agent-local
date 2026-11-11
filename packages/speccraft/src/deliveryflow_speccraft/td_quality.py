"""Deterministic TD quality findings and bounded patch evaluation."""

import re
from collections.abc import Callable
from dataclasses import dataclass
from hashlib import sha256
from typing import Literal

from deliveryflow_contracts.quality import QualityGateProjection, QualityIssueRecord
from deliveryflow_contracts.td import TdBlueprint, TdRevision, td_obligations_hash

from deliveryflow_speccraft.td import check_td_readiness


@dataclass(frozen=True)
class QualityFinding:
    validator_id: str
    rule_id: str
    section_id: str
    authority_ref: str
    evidence: str
    severity: Literal["blocker", "major"] = "blocker"

    @property
    def issue_id(self) -> str:
        identity = "\0".join((self.validator_id, self.rule_id, self.section_id, self.authority_ref))
        return sha256(identity.encode("utf-8")).hexdigest()[:24]


VALIDATORS = {
    "td.placeholder": "td_document",
    "td.structure": "td_document",
    "td.authority_ref": "td_blueprint",
    "td.obligation_ref": "td_blueprint",
    "td.uncertain": "td_document",
}


def discover_td_quality(content: str) -> tuple[QualityFinding, ...]:
    """Find exact placeholders; semantic review remains an independent human task."""
    section = "document"
    findings: list[QualityFinding] = []
    for line in content.splitlines():
        if line.startswith("## "):
            section = line[3:].strip()
        elif re.search(r"TODO|待补充|\{\{[^}]*\}\}|<[^>]+>", line, re.IGNORECASE):
            findings.append(
                QualityFinding("td_document", "td.placeholder", section, "", line.strip())
            )
        elif "待核实" in line:
            findings.append(
                QualityFinding("td_document", "td.uncertain", section, "", line.strip(), "major")
            )
    return tuple(findings)


def discover_td_references(content: str, blueprint: TdBlueprint) -> tuple[QualityFinding, ...]:
    """Require each planned reference in its own canonical TD section."""
    sections: dict[str, str] = {}
    current = ""
    lines: list[str] = []
    for line in content.splitlines():
        if line.startswith("## "):
            if current:
                sections[current] = "\n".join(lines)
            current = line[3:].strip()
            lines = []
        elif current:
            lines.append(line)
    if current:
        sections[current] = "\n".join(lines)
    findings: list[QualityFinding] = []
    for plan in blueprint.sections:
        body = sections.get(plan.title, "")
        for authority_id in plan.authority_ids:
            if f"Authority `{authority_id}`" not in body:
                findings.append(
                    QualityFinding(
                        "td_blueprint",
                        "td.authority_ref",
                        plan.title,
                        authority_id,
                        f"缺少 Authority `{authority_id}` 引用",
                    )
                )
        for obligation_id in plan.obligation_ids:
            if f"PRD 义务 `{obligation_id}`" not in body:
                findings.append(
                    QualityFinding(
                        "td_blueprint",
                        "td.obligation_ref",
                        plan.title,
                        obligation_id,
                        f"缺少 PRD 义务 `{obligation_id}` 引用",
                    )
                )
    return tuple(findings)


@dataclass(frozen=True)
class PatchResult:
    content: str
    committed: bool
    reason: str | None = None


def apply_quality_patch(
    content: str,
    section_title: str,
    replacement_body: str,
    *,
    expected_hash: str,
    target_check: Callable[[str], bool],
    regression_check: Callable[[str], bool],
) -> PatchResult:
    if sha256(content.encode("utf-8")).hexdigest() != expected_hash:
        raise ValueError("stale patch baseline")
    if not replacement_body.strip():
        raise ValueError("empty replacement body")
    heading = f"## {section_title}"
    lines = content.splitlines(keepends=True)
    starts = [i for i, line in enumerate(lines) if line.rstrip("\r\n") == heading]
    if len(starts) != 1:
        raise ValueError("patch requires exactly one existing section")
    start = starts[0]
    end = next((i for i in range(start + 1, len(lines)) if lines[i].startswith("## ")), len(lines))
    prefix = "".join(lines[: start + 1])
    candidate = (
        prefix
        + ("" if prefix.endswith("\n") else "\n")
        + replacement_body.strip()
        + "\n"
        + "".join(lines[end:])
    )
    before = tuple(line for line in content.splitlines() if line.startswith("## "))
    after = tuple(line for line in candidate.splitlines() if line.startswith("## "))
    if before != after:
        return PatchResult(content, False, "section_set_changed")
    if not target_check(candidate):
        return PatchResult(content, False, "target_still_present")
    if not regression_check(candidate):
        return PatchResult(content, False, "regression_detected")
    return PatchResult(candidate, True)


def project_quality(
    td: TdRevision, previous: tuple[QualityIssueRecord, ...], blueprint: TdBlueprint | None = None
) -> tuple[tuple[QualityIssueRecord, ...], QualityGateProjection]:
    """Reconcile exact current findings with persisted Issue history."""
    scanned = list(discover_td_quality(td.content))
    if blueprint is not None:
        scanned.extend(discover_td_references(td.content, blueprint))
    for structural in check_td_readiness(td).issues:
        if structural.code != "placeholder":
            scanned.append(
                QualityFinding(
                    "td_document",
                    f"td.structure.{structural.code}",
                    structural.section_id.value if structural.section_id else "document",
                    "",
                    structural.code,
                )
            )
    findings = {item.issue_id: item for item in scanned}
    old = {item.issue_id: item for item in previous}
    records: list[QualityIssueRecord] = []
    for issue_id, finding in findings.items():
        prior = old.get(issue_id)
        records.append(
            QualityIssueRecord(
                issue_id=issue_id,
                validator_id=finding.validator_id,
                rule_id=finding.rule_id,
                section_id=finding.section_id,
                authority_ref=finding.authority_ref,
                evidence=finding.evidence,
                severity=finding.severity,
                status=(
                    "failed"
                    if prior and prior.status == "failed"
                    else "reopened"
                    if prior
                    and (
                        prior.status == "resolved"
                        or (prior.status == "accepted" and td.revision > prior.latest_td_revision)
                    )
                    else prior.status
                    if prior
                    else "open"
                ),
                attempts=prior.attempts if prior else 0,
                last_failure=prior.last_failure if prior else None,
                first_td_revision=prior.first_td_revision if prior else td.revision,
                latest_td_revision=td.revision,
            )
        )
    for issue_id, prior in old.items():
        if issue_id not in findings and prior.producer_kind == "model":
            records.append(prior.model_copy(update={
                "status": "reopened" if td.revision > prior.latest_td_revision
                    and prior.status in ("accepted", "resolved") else prior.status,
                "latest_td_revision": td.revision,
            }))
        elif issue_id not in findings:
            records.append(
                prior.model_copy(
                    update={
                        "status": "resolved",
                        "last_failure": None,
                        "latest_td_revision": td.revision,
                    }
                )
            )
    blockers = tuple(
        item.issue_id for item in records if item.status not in ("resolved", "accepted")
    )
    gate_status: Literal["continue", "diagnose", "final_audit", "ready"] = (
        "diagnose"
        if any(item.status == "failed" and item.severity == "blocker" for item in records)
        else ("continue" if blockers else "ready")
    )
    return tuple(records), QualityGateProjection(
        td_revision=td.revision,
        td_content_hash=td.content_hash,
        authority_pack_hash=td.authority_pack_hash,
        obligations_hash=td_obligations_hash(td.obligations),
        status=gate_status,
        blocking_issue_ids=blockers,
    )
