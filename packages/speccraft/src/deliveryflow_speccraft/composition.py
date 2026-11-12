"""Server-owned local assembly shared by API and diagnostic entry points."""

from pathlib import Path

from deliveryflow_contracts.execution import ModelBudgetPolicy

from deliveryflow_speccraft.clarification import ClarificationProvider
from deliveryflow_speccraft.prd_authoring import PrdAuthor
from deliveryflow_speccraft.quality_engine import QualityModel
from deliveryflow_speccraft.repository_context import RepositoryHarness
from deliveryflow_speccraft.runner import RunRunner
from deliveryflow_speccraft.td_authoring import TdAuthor


def build_runner(
    project_root: Path,
    *,
    database_path: Path | None = None,
    clarification_provider: ClarificationProvider | None = None,
    prd_author: PrdAuthor | None = None,
    td_author: TdAuthor | None = None,
    quality_model: QualityModel | None = None,
    model_budget_policy: ModelBudgetPolicy | None = None,
) -> RunRunner:
    """Assemble the existing synchronous teaching mode; never resolve credentials."""
    return RunRunner(
        RepositoryHarness(project_root / "examples/speccraft/repositories/exportflow-sample"),
        project_root / "learning-assets/authoring-pack/v1/prd",
        td_authoring_directory=project_root / "learning-assets/authoring-pack/v1/td",
        database_path=(
            database_path
            if database_path is not None
            else project_root / ".deliveryflow-state/runs.sqlite3"
        ),
        clarification_provider=clarification_provider,
        prd_author=prd_author,
        td_author=td_author,
        quality_model=quality_model,
        model_budget_policy=model_budget_policy,
    )
