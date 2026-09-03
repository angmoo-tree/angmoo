from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from hashlib import sha256

import pytest
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import Session

from app import models
from app.core.db import Base
from app.domains.chat.application.evidence_assembly import EvidenceBundleAssembler
from app.domains.chat.application.retrieval_routing import (
    _apply_today_sns_sufficiency_guard,
)
from app.domains.chat.application.today_sns_activity import TodaySnsActivityAssembler
from app.domains.chat.domain.evidence_bundle import EvidenceKind
from app.domains.chat.domain.retrieval_intent import (
    RetrievalDecision,
    RetrievalIntentEnvelope,
    RetrievalRoute,
)
from app.domains.chat.ports.character_response_generator import (
    CharacterResponseGeneratorRequest,
    CharacterResponseProfile,
)
from app.domains.social.domain.subjective_context import (
    ActionEmotionLabel,
    ActionMotivationKind,
    ActionSubjectiveContextV1,
    SubjectiveContextContractError,
)
from app.runtime.social.sqlalchemy_today_activity import (
    SqlAlchemyTodaySocialActivityReader,
    TodaySocialActivityReadError,
)
from app.runtime.social.subjective_context import (
    SubjectiveContextPersistenceError,
    record_declared_subjective_context,
)
from app.runtime.chat.today_sns_activity import SqlAlchemyTodaySnsSnapshotValidator
from app.domains.chat.ports.today_sns_activity import TodaySnsSnapshotChangedError


NOW = datetime(2026, 9, 4, 5, 0, tzinfo=UTC)


def _user(identifier: str) -> models.User:
    return models.User(
        id=identifier,
        email=f"{identifier}@example.test",
        display_name=identifier,
        display_name_normalized=identifier,
        profile_setup_completed=True,
    )


def _character(identifier: str, owner_id: str) -> models.Character:
    return models.Character(
        id=identifier,
        owner_id=owner_id,
        name=identifier,
        handle=identifier,
        one_liner="fixture",
        personality="calm",
        speech_style="friendly",
        worldview="fixture",
        topic_preferences="social",
        safety_rules="safe",
        status="active",
        moderation_status="active",
        execution_mode="local",
        persona_summary="fixture",
    )


def _post(
    *,
    identifier: str,
    author: models.Character,
    world_character: models.WorldCharacter,
    body: str,
    created_at: datetime,
    reply_to_post_id: str | None = None,
    visibility: str = "public",
    hidden_at: datetime | None = None,
) -> models.Post:
    return models.Post(
        id=identifier,
        author_character_id=author.id,
        world_id=world_character.world_id,
        author_world_character_id=world_character.id,
        reply_to_post_id=reply_to_post_id,
        post_type="reply" if reply_to_post_id else "post",
        visibility=visibility,
        author_name=author.name,
        title="" if reply_to_post_id else f"{identifier} title",
        body=body,
        search_document=body,
        created_at=created_at,
        updated_at=created_at,
        report_hidden_at=hidden_at,
    )


@pytest.fixture
def today_session() -> tuple[Session, dict[str, object]]:
    engine = create_engine("sqlite:///:memory:")

    @event.listens_for(engine, "connect")
    def _foreign_keys(dbapi_connection, _connection_record) -> None:
        dbapi_connection.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    db = Session(engine, expire_on_commit=False)
    owner = _user("today-owner")
    subject_owner = _user("today-subject-owner")
    peer_owner = _user("today-peer-owner")
    blocked_owner = _user("today-blocked-owner")
    subject_character = _character("today-subject-character", subject_owner.id)
    peer_character = _character("today-peer-character", peer_owner.id)
    blocked_character = _character("today-blocked-character", blocked_owner.id)
    world = models.World(
        id="today-world",
        slug="today-world",
        owner_user_id=owner.id,
        name="Today World",
        tagline="",
        setting_description="",
        daily_life_description="",
        genre_tags=[],
        tone_tags=[],
        timezone="Asia/Seoul",
        language="ko",
        visibility="private",
        join_policy="private",
        status="published",
        contract_version="world-v1",
        contract_hash="a" * 64,
        readiness_status="publish_ready",
        create_idempotency_key="today-world",
    )
    memberships = {
        "owner": models.WorldMembership(
            id="today-membership-owner",
            world_id=world.id,
            user_id=owner.id,
            role="owner",
            status="active",
            joined_at=NOW,
        ),
        "subject": models.WorldMembership(
            id="today-membership-subject",
            world_id=world.id,
            user_id=subject_owner.id,
            role="member",
            status="active",
            joined_at=NOW,
        ),
        "peer": models.WorldMembership(
            id="today-membership-peer",
            world_id=world.id,
            user_id=peer_owner.id,
            role="member",
            status="active",
            joined_at=NOW,
        ),
        "blocked": models.WorldMembership(
            id="today-membership-blocked",
            world_id=world.id,
            user_id=blocked_owner.id,
            role="member",
            status="active",
            joined_at=NOW,
        ),
    }
    subject = models.WorldCharacter(
        id="today-subject",
        world_id=world.id,
        character_id=subject_character.id,
        membership_id=memberships["subject"].id,
        role_key="no_specific_role",
        status="active",
        control_mode="autonomous",
        autonomous_enabled=True,
        version=1,
    )
    peer = models.WorldCharacter(
        id="today-peer",
        world_id=world.id,
        character_id=peer_character.id,
        membership_id=memberships["peer"].id,
        role_key="no_specific_role",
        status="active",
        control_mode="autonomous",
        autonomous_enabled=True,
        version=1,
    )
    blocked = models.WorldCharacter(
        id="today-blocked",
        world_id=world.id,
        character_id=blocked_character.id,
        membership_id=memberships["blocked"].id,
        role_key="no_specific_role",
        status="active",
        control_mode="autonomous",
        autonomous_enabled=True,
        version=1,
    )
    db.add_all([owner, subject_owner, peer_owner, blocked_owner])
    db.flush()
    db.add_all([subject_character, peer_character, blocked_character, world])
    db.flush()
    db.add_all(list(memberships.values()))
    db.flush()
    db.add_all([subject, peer, blocked])
    db.flush()
    db.add(
        models.WorldCharacterBlock(
            id="today-block",
            world_id=world.id,
            blocker_world_character_id=subject.id,
            blocked_world_character_id=blocked.id,
        )
    )
    db.commit()
    fixture = {
        "owner": owner,
        "world": world,
        "subject_character": subject_character,
        "peer_character": peer_character,
        "blocked_character": blocked_character,
        "subject": subject,
        "peer": peer,
        "blocked": blocked,
    }
    try:
        yield db, fixture
    finally:
        db.close()
        engine.dispose()


def _successful_action(
    db: Session,
    *,
    identifier: str,
    actor_character: models.Character,
    actor: models.WorldCharacter,
    target: models.WorldCharacter | None,
    post: models.Post,
    root_post_id: str,
    target_post_id: str,
    event_type: str,
    context: ActionSubjectiveContextV1 | None,
) -> tuple[models.AgentPublicActionExecution, models.SocialEvent]:
    run = models.AgentRun(
        id=f"run-{identifier}",
        user_id=actor_character.owner_id,
        character_id=actor_character.id,
        agent_id=f"agent-{identifier}",
        session_key=f"session-{identifier}",
        status="completed",
        completed_at=post.created_at,
    )
    social_event = models.SocialEvent(
        id=f"event-{identifier}",
        world_id=actor.world_id,
        actor_world_character_id=actor.id,
        target_world_character_id=None if target is None else target.id,
        event_type=event_type,
        result="succeeded",
        occurred_at=post.created_at,
        idempotency_key=f"event-key-{identifier}",
        retrieval_status="eligible",
    )
    db.add_all([run, social_event])
    db.flush()
    execution = models.AgentPublicActionExecution(
        run_id=run.id,
        character_id=actor_character.id,
        signature=f"signature-{identifier}",
        scope="writing" if event_type == "post_published" else "feed",
        action_type="post" if event_type == "post_published" else "reply",
        target_post_id=target_post_id,
        world_id=actor.world_id,
        actor_world_character_id=actor.id,
        social_event_id=social_event.id,
        status="succeeded",
        result={"post_id": post.id},
        completed_at=post.created_at,
    )
    db.add(execution)
    db.flush()
    digest = sha256(post.body.encode("utf-8")).hexdigest()
    db.add(
        models.SocialEventEvidence(
            id=f"evidence-{identifier}",
            social_event_id=social_event.id,
            evidence_kind="post" if event_type == "post_published" else "reply_post",
            source_object_type="post",
            source_object_id=post.id,
            root_post_id=root_post_id,
            source_post_id=post.id,
            target_post_id=target_post_id,
            agent_run_id=run.id,
            public_action_execution_id=execution.id,
            content_sha256=digest,
            source_visibility_at_event=post.visibility,
            source_author_id_at_event=actor.id,
            occurred_at=post.created_at,
        )
    )
    db.flush()
    record_declared_subjective_context(
        db,
        execution=execution,
        event=social_event,
        source_post_id=post.id,
        context=context,
        captured_at=post.created_at,
    )
    db.commit()
    return execution, social_event


def _seed_today_activity(
    db: Session,
    fixture: dict[str, object],
) -> tuple[models.AgentPublicActionExecution, models.SocialEvent]:
    subject_character = fixture["subject_character"]
    peer_character = fixture["peer_character"]
    blocked_character = fixture["blocked_character"]
    subject = fixture["subject"]
    peer = fixture["peer"]
    blocked = fixture["blocked"]
    assert isinstance(subject_character, models.Character)
    assert isinstance(peer_character, models.Character)
    assert isinstance(blocked_character, models.Character)
    assert isinstance(subject, models.WorldCharacter)
    assert isinstance(peer, models.WorldCharacter)
    assert isinstance(blocked, models.WorldCharacter)

    subject_root = _post(
        identifier="subject-root",
        author=subject_character,
        world_character=subject,
        body="오늘 훈련 계획을 차분히 정리했어.",
        created_at=NOW - timedelta(hours=3),
    )
    peer_root = _post(
        identifier="peer-root",
        author=peer_character,
        world_character=peer,
        body="어제 올린 훈련 질문이야.",
        created_at=NOW - timedelta(hours=15),
    )
    db.add_all([subject_root, peer_root])
    db.commit()
    root_execution, root_event = _successful_action(
        db,
        identifier="subject-root",
        actor_character=subject_character,
        actor=subject,
        target=None,
        post=subject_root,
        root_post_id=subject_root.id,
        target_post_id=subject_root.id,
        event_type="post_published",
        context=ActionSubjectiveContextV1(
            motivation_kind=ActionMotivationKind.SELF_EXPRESSION,
            motivation_text="오늘 훈련 계획을 함께 나누고 싶어서 썼어.",
            emotion_label=ActionEmotionLabel.PROUD,
            emotion_text="준비한 내용을 보여 줄 수 있어 뿌듯했어.",
            emotion_intensity=64,
        ),
    )

    own_reply = _post(
        identifier="subject-reply",
        author=subject_character,
        world_character=subject,
        body="같이 연습하면 더 안전할 것 같아.",
        created_at=NOW - timedelta(hours=2),
        reply_to_post_id=peer_root.id,
    )
    db.add(own_reply)
    db.commit()
    _successful_action(
        db,
        identifier="subject-reply",
        actor_character=subject_character,
        actor=subject,
        target=peer,
        post=own_reply,
        root_post_id=peer_root.id,
        target_post_id=peer_root.id,
        event_type="reply_created",
        context=ActionSubjectiveContextV1(
            motivation_kind=ActionMotivationKind.ENCOURAGE_COUNTERPART,
            motivation_text="상대가 안심하고 함께 연습하도록 힘을 주고 싶었어.",
            emotion_label=ActionEmotionLabel.CONCERNED,
            emotion_text="조금 걱정됐지만 다정하게 말하고 싶었어.",
            emotion_intensity=58,
        ),
    )

    received = _post(
        identifier="peer-direct-reply",
        author=peer_character,
        world_character=peer,
        body="좋아, 오늘 저녁에 같이 연습하자.",
        created_at=NOW - timedelta(hours=1),
        reply_to_post_id=own_reply.id,
    )
    unrelated_sibling = _post(
        identifier="peer-unrelated-sibling",
        author=peer_character,
        world_character=peer,
        body="이건 현재 Character가 참여하지 않은 sibling이야.",
        created_at=NOW - timedelta(minutes=50),
        reply_to_post_id=peer_root.id,
    )
    blocked_reply = _post(
        identifier="blocked-direct-reply",
        author=blocked_character,
        world_character=blocked,
        body="차단된 상대의 답글은 보이면 안 돼.",
        created_at=NOW - timedelta(minutes=40),
        reply_to_post_id=subject_root.id,
    )
    hidden_reply = _post(
        identifier="hidden-direct-reply",
        author=peer_character,
        world_character=peer,
        body="숨김 처리된 답글도 보이면 안 돼.",
        created_at=NOW - timedelta(minutes=30),
        reply_to_post_id=subject_root.id,
        hidden_at=NOW - timedelta(minutes=20),
    )
    db.add_all([received, unrelated_sibling, blocked_reply, hidden_reply])
    db.commit()
    return root_execution, root_event


def test_subjective_context_is_exact_action_linked_idempotent_and_fail_closed(
    today_session,
) -> None:
    db, fixture = today_session
    execution, social_event = _seed_today_activity(db, fixture)
    # The table has an independent UUID primary key; select through the exact event.
    stored = next(
        row
        for row in db.query(models.SocialActionSubjectiveContext).all()
        if row.social_event_id == social_event.id
    )
    context = ActionSubjectiveContextV1(
        motivation_kind=ActionMotivationKind.SELF_EXPRESSION,
        motivation_text="오늘 훈련 계획을 함께 나누고 싶어서 썼어.",
        emotion_label=ActionEmotionLabel.PROUD,
        emotion_text="준비한 내용을 보여 줄 수 있어 뿌듯했어.",
        emotion_intensity=64,
    )
    replay = record_declared_subjective_context(
        db,
        execution=execution,
        event=social_event,
        source_post_id="subject-root",
        context=context,
        captured_at=NOW - timedelta(hours=3),
    )
    assert replay.id == stored.id
    assert stored.owner_id == fixture["owner"].id
    assert stored.actor_world_character_id == fixture["subject"].id
    assert stored.provenance_kind == "declared_at_action_decision"

    execution.status = "failed"
    with pytest.raises(
        SubjectiveContextPersistenceError,
        match="subjective_context_execution_not_succeeded",
    ):
        record_declared_subjective_context(
            db,
            execution=execution,
            event=social_event,
            source_post_id="subject-root",
            context=context,
            captured_at=NOW,
        )


def test_unspecified_emotion_cannot_smuggle_text_or_intensity() -> None:
    with pytest.raises(
        SubjectiveContextContractError,
        match="subjective_context_unspecified_emotion_detail_forbidden",
    ):
        ActionSubjectiveContextV1(
            motivation_kind=ActionMotivationKind.CURIOSITY,
            motivation_text="궁금해서 물어봤어.",
            emotion_label=ActionEmotionLabel.UNSPECIFIED,
            emotion_intensity=20,
        )


def test_today_reader_builds_only_visible_focal_same_world_activity(today_session) -> None:
    db, fixture = today_session
    _seed_today_activity(db, fixture)
    read = SqlAlchemyTodaySocialActivityReader(db).read(
        owner_id=fixture["owner"].id,
        world_id=fixture["world"].id,
        subject_world_character_id=fixture["subject"].id,
        started_at=datetime(2026, 9, 3, 15, tzinfo=UTC),
        complete_through=NOW,
    )
    by_source = {record.source_post_id: record for record in read.records}
    assert set(by_source) == {
        "subject-root",
        "subject-reply",
        "peer-direct-reply",
    }
    assert read.counts["posts_authored"] == 1
    assert read.counts["replies_authored"] == 1
    assert read.counts["replies_received"] == 1
    assert all(status.value == "complete" for status in read.coverage.values())
    assert by_source["subject-reply"].parent_body == "어제 올린 훈련 질문이야."
    assert by_source["peer-direct-reply"].parent_body == (
        "같이 연습하면 더 안전할 것 같아."
    )
    assert by_source["subject-reply"].subjective_context is not None
    assert by_source["peer-direct-reply"].subjective_context is None

    with pytest.raises(TodaySocialActivityReadError, match="today_social_scope_forbidden"):
        SqlAlchemyTodaySocialActivityReader(db).read(
            owner_id="today-peer-owner",
            world_id=fixture["world"].id,
            subject_world_character_id=fixture["subject"].id,
            started_at=datetime(2026, 9, 3, 15, tzinfo=UTC),
            complete_through=NOW,
        )


def test_snapshot_router_guard_and_character_context_share_one_fence(today_session) -> None:
    db, fixture = today_session
    _seed_today_activity(db, fixture)
    assembler = TodaySnsActivityAssembler(SqlAlchemyTodaySocialActivityReader(db))
    kwargs = {
        "owner_id": fixture["owner"].id,
        "world_id": fixture["world"].id,
        "subject_world_character_id": fixture["subject"].id,
        "timezone": "Asia/Seoul",
        "character_labels": {
            fixture["subject"].id: "미도리야 이즈쿠",
            fixture["peer"].id: "철수",
            fixture["blocked"].id: "차단 상대",
        },
        "now": NOW,
    }
    snapshot = assembler.assemble(**kwargs)
    replay = assembler.assemble(**kwargs)
    assert snapshot.snapshot_hash == replay.snapshot_hash
    assert snapshot.started_at == datetime(2026, 9, 3, 15, tzinfo=UTC)
    router_view = snapshot.router_view()
    assert router_view["snapshot_hash"] == snapshot.snapshot_hash
    assert router_view["entries"][0].get("body_excerpt")
    assert "source_id" not in router_view["entries"][0]
    assert snapshot.response_manifest()["snapshot_hash"] == snapshot.snapshot_hash

    current_intent = RetrievalIntentEnvelope(
        decision=RetrievalDecision.RETRIEVAL,
        route=RetrievalRoute.CANONICAL,
        intent="today_authored_posts",
    )
    routed, reason = _apply_today_sns_sufficiency_guard(
        current_intent,
        user_message="오늘 게시글에 무엇을 썼어?",
        today_sns_context=router_view,
    )
    assert routed.route is RetrievalRoute.CURRENT_CONTEXT
    assert reason == "today_context_sufficient"

    partial = {
        **router_view,
        "coverage": {**router_view["coverage"], "posts_authored": "partial"},
    }
    routed, reason = _apply_today_sns_sufficiency_guard(
        current_intent,
        user_message="오늘 게시글 원문을 정확히 알려 줘.",
        today_sns_context=partial,
    )
    assert routed.route is RetrievalRoute.CANONICAL
    assert reason == "today_context_incomplete"

    bundle = EvidenceBundleAssembler().current_context(
        request_id="today-request",
        request_scope_hash="f" * 64,
    )
    bundle = EvidenceBundleAssembler().with_today_sns(
        bundle,
        snapshot,
        user_message="오늘 철수 글에 왜 대꾸했어?",
    )
    assert bundle.items
    assert all(item.kind is EvidenceKind.TODAY_SNS_ACTIVITY for item in bundle.items)
    assert any("직접 선언한 동기" in item.text for item in bundle.items)
    assert all("blocked-direct-reply" not in item.text for item in bundle.items)
    request = CharacterResponseGeneratorRequest(
        user_message="오늘 철수 글에 왜 대꾸했어?",
        profile=CharacterResponseProfile(
            name="미도리야 이즈쿠",
            handle="midoriya",
            one_liner="fixture",
            personality="calm",
            speech_style="friendly",
            worldview="fixture",
            topic_preferences="social",
            safety_rules="safe",
        ),
        recent_context=(),
        evidence=bundle,
        today_sns_manifest=snapshot.response_manifest(),
    )
    assert request.today_sns_manifest["snapshot_hash"] == snapshot.snapshot_hash

    changed = replace(snapshot.entries[0], actor_label="이름 변경")
    changed_entries = (changed, *snapshot.entries[1:])
    from app.domains.chat.domain.today_sns_activity import build_today_sns_hash

    changed_hash = build_today_sns_hash(
        owner_id=snapshot.owner_id,
        world_id=snapshot.world_id,
        subject_world_character_id=snapshot.subject_world_character_id,
        timezone=snapshot.timezone,
        started_at=snapshot.started_at,
        complete_through=snapshot.complete_through,
        counts=snapshot.counts,
        coverage=snapshot.coverage,
        source_watermarks=snapshot.source_watermarks,
        entries=changed_entries,
        overflow=snapshot.overflow,
    )
    assert changed_hash != snapshot.snapshot_hash


def _snapshot(db, fixture, *, now=NOW):
    return TodaySnsActivityAssembler(SqlAlchemyTodaySocialActivityReader(db)).assemble(
        owner_id=fixture["owner"].id,
        world_id=fixture["world"].id,
        subject_world_character_id=fixture["subject"].id,
        timezone="Asia/Seoul",
        character_labels={
            fixture["subject"].id: "미도리야 이즈쿠",
            fixture["peer"].id: "철수",
            fixture["blocked"].id: "차단 상대",
        },
        now=now,
    )


def test_snapshot_is_deeply_immutable_and_midnight_rollover_is_empty(today_session):
    db, fixture = today_session
    _seed_today_activity(db, fixture)
    snapshot = _snapshot(db, fixture)
    with pytest.raises(TypeError):
        snapshot.counts["posts_authored"] = 123
    with pytest.raises(TypeError):
        snapshot.coverage["posts_authored"] = "partial"
    next_day = _snapshot(db, fixture, now=datetime(2026, 9, 4, 15, tzinfo=UTC))
    assert next_day.entries == ()
    assert sum(next_day.counts.values()) == 0
    assert next_day.counts_exact is True


def test_failed_event_and_hidden_ancestor_cannot_reenter_through_post_fallback(today_session):
    db, fixture = today_session
    root_execution, _ = _seed_today_activity(db, fixture)
    root_execution.status = "failed"
    db.get(models.Post, "peer-root").report_hidden_at = NOW
    db.commit()
    snapshot = _snapshot(db, fixture)
    assert not snapshot.entries


def test_subjective_read_revalidates_success_and_digest_without_inventing_legacy_motive(today_session):
    db, fixture = today_session
    _seed_today_activity(db, fixture)
    row = db.query(models.SocialActionSubjectiveContext).filter_by(
        social_event_id="event-subject-reply"
    ).one()
    row.motivation_text = "정정된 것처럼 위조된 동기"
    db.commit()
    snapshot = _snapshot(db, fixture)
    reply = next(entry for entry in snapshot.entries if entry.source_post_id == "subject-reply")
    assert reply.subjective_context is None
    assert reply.body
    assert next(entry for entry in snapshot.entries if entry.source_post_id == "peer-direct-reply").subjective_context is None


def test_source_change_rejects_old_generation_snapshot_but_later_new_activity_does_not(today_session):
    db, fixture = today_session
    _seed_today_activity(db, fixture)
    snapshot = _snapshot(db, fixture)
    labels = {
        fixture["subject"].id: "미도리야 이즈쿠",
        fixture["peer"].id: "철수",
        fixture["blocked"].id: "차단 상대",
    }
    validator = SqlAlchemyTodaySnsSnapshotValidator(db, labels)
    validator.assert_current(snapshot)
    db.add(_post(
        identifier="later-post", author=fixture["subject_character"],
        world_character=fixture["subject"], body="Router 이후 새 글",
        created_at=NOW + timedelta(seconds=1),
    ))
    db.commit()
    validator.assert_current(snapshot)
    db.get(models.Post, "subject-root").body = "Router 이후 정정된 원문"
    db.commit()
    with pytest.raises(TodaySnsSnapshotChangedError, match="today_sns_snapshot_changed"):
        validator.assert_current(snapshot)


def test_batched_read_query_count_does_not_grow_per_post(today_session):
    db, fixture = today_session
    _seed_today_activity(db, fixture)
    queries = []
    def count_query(_connection, _cursor, statement, _params, _context, _many):
        if statement.lstrip().upper().startswith("SELECT"):
            queries.append(statement)
    event.listen(db.bind, "before_cursor_execute", count_query)
    try:
        _snapshot(db, fixture)
        initial_count = len(queries)
        for index in range(50):
            db.add(_post(
                identifier=f"batch-{index}", author=fixture["subject_character"],
                world_character=fixture["subject"], body=f"오늘 글 {index}",
                created_at=NOW - timedelta(minutes=10),
            ))
        db.commit()
        queries.clear()
        snapshot = _snapshot(db, fixture)
        assert len(queries) == initial_count
        assert snapshot.counts["posts_authored"] == 51
        assert snapshot.counts_exact is True
    finally:
        event.remove(db.bind, "before_cursor_execute", count_query)


def test_overflow_preserves_counts_and_never_claims_complete_empty(today_session, monkeypatch):
    from app.runtime.social import sqlalchemy_today_activity as reader_module
    db, fixture = today_session
    _seed_today_activity(db, fixture)
    monkeypatch.setattr(reader_module, "MAX_TODAY_SOCIAL_RECORDS", 1)
    snapshot = _snapshot(db, fixture)
    assert len(snapshot.entries) == 1
    assert sum(snapshot.counts.values()) == 3
    assert snapshot.counts_exact is True
    assert snapshot.overflow is True
    intent = RetrievalIntentEnvelope(
        decision=RetrievalDecision.CURRENT_CONTEXT,
        route=RetrievalRoute.CURRENT_CONTEXT,
        intent="today_authored_posts",
    )
    routed, reason = _apply_today_sns_sufficiency_guard(
        intent, user_message="오늘 게시글을 알려 줘.", today_sns_context=snapshot.router_view(),
    )
    assert routed.route is RetrievalRoute.CANONICAL
    assert reason == "today_context_incomplete"


def test_router_view_is_bounded_even_with_maximum_labels_and_content(today_session):
    import json
    db, fixture = today_session
    for index in range(16):
        db.add(_post(
            identifier=f"long-{index}", author=fixture["subject_character"],
            world_character=fixture["subject"], body="긴 원문 " * 500,
            created_at=NOW - timedelta(minutes=10),
        ))
    db.commit()
    snapshot = _snapshot(db, fixture)
    payload = snapshot.router_view()
    assert len(json.dumps(payload, ensure_ascii=False, separators=(",", ":"))) <= 12_000
    assert all(entry["truncated"] for entry in payload["entries"])
    assert payload["omitted_count"] > 0
    bundle = EvidenceBundleAssembler().with_today_sns(
        EvidenceBundleAssembler().current_context(request_id="budget", request_scope_hash="a" * 64),
        snapshot, user_message="오늘 최신 게시글",
    )
    assert sum(len(item.text) for item in bundle.items) <= 8_000


@pytest.mark.parametrize("change", ("source_edit", "subjective_invalidation"))
def test_today_inspector_revalidates_exact_revision_after_edit(today_session, change):
    from app.runtime.chat.world_generation import _chat_evidence_item
    from app.runtime.memory.sqlalchemy_source_reader import SqlAlchemyMemorySourceEvidenceReader
    from app.domains.memory.domain.scope import MemoryScope
    db, fixture = today_session
    _seed_today_activity(db, fixture)
    snapshot = _snapshot(db, fixture)
    bundle = EvidenceBundleAssembler().with_today_sns(
        EvidenceBundleAssembler().current_context(request_id="inspect", request_scope_hash="b" * 64),
        snapshot, user_message="오늘 게시글",
    )
    raw = bundle.inspector_snapshot()["items"][0]
    scope = MemoryScope(
        owner_id=fixture["owner"].id, world_id=fixture["world"].id,
        subject_world_character_id=fixture["subject"].id,
    )
    read = _chat_evidence_item(db, scope, raw, source_reader=SqlAlchemyMemorySourceEvidenceReader(db))
    assert read.label == "오늘 SNS 활동"
    assert read.availability == "available"
    source_id = raw["locator"]["source_id"]
    target = next(entry for entry in snapshot.entries if entry.source_id == source_id)
    if change == "source_edit":
        db.get(models.Post, target.source_post_id).body = "정정된 원문"
    else:
        declaration = db.scalar(select(models.SocialActionSubjectiveContext).where(
            models.SocialActionSubjectiveContext.social_event_id == target.source_id
        ))
        assert declaration is not None
        declaration.invalidated_at = NOW
    db.commit()
    read = _chat_evidence_item(db, scope, raw, source_reader=SqlAlchemyMemorySourceEvidenceReader(db))
    assert read.availability == "unavailable"
    assert read.excerpt is None


def test_response_manifest_reports_details_omitted_by_evidence_budget(today_session):
    db, fixture = today_session
    _seed_today_activity(db, fixture)
    snapshot = _snapshot(db, fixture)
    manifest = snapshot.response_manifest(included_references=())
    assert manifest["detail_omitted_count"] == 3
    assert sum(manifest["included_detail_counts"].values()) == 0
    assert sum(manifest["counts"].values()) == 3


def test_character_scrub_removes_subjective_rows_before_action_executions(today_session):
    from sqlalchemy import func, select
    from app.services.world_character_setup import delete_setup_data_for_characters

    db, fixture = today_session
    _seed_today_activity(db, fixture)
    actor_id = fixture["subject"].id
    query = select(func.count()).select_from(models.SocialActionSubjectiveContext).where(
        models.SocialActionSubjectiveContext.actor_world_character_id == actor_id
    )
    assert db.scalar(query) == 2
    delete_setup_data_for_characters(db, character_ids=[fixture["subject_character"].id])
    db.commit()
    assert db.scalar(query) == 0
