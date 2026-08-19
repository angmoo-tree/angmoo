from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from app.domains.routines.infrastructure import sqlalchemy_daily_activity_plans


class SqlAlchemyDailyPlanRepository:
    def __init__(self, db: Session) -> None:
        self._db = db

    def prepare(self, **kwargs: Any) -> Any:
        return sqlalchemy_daily_activity_plans.prepare_activity_plan(self._db, **kwargs)

    def get(self, **kwargs: Any) -> Any:
        return sqlalchemy_daily_activity_plans.get_activity_plan(self._db, **kwargs)

    def update_runtime_mode(self, **kwargs: Any) -> Any:
        return sqlalchemy_daily_activity_plans.update_activity_runtime_mode(
            self._db, **kwargs
        )


__all__ = ["SqlAlchemyDailyPlanRepository"]
