"""Canonical Character profile persistence and handle policy.

Existing create/update operations own commit/refresh. Read methods use the
caller Session; seed creation has a distinct flush-only contract in seed.py.
"""
import re
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from app.domains.characters import models, schemas
from app.domains.characters.exceptions import CharacterHandleConflictError, InvalidCharacterHandleError
from app.domains.identity.public import User

HANDLE_RE = re.compile(r"^[a-z0-9_]{2,40}$")

def normalize_character_handle(value: str) -> str:
    handle = value.strip().lower().removeprefix("@")
    handle = re.sub(r"[\s-]+", "_", handle)
    if not HANDLE_RE.fullmatch(handle):
        raise InvalidCharacterHandleError(
            "핸들은 영문 소문자, 숫자, 밑줄(_)만 사용할 수 있습니다."
        )
    return handle


def _fallback_handle(name: str, character_id: str) -> str:
    raw = re.sub(r"[\s-]+", "_", name.strip().lower())
    handle = re.sub(r"[^a-z0-9_]", "", raw).strip("_")
    if len(handle) < 2:
        handle = f"angmoo_{character_id.replace('char-', '')[:8]}"
    return handle[:40].strip("_") or f"angmoo_{character_id[-8:]}"


def _ensure_available_handle(
    db: Session,
    handle: str,
    *,
    current_character_id: str | None = None,
    allow_suffix: bool,
) -> str:
    candidate = handle
    suffix = 2
    while True:
        existing = db.scalar(
            select(models.Character).where(models.Character.handle == candidate)
        )
        if existing is None or existing.id == current_character_id:
            return candidate
        if not allow_suffix:
            raise CharacterHandleConflictError(f"@{handle} 핸들은 이미 사용 중입니다.")
        suffix_text = f"_{suffix}"
        candidate = f"{handle[: 40 - len(suffix_text)]}{suffix_text}"
        suffix += 1


def validate_character_handle_for_create(db: Session, value: str) -> str:
    handle = normalize_character_handle(value)
    return _ensure_available_handle(db, handle, allow_suffix=False)


def get_character(db: Session, character_id: str) -> models.Character | None:
    return db.get(models.Character, character_id)


def count_user_characters(db: Session, user_id: str) -> int:
    return db.scalar(
        select(func.count(models.Character.id)).where(
            models.Character.owner_id == user_id,
            models.Character.deleted_at.is_(None),
        )
    ) or 0


def list_characters_for_user(db: Session, user_id: str) -> list[models.Character]:
    return list(
        db.scalars(
            select(models.Character)
            .where(
                models.Character.owner_id == user_id,
                models.Character.deleted_at.is_(None),
            )
            .order_by(models.Character.created_at.asc(), models.Character.id.asc())
        )
    )


def create_character(
    db: Session, *, user: User, character_id: str, data: schemas.AgentCreate
) -> models.Character:
    requested_handle = (
        normalize_character_handle(data.handle) if data.handle else None
    )
    handle = _ensure_available_handle(
        db,
        requested_handle or _fallback_handle(data.name, character_id),
        allow_suffix=requested_handle is None,
    )
    avatar_url = data.avatar_url.strip() if data.avatar_url else None
    banner_url = data.banner_url.strip() if data.banner_url else None
    character = models.Character(
        id=character_id,
        owner_id=user.id,
        name=data.name.strip(),
        handle=handle,
        avatar_url=avatar_url,
        banner_url=banner_url,
        one_liner=data.one_liner.strip(),
        personality=data.personality.strip(),
        speech_style=data.speech_style.strip(),
        worldview=data.worldview.strip(),
        topic_preferences=data.topic_preferences.strip(),
        safety_rules=data.safety_rules.strip(),
        status="inactive",
        execution_mode=data.execution_mode,
        persona_summary="",
    )
    character.persona_summary = _build_persona_summary(character)
    db.add(character)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        _raise_handle_conflict_from_integrity(exc, handle)
        raise
    db.refresh(character)
    return character


def update_character_profile(
    db: Session, character: models.Character, data: schemas.AgentProfileUpdate
) -> models.Character:
    if data.name is not None:
        character.name = data.name.strip()
    if data.handle is not None:
        handle = normalize_character_handle(data.handle)
        character.handle = _ensure_available_handle(
            db,
            handle,
            current_character_id=character.id,
            allow_suffix=False,
        )
    if data.avatar_url is not None:
        character.avatar_url = data.avatar_url.strip() or None
    if data.banner_url is not None:
        character.banner_url = data.banner_url.strip() or None
    if data.one_liner is not None:
        character.one_liner = data.one_liner.strip()
        character.persona_summary = _build_persona_summary(character)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        _raise_handle_conflict_from_integrity(exc, character.handle)
        raise
    db.refresh(character)
    return character


def update_character_persona(
    db: Session, character: models.Character, data: schemas.AgentPersonaUpdate
) -> models.Character:
    character.personality = data.personality.strip()
    character.speech_style = data.speech_style.strip()
    character.worldview = data.worldview.strip()
    character.topic_preferences = data.topic_preferences.strip()
    character.safety_rules = data.safety_rules.strip()
    character.persona_summary = _build_persona_summary(character)
    db.commit()
    db.refresh(character)
    return character


def _build_persona_summary(character: models.Character) -> str:
    return "\n".join(
        part
        for part in [
            character.one_liner.strip(),
            f"성격: {character.personality.strip()}"
            if character.personality.strip()
            else "",
            f"말투: {character.speech_style.strip()}"
            if character.speech_style.strip()
            else "",
            f"세계관: {character.worldview.strip()}"
            if character.worldview.strip()
            else "",
            f"관심 주제: {character.topic_preferences.strip()}"
            if character.topic_preferences.strip()
            else "",
            f"피해야 할 행동: {character.safety_rules.strip()}"
            if character.safety_rules.strip()
            else "",
        ]
        if part
    )


def _raise_handle_conflict_from_integrity(exc: IntegrityError, handle: str) -> None:
    message = str(exc.orig)
    if "uq_characters_handle" in message or "characters_handle_key" in message:
        raise CharacterHandleConflictError(f"@{handle} 핸들은 이미 사용 중입니다.") from exc
