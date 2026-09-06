"""Memory consent, scheduled/exit cutoffs and bounded queue admission."""
from datetime import date, datetime
from sqlalchemy import exists, func, or_, select, update
from app.domains.memory.contracts.batch_preparation import MemoryPreparationDependencies
from app.domains.memory.contracts.items import as_utc
from app.domains.memory.contracts.scope import MemoryScope
from app.domains.memory.exceptions import MemoryDomainError
from app.domains.memory.models.batch import MemoryBatchSetting, MemorySourceDelivery
from app.domains.memory.models.items import MemoryScopeSettingModel
from app.domains.memory.policies.batch import next_daily_slot, schedule_timezone
from app.domains.memory.service.batch_preparation import enqueue_scope


def schedule_batches(session, *, dependencies: MemoryPreparationDependencies, now: datetime, shutdown: bool = False) -> None:
    # Authorize the cutoff once, in one SQL statement even for many characters.
    # Recovery may later deliver holes inside this persisted time boundary.
    config_table = MemoryBatchSetting.__table__
    scope_table = MemoryScopeSettingModel.__table__
    consent = (MemoryBatchSetting.ai_enabled.is_(True)) & (
        MemoryBatchSetting.consent_version == "memory-selection-consent.v1"
    )
    live_scope = exists(
        select(scope_table.c.id).where(
            scope_table.c.id == config_table.c.scope_setting_id,
            scope_table.c.enabled.is_(True),
        )
    )
    if shutdown:
        session.execute(
            update(MemoryBatchSetting)
            .where(consent, live_scope, MemoryBatchSetting.shutdown_enabled.is_(True))
            .values(trigger_kind="shutdown", trigger_requested_at=now)
        )
        session.flush()
    deliveries = MemorySourceDelivery.__table__
    ready_source = exists(
        select(deliveries.c.sequence).where(
            deliveries.c.scope_setting_id == config_table.c.scope_setting_id,
            deliveries.c.state == "delivered",
            deliveries.c.batch_job_id.is_(None),
            or_(
                deliveries.c.sequence <= config_table.c.trigger_cutoff,
                deliveries.c.captured_at <= config_table.c.trigger_requested_at,
            ),
        )
    )
    configs = dependencies.read_due_configs(session, consent=consent, ready_source=ready_source, now=now)
    for config in configs:
        setting = session.get(MemoryScopeSettingModel, config.scope_setting_id)
        scope = MemoryScope(
            setting.owner_id, setting.world_id, setting.subject_world_character_id
        )
        try:
            zone = dependencies.batch_repository(session).timezone(scope)
        except MemoryDomainError:
            # Preserve user settings but rotate unavailable scopes behind the
            # next bounded scan, without authorizing a provider request.
            config.last_claimed_at = now
            continue
        consumed = (
            None
            if config.last_consumed_date is None
            else date.fromisoformat(config.last_consumed_date)
        )
        if config.timezone != zone:
            config.timezone, config.version = zone, config.version + 1
            config.next_due_at = next_daily_slot(
                after=now,
                local_time=config.local_time,
                timezone=zone,
                last_consumed_date=consumed,
            )
        due = (
            config.schedule_enabled
            and config.next_due_at is not None
            and as_utc(config.next_due_at) <= as_utc(now)
        )
        if due:
            latest = (
                session.scalar(
                    select(func.max(MemorySourceDelivery.sequence)).where(
                        MemorySourceDelivery.scope_setting_id == config.scope_setting_id
                    )
                )
                or 0
            )
            config.trigger_cutoff = max(config.trigger_cutoff, latest)
            config.trigger_kind, config.trigger_requested_at = "scheduled", now
            config.last_consumed_date = (
                as_utc(now).astimezone(schedule_timezone(zone)).date().isoformat()
            )
            config.next_due_at = next_daily_slot(
                after=now,
                local_time=config.local_time,
                timezone=zone,
                last_consumed_date=date.fromisoformat(config.last_consumed_date),
            )
        if config.trigger_kind:
            enqueue_scope(
                session,
                dependencies=dependencies,
                scope_setting_id=config.scope_setting_id,
                trigger=config.trigger_kind,
                now=now,
                cutoff=config.trigger_cutoff,
                requested_at=config.trigger_requested_at,
            )
    session.commit()
