"""Read-only export of the exact three published artifacts, with no model or file I/O."""

from dataclasses import dataclass
from hashlib import sha256

from deliveryflow_contracts.artifacts import (
    ArtifactApprovalRef,
    ArtifactKind,
    ArtifactRef,
    PublishedArtifact,
)
from deliveryflow_contracts.runs import RunResponse, RunStatus

from deliveryflow_speccraft.quality_engine import audit_current, ledger_hash
from deliveryflow_speccraft.runner import GovernanceError
from deliveryflow_speccraft.td import (
    check_td_readiness,
    extract_prd_obligations,
    validate_td_obligations,
)
from deliveryflow_speccraft.td_review import current_td_review_binding


@dataclass(frozen=True)
class ArtifactDownload:
    metadata: PublishedArtifact
    content: bytes


def published_artifacts(run: RunResponse) -> tuple[ArtifactDownload, ...]:
    """Recheck all publication evidence before returning even one artifact's bytes."""
    if run.status is not RunStatus.COMPLETED:
        raise GovernanceError("artifact_export_unavailable", 409)
    try:
        run = RunResponse.model_validate(run.model_dump())
        prd, td, spec = run.prd_draft, run.td_draft, run.delivery_spec
        approval, td_approval, review = run.prd_approval, run.td_approval, run.td_review
        if not all((prd, td, spec, approval, td_approval, review, run.quality_gate)):
            raise ValueError("missing publication evidence")
        assert prd and td and spec and approval and td_approval and review and run.quality_gate
        if (
            approval.revision != prd.revision
            or approval.content_hash != prd.content_hash
            or td_approval.revision != td.revision
            or td_approval.content_hash != td.content_hash
            or review.status != "ready"
            or review.binding != current_td_review_binding(run)
            or td_approval.review_id != review.current_review_id
            or td_approval.expected_review_revision != review.review_revision
            or not run.td_review_records
            or run.td_review_records[-1].review_id != review.current_review_id
            or run.td_review_records[-1].binding != review.binding
            or not audit_current(run)
            or not run.quality_audit_current
            or run.quality_gate.status != "ready"
            or not check_td_readiness(td).ready
        ):
            raise ValueError("publication Gate is not current")
        assert run.prd_blueprint and run.td_blueprint and run.design_authority
        validate_td_obligations(
            td,
            prd,
            approval,
            run.design_authority,
            run.td_blueprint,
            extract_prd_obligations(prd, run.prd_blueprint),
        )
        prd_ref = ArtifactRef(
            artifact_id=f"{run.run_id}:prd",
            kind=ArtifactKind.PRD,
            revision=prd.revision,
            content_hash=prd.content_hash,
            media_type="text/markdown",
        )
        td_ref = ArtifactRef(
            artifact_id=f"{run.run_id}:td",
            kind=ArtifactKind.TD,
            revision=td.revision,
            content_hash=td.content_hash,
            media_type="text/markdown",
        )
        data = (
            (ArtifactKind.PRD, "PRD.md", prd.content.encode("utf-8"), prd_ref),
            (ArtifactKind.TD, "TD.md", td.content.encode("utf-8"), td_ref),
            (
                ArtifactKind.DELIVERY_SPEC,
                "DeliverySpec.json",
                spec.model_dump_json().encode("utf-8"),
                ArtifactRef(
                    artifact_id=f"{run.run_id}:delivery-spec",
                    kind=ArtifactKind.DELIVERY_SPEC,
                    revision=1,
                    content_hash=sha256(spec.model_dump_json().encode("utf-8")).hexdigest(),
                    media_type="application/json",
                ),
            ),
        )
        if spec.prd != prd_ref or spec.td != td_ref:
            raise ValueError("delivery references changed")
        approvals = {
            ArtifactKind.PRD: ArtifactApprovalRef(
                revision=approval.revision,
                content_hash=approval.content_hash,
                actor=approval.actor,
                approved_at=approval.approved_at,
            ),
            ArtifactKind.TD: ArtifactApprovalRef(
                revision=td_approval.revision,
                content_hash=td_approval.content_hash,
                actor=td_approval.actor,
                approved_at=td_approval.approved_at,
            ),
        }
        approvals[ArtifactKind.DELIVERY_SPEC] = approvals[ArtifactKind.TD]
        derivations = {
            ArtifactKind.PRD: (),
            ArtifactKind.TD: (prd_ref,),
            ArtifactKind.DELIVERY_SPEC: (prd_ref, td_ref),
        }
        envelopes = {item.artifact.kind: item for item in run.artifact_envelopes}
        downloads = []
        for kind, filename, content, reference in data:
            envelope = envelopes[kind]
            if (
                sha256(content).hexdigest() != reference.content_hash
                or envelope.artifact != reference
                or envelope.approval != approvals[kind]
                or envelope.derived_from != derivations[kind]
                or (kind != ArtifactKind.PRD and envelope.quality_evidence_hash != ledger_hash(run))
            ):
                raise ValueError("published bytes or evidence changed")
            downloads.append(
                ArtifactDownload(
                    metadata=PublishedArtifact(
                        kind=kind,
                        filename=filename,
                        revision=reference.revision,
                        content_hash=reference.content_hash,
                        media_type=reference.media_type,
                    ),
                    content=content,
                )
            )
        return tuple(downloads)
    except (ValueError, KeyError, AssertionError) as error:
        raise GovernanceError("artifact_integrity_conflict", 409) from error
