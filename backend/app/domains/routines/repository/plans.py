"""Selection history; no permission, publication, or commit decisions."""
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domains.routines import models
from app.domains.routines.constants import USAGE_WINDOW_DAYS


def _selection_history(
    db: Session,
    *,
    world_character_id: str,
    local_date: date,
) -> list[tuple[models.DailyActivityPlanItem, date]]:
    earliest = local_date - timedelta(days=USAGE_WINDOW_DAYS)
    rows = db.execute(
        select(models.DailyActivityPlanItem, models.DailyActivityPlan.local_date)
        .join(
            models.DailyActivityPlan,
            models.DailyActivityPlan.id == models.DailyActivityPlanItem.plan_id,
        )
        .where(
            models.DailyActivityPlan.world_character_id == world_character_id,
            models.DailyActivityPlan.local_date >= earliest,
            models.DailyActivityPlan.local_date < local_date,
        )
    )
    return [(item, history_date) for item, history_date in rows]
