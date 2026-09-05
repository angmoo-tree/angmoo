"""Request Session and application-supplied planning references."""
from fastapi import Depends, Request
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.domains.routines.contracts.plans import PlanReferences, PlanReferencesFactory


def get_plan_references(
    request: Request, db: Session = Depends(get_db)
) -> PlanReferences:
    factory: PlanReferencesFactory = request.app.state.routine_plan_references_factory
    return factory(db)
