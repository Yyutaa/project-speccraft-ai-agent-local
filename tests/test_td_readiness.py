from hashlib import sha256

import pytest
from deliveryflow_speccraft.td import check_td_readiness
from test_td_review import awaiting_td
from test_td_runner import runner


@pytest.mark.parametrize(
    "change,code",
    [
        ("title", "missing_title"),
        ("missing", "missing_section"),
        ("duplicate", "duplicate_section"),
        ("unexpected", "unexpected_section"),
        ("order", "out_of_order"),
        ("empty", "empty_section"),
        ("placeholder", "placeholder"),
    ],
)
def test_td_structural_readiness_reports_issues_without_claiming_semantic_quality(
    change, code
):
    revision = awaiting_td(runner()).td_draft
    content = revision.content
    first = "## 文档信息"
    second = "## 背景、目标与技术范围"
    if change == "title":
        content = content.replace("# 统一技术设计（TD）", "# 错误标题", 1)
    elif change == "missing":
        content = content.replace(first, "正文信息", 1)
    elif change == "duplicate":
        content += "\n" + first + "\n重复章节正文\n"
    elif change == "unexpected":
        content += "\n## 额外章节\n额外正文\n"
    elif change == "order":
        content = (
            content.replace(first, "SECTION_TEMP", 1)
            .replace(second, first, 1)
            .replace("SECTION_TEMP", second, 1)
        )
    else:
        start = content.index(first) + len(first)
        end = content.index(second)
        content = (
            content[:start]
            + ("\n\n" if change == "empty" else "\nTODO\n")
            + content[end:]
        )
    mutated = revision.model_copy(
        update={
            "content": content,
            "content_hash": sha256(content.encode()).hexdigest(),
        }
    )
    readiness = check_td_readiness(mutated)
    assert (
        readiness.revision == revision.revision
        and readiness.content_hash == mutated.content_hash
    )
    assert not readiness.ready and code in {item.code for item in readiness.issues}
