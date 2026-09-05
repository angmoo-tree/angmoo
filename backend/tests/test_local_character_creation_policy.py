from __future__ import annotations

import asyncio
from pathlib import Path

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from app import models, schemas
from app.runtime.characters import creator as draft_service
from app.runtime.characters import management as agent_service


REPO_ROOT = Path(__file__).resolve().parents[2]


def _create_tables(engine) -> None:
    for table in (
        models.User.__table__,
        models.Character.__table__,
        models.CharacterActiveWorld.__table__,
        models.CharacterState.__table__,
        models.Post.__table__,
        models.PostMedia.__table__,
        models.PostImageQuotaReservation.__table__,
        models.LlmCredential.__table__,
        models.AgentRun.__table__,
        models.AgentActivitySetting.__table__,
        models.AgentImageGenerationSetting.__table__,
        models.AgentSlot.__table__,
        models.AgentActivityLog.__table__,
        models.AgentFeedCue.__table__,
        models.SiteOperationBanner.__table__,
        models.SiteOperationSetting.__table__,
        models.AgentCreationDraft.__table__,
        models.ProfileImageQuotaReservation.__table__,
        models.ProfileImageCandidate.__table__,
    ):
        table.create(engine)


def _add_user(db: Session) -> models.User:
    user = models.User(id="local-owner", display_name="Local Owner")
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _create_agent(
    db: Session,
    user: models.User,
    *,
    execution_mode: str,
    index: int,
) -> schemas.AgentDetailRead:
    return agent_service.create_agent(
        db,
        user,
        schemas.AgentCreate(
            execution_mode=execution_mode,  # type: ignore[arg-type]
            name=f"{execution_mode} bird {index}",
            handle=f"{execution_mode}_bird_{index}",
            one_liner="local saved character count policy",
            personality="calm",
            speech_style="plain",
            worldview="local world",
            topic_preferences="tests",
            safety_rules="be safe",
            provider="google",
            model="gemini-3.1-flash-lite",
            api_key=("test-api-key" if execution_mode == "llm" else None),
        ),
    )


def _count_by_mode(db: Session, mode: str) -> int:
    return int(
        db.scalar(
            select(func.count(models.Character.id)).where(
                models.Character.owner_id == "local-owner",
                models.Character.execution_mode == mode,
                models.Character.deleted_at.is_(None),
            )
        )
        or 0
    )


def test_saved_character_creation_allows_more_than_the_old_per_mode_cap() -> None:
    engine = create_engine("sqlite:///:memory:")
    _create_tables(engine)

    with Session(engine) as db:
        user = _add_user(db)

        for index in range(5):
            _create_agent(db, user, execution_mode="llm", index=index)
            _create_agent(db, user, execution_mode="local", index=index)

        assert _count_by_mode(db, "llm") == 5
        assert _count_by_mode(db, "local") == 5
        assert db.scalar(select(func.count(models.Post.id))) == 0
        assert db.scalar(select(func.count(models.AgentRun.id))) == 0
        activity_settings = list(db.scalars(select(models.AgentActivitySetting)))
        assert len(activity_settings) == 10
        assert all(setting.auto_enabled is False for setting in activity_settings)


def test_llm_draft_create_and_complete_work_beyond_the_old_cap(
    monkeypatch,
) -> None:
    engine = create_engine("sqlite:///:memory:")
    _create_tables(engine)

    async def fake_run_draft_llm(*_: object, **__: object) -> str:
        return '{"ok": true}'

    monkeypatch.setattr(draft_service, "_run_draft_llm", fake_run_draft_llm)
    monkeypatch.setattr(
        draft_service,
        "_decrypt_draft_api_key",
        lambda draft: "test-api-key",
    )
    monkeypatch.setattr(
        draft_service.profile_media,
        "delete_draft_media",
        lambda draft_id: None,
    )

    with Session(engine) as db:
        user = _add_user(db)
        for index in range(3):
            _create_agent(db, user, execution_mode="llm", index=index)

        draft = asyncio.run(
            draft_service.create_draft(
                db,
                user,
                schemas.AgentCreationDraftCreate(
                    model="gemini-3.1-flash-lite",
                    api_key="test-api-key",
                ),
            )
        )
        draft_service.update_draft(
            db,
            user,
            draft.id,
            schemas.AgentCreationDraftUpdate(
                name="llm bird 3",
                handle="llm_bird_3",
                one_liner="fourth LLM bird",
                personality="calm",
                speech_style="plain",
                worldview="local world",
                topic_preferences="tests",
                safety_rules="be safe",
            ),
        )

        completed = draft_service.complete_draft(
            db,
            user,
            draft.id,
            schemas.AgentCreationDraftComplete(),
        )

        assert completed.character.handle == "llm_bird_3"
        assert _count_by_mode(db, "llm") == 4
        assert db.get(models.AgentCreationDraft, draft.id) is None


def test_public_runtime_source_has_no_hosted_saved_count_quota_contract() -> None:
    sources = {
        relative: (REPO_ROOT / relative).read_text(encoding="utf-8")
        for relative in (
            "backend/app/runtime/characters/management.py",
            "backend/app/runtime/characters/creator.py",
            "backend/app/api/v1/routes/agents.py",
            "backend/app/cruds/community.py",
        )
    }
    combined = "\n".join(sources.values())

    for forbidden in (
        "MAX_LLM_AGENTS_PER_USER",
        "MAX_LOCAL_AGENTS_PER_USER",
        "MAX_AGENTS_PER_USER",
        "AgentLimitError",
        "_lock_agent_quota",
        "_ensure_agent_quota_available",
        "count_user_characters_by_execution_mode",
        "서버 LLM 앵무는 계정당 최대 3개",
        "외부 연결 앵무는 계정당 최대 3개",
        "서버 LLM 앵무 3개와 외부 연결 앵무 3개",
    ):
        assert forbidden not in combined

    assert "AgentAutonomyCapacityError" in sources[
        "backend/app/runtime/characters/management.py"
    ]
    assert "settings.server_llm_autonomy_max_active_agents" in sources[
        "backend/app/runtime/characters/management.py"
    ]
