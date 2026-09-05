"""Connect same-Session planning references at application creation."""
from typing import Any

from app.runtime.routines.plan_references import SqlAlchemyPlanReferences


def configure_routines_runtime(app: Any) -> None:
    app.state.routine_plan_references_factory = SqlAlchemyPlanReferences
