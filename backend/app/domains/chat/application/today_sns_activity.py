"""Deterministic Today SNS snapshot assembly with no LLM call."""

from __future__ import annotations

from datetime import UTC, datetime, time
from hashlib import sha256
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.domains.chat.domain.today_sns_activity import (
    MAX_TODAY_ENTRY_TEXT_CHARS,
    TodaySnsActivityEntry,
    TodaySnsActivitySnapshot,
    TodaySnsSubjectiveContext,
    build_today_sns_hash,
)
from app.domains.chat.ports.today_sns_activity import TodaySnsActivityReaderPort


class TodaySnsActivityAssembler:
    def __init__(self, reader: TodaySnsActivityReaderPort) -> None:
        self._reader = reader

    def assemble(
        self,
        *,
        owner_id: str,
        world_id: str,
        subject_world_character_id: str,
        timezone: str,
        character_labels: dict[str, str],
        now: datetime,
    ) -> TodaySnsActivitySnapshot:
        if now.tzinfo is None:
            raise ValueError("today_sns_now_timezone_required")
        try:
            zone = ZoneInfo(timezone)
        except ZoneInfoNotFoundError as exc:
            raise ValueError("today_sns_world_timezone_invalid") from exc
        local_now = now.astimezone(zone)
        local_start = datetime.combine(local_now.date(), time.min, tzinfo=zone)
        start_utc = local_start.astimezone(UTC)
        end_utc = local_now.astimezone(UTC)
        source = self._reader.read(
            owner_id=owner_id,
            world_id=world_id,
            subject_world_character_id=subject_world_character_id,
            started_at=start_utc,
            complete_through=end_utc,
        )
        entries: list[TodaySnsActivityEntry] = []
        for record in source.records:
            body, body_truncated = _bounded(record.body)
            title, title_truncated = _bounded(record.title, limit=120)
            parent_body, parent_body_truncated = _bounded(record.parent_body, limit=300)
            parent_title, parent_title_truncated = _bounded(
                record.parent_title, limit=120
            )
            root_title, root_title_truncated = _bounded(record.root_title, limit=80)
            root_body, root_body_truncated = _bounded(record.root_body, limit=180)
            subjective = None
            if record.subjective_context is not None:
                subjective = TodaySnsSubjectiveContext(
                    motivation_kind=record.subjective_context.motivation_kind,
                    motivation_text=record.subjective_context.motivation_text,
                    emotion_label=record.subjective_context.emotion_label,
                    emotion_text=record.subjective_context.emotion_text,
                    emotion_intensity=record.subjective_context.emotion_intensity,
                )
            has_branch = record.parent_body is not None and record.body is not None
            details = {
                "title": title, "body": body, "parent_title": parent_title,
                "parent_body": parent_body, "root_title": root_title, "root_body": root_body,
            }
            reserved = 0 if subjective is None else (
                len(subjective.motivation_text) + len(subjective.emotion_text or "")
            )
            detail_budget_truncated = _fit_detail_budget(details, reserved=reserved)
            truncated = any((
                body_truncated, title_truncated, parent_body_truncated,
                parent_title_truncated, root_title_truncated, root_body_truncated,
                detail_budget_truncated,
            ))
            entries.append(
                TodaySnsActivityEntry(
                    opaque_reference=_opaque_reference(
                        record.record_key, record.source_revision
                    ),
                    kind=record.kind.value,
                    event_type=record.event_type,
                    source_type=record.source_type,
                    source_id=record.source_id,
                    source_revision=record.source_revision,
                    occurred_at=record.occurred_at,
                    actor_label=character_labels.get(
                        record.actor_world_character_id, "한 Character"
                    )[:80],
                    counterpart_label=(
                        None
                        if record.counterpart_world_character_id is None
                        else character_labels.get(
                            record.counterpart_world_character_id, "상대 Character"
                        )[:80]
                    ),
                    content_mode=(
                        "conversation_branch"
                        if has_branch
                        else "structured_fact"
                        if record.body is None
                        else "verbatim_excerpt"
                        if body_truncated or title_truncated
                        else "verbatim"
                    ),
                    **details,
                    root_post_id=record.root_post_id,
                    source_post_id=record.source_post_id,
                    target_post_id=record.target_post_id,
                    content_complete=not truncated,
                    truncated=truncated,
                    subjective_context=subjective,
                )
            )
        return TodaySnsActivitySnapshot(
            owner_id=owner_id,
            world_id=world_id,
            subject_world_character_id=subject_world_character_id,
            timezone=timezone,
            started_at=start_utc,
            complete_through=end_utc,
            counts=source.counts,
            coverage=source.coverage,
            source_watermarks=source.source_watermarks,
            entries=tuple(entries),
            overflow=source.overflow,
            counts_exact=source.counts_exact,
            snapshot_hash=build_today_sns_hash(
                owner_id=owner_id,
                world_id=world_id,
                subject_world_character_id=subject_world_character_id,
                timezone=timezone,
                started_at=start_utc,
                complete_through=end_utc,
                counts=source.counts,
                coverage=source.coverage,
                source_watermarks=source.source_watermarks,
                entries=tuple(entries),
                overflow=source.overflow,
                counts_exact=source.counts_exact,
            ),
        )


def _bounded(value: str | None, *, limit: int = MAX_TODAY_ENTRY_TEXT_CHARS):
    if value is None:
        return None, False
    normalized = " ".join(value.split())
    return normalized[:limit], len(normalized) > limit


def _opaque_reference(record_key: str, revision: str) -> str:
    digest = sha256(f"{record_key}\x1f{revision}".encode("utf-8")).hexdigest()[:24]
    return f"today-sns-{digest}"


def _fit_detail_budget(details: dict[str, str | None], *, reserved: int) -> bool:
    """Leave space for labels and typed prose inside the 2,000-char evidence cap."""
    excess = max(0, sum(len(value or "") for value in details.values()) + reserved - 1_400)
    truncated = excess > 0
    for key in ("root_body", "parent_body", "root_title", "parent_title", "title", "body"):
        value = details[key]
        if not excess or value is None:
            continue
        removed = min(excess, len(value))
        details[key] = value[:len(value) - removed] or None
        excess -= removed
    return truncated


__all__ = ["TodaySnsActivityAssembler"]
