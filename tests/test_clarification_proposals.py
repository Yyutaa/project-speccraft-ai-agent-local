from deliveryflow_contracts.facts import FactDimension, GapSignal
from deliveryflow_speccraft.model_boundary import build_clarification_task
from deliveryflow_speccraft.runner import FakeProvider


def test_fake_provider_only_translates_gap_signals_into_complete_proposals() -> None:
    gaps = tuple(
        GapSignal(
            gap_id=f"gap-{dimension.value}",
            dimension=dimension,
            blocking=True,
            reason=f"缺少 {dimension.value} 信息",
            ledger_revision=1,
        )
        for dimension in FactDimension
    )

    proposals = (
        FakeProvider().propose_clarifications(build_clarification_task(gaps)).proposals
    )

    assert {proposal.gap_id for proposal in proposals} == {gap.gap_id for gap in gaps}
    assert all(proposal.question and proposal.options for proposal in proposals)
    assert all(
        proposal.recommended_option_id is None
        or proposal.recommended_option_id
        in {option.option_id for option in proposal.options}
        for proposal in proposals
    )
