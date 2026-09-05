"""active hours presets and cap

Revision ID: 20260616_0048
Revises: 20260616_0047
Create Date: 2026-06-16
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20260616_0048"
down_revision: str | None = "20260616_0047"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        sa.text(
            """
            with parsed as (
                select
                    character_id,
                    case
                        when active_hours_start ~ '^(0[0-9]|1[0-9]|2[0-3]):(00|30)$'
                        then split_part(active_hours_start, ':', 1)::integer * 60
                           + split_part(active_hours_start, ':', 2)::integer
                        else null
                    end as start_minute,
                    case
                        when active_hours_end = '24:00' then 1440
                        when active_hours_end ~ '^(0[0-9]|1[0-9]|2[0-3]):(00|30)$'
                        then split_part(active_hours_end, ':', 1)::integer * 60
                           + split_part(active_hours_end, ':', 2)::integer
                        else null
                    end as end_minute
                from agent_activity_settings
            ),
            invalid_settings as (
                select
                    character_id,
                    case
                        when start_minute is null or end_minute is null then null
                        when start_minute = end_minute then 0
                        else mod(end_minute - start_minute + 1440, 1440)
                    end as duration_minutes
                from parsed
            )
            update agent_activity_settings as settings
               set active_hours_start = '14:00',
                   active_hours_end = '22:00'
              from invalid_settings
             where settings.character_id = invalid_settings.character_id
               and (
                    invalid_settings.duration_minutes is null
                    or invalid_settings.duration_minutes <= 0
                    or invalid_settings.duration_minutes > 1020
               )
            """
        )
    )


def downgrade() -> None:
    pass
