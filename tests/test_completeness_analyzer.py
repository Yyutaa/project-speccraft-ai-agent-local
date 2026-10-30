from deliveryflow_contracts.facts import (
    CompletenessResult,
    FactDimension,
    FactLedger,
    RequirementFact,
)
from deliveryflow_speccraft.completeness import CompletenessAnalyzer
from governance_helpers import admitted_fact


def source_fact(fact_id: str, dimension: FactDimension, claim: str) -> RequirementFact:
    return admitted_fact(fact_id=fact_id, dimension=dimension, claim=claim)


def test_analyzer_reports_each_missing_blocking_dimension_deterministically() -> None:
    ledger = FactLedger(revision=1, facts=())
    analyzer = CompletenessAnalyzer()

    first = analyzer.analyze(ledger)
    second = analyzer.analyze(ledger)

    assert first == second
    assert isinstance(first, CompletenessResult)
    assert not first.is_complete
    assert {gap.dimension for gap in first.gaps} == set(FactDimension)
    assert all(gap.blocking for gap in first.gaps)


def test_explicit_source_facts_cover_only_their_typed_dimensions() -> None:
    ledger = FactLedger(
        revision=3,
        facts=(source_fact("role", FactDimension.ROLE, "管理员使用"),),
    )

    result = CompletenessAnalyzer().analyze(ledger)

    assert FactDimension.ROLE not in {gap.dimension for gap in result.gaps}
    assert {gap.dimension for gap in result.gaps} == set(FactDimension) - {FactDimension.ROLE}


def test_conflicting_source_facts_block_until_a_user_decision_resolves_them() -> None:
    facts = (
        source_fact("role-a", FactDimension.ROLE, "管理员使用"),
        source_fact("role-b", FactDimension.ROLE, "客户使用"),
    )
    analyzer = CompletenessAnalyzer()

    result = analyzer.analyze(FactLedger(revision=1, facts=facts))

    assert any(gap.dimension is FactDimension.ROLE and gap.blocking for gap in result.gaps)
