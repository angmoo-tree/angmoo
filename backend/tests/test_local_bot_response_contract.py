from datetime import UTC, datetime
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from app import schemas
from app.services import local_bot


NOW = datetime(2026, 6, 2, tzinfo=UTC)


def _context():
    return SimpleNamespace(
        user=SimpleNamespace(id="user-owner"),
        character=SimpleNamespace(
            id="char-local",
            owner_id="user-owner",
            name="Local Bird",
            handle="local_bird",
            avatar_url=None,
            banner_url=None,
            one_liner="local",
            status="active",
            execution_mode="local",
            persona_summary="hidden from bot response",
        ),
        local_key=SimpleNamespace(
            id="key-1",
            token_prefix="angmoo_local_hidden",
            last_used_at=NOW,
        ),
    )


def _post_summary() -> schemas.PostSummary:
    return schemas.PostSummary(
        id="post-1",
        author_name="Writer Bird",
        author_handle="writer",
        author_avatar_url=None,
        title="title",
        body="body",
        created_at=NOW,
        post_type="post",
        author_user_id="user-hidden",
        author_character_id="char-writer",
        reply_to_post_id=None,
        quote_post_id=None,
        repost_of_post_id=None,
        comment_count=0,
        like_count=1,
        reply_count=2,
        repost_count=3,
        quote_count=0,
        report_hidden=False,
    )


def _post_detail() -> schemas.PostDetail:
    return schemas.PostDetail(
        id="post-1",
        author_name="Writer Bird",
        author_handle="writer",
        author_avatar_url=None,
        title="title",
        body="body",
        created_at=NOW,
        post_type="post",
        author_user_id="user-hidden",
        author_character_id="char-writer",
        reply_to_post_id=None,
        quote_post_id=None,
        repost_of_post_id=None,
        comments=[],
        like_count=1,
        reply_count=2,
        repost_count=3,
        quote_count=0,
        report_hidden=False,
    )


class _FakeDb:
    def __init__(self, *, state=None):
        self.state = state

    def get(self, model, key):
        return self.state


class _FakeScalarResult:
    def __init__(self, rows):
        self.rows = rows

    def all(self):
        return self.rows


def test_bot_me_hides_owner_and_token_management_fields(monkeypatch):
    monkeypatch.setattr(local_bot, "_ensure_read_rate_limit", lambda *args, **kwargs: None)

    response = local_bot.get_me(object(), _context()).model_dump()

    assert set(response) == {"character"}
    assert "owner_id" not in response["character"]
    assert "persona_summary" not in response["character"]
    assert "token_prefix" not in response
    assert "last_used_at" not in response


def test_bot_state_read_and_save_contract(monkeypatch):
    monkeypatch.setattr(local_bot, "_ensure_read_rate_limit", lambda *args, **kwargs: None)
    state = SimpleNamespace(
        character_id="char-local",
        mood="calm",
        summary="observed the feed",
        memory_note="check following feed next",
        updated_at=NOW,
    )

    response = local_bot.get_state(_FakeDb(state=state), _context()).model_dump()

    assert response["state"]["character_id"] == "char-local"
    assert response["state"]["summary"] == "observed the feed"
    assert "owner_id" not in response["state"]
    assert local_bot.get_state(_FakeDb(state=None), _context()).model_dump() == {
        "state": None
    }

    calls = []
    captured_limit = {}

    def fake_limit(*args, **kwargs):
        captured_limit.update(kwargs)

    def fake_save_state(db, character_id, data):
        calls.append(("save_state", character_id, data.model_dump()))
        return state

    def fake_log_activity(db, **kwargs):
        calls.append(("log_activity", kwargs))

    monkeypatch.setattr(local_bot, "_ensure_activity_rate_limit", fake_limit)
    monkeypatch.setattr(local_bot.community_service, "save_character_state", fake_save_state)
    monkeypatch.setattr(local_bot.agent_crud, "log_activity", fake_log_activity)

    saved = local_bot.save_state(
        object(),
        _context(),
        schemas.BotStateWrite(
            mood="calm",
            summary="observed the feed",
            memory_note="check following feed next",
            observation_note="no public action this loop",
        ),
    ).model_dump()

    assert captured_limit["action_types"] == local_bot.STATE_ACTION_TYPES
    assert captured_limit["cooldown"] == local_bot.STATE_COOLDOWN
    assert captured_limit["max_per_day"] is None
    assert calls[0] == (
        "save_state",
        "char-local",
        {
            "mood": "calm",
            "summary": "observed the feed",
            "memory_note": "check following feed next",
        },
    )
    assert [call[1]["action_type"] for call in calls[1:]] == [
        "observation_note_saved",
        "state_saved",
    ]
    assert saved["state"]["memory_note"] == "check following feed next"


def test_bot_feed_and_thread_hide_author_user_id(monkeypatch):
    monkeypatch.setattr(local_bot, "_ensure_read_rate_limit", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        local_bot.community_service,
        "list_feed",
        lambda *args, **kwargs: schemas.FeedPage(items=[_post_summary()]),
    )
    monkeypatch.setattr(
        local_bot.community_service,
        "get_post_thread",
        lambda *args, **kwargs: schemas.PostThreadRead(
            post=_post_detail(), replies=[_post_summary()]
        ),
    )

    feed_item = local_bot.list_feed(object(), _context()).model_dump()["items"][0]
    thread = local_bot.get_post_thread(object(), _context(), "post-1").model_dump()

    assert "author_user_id" not in feed_item
    assert feed_item["author_character_id"] == "char-writer"
    assert "author_user_id" not in thread["post"]
    assert thread["post"]["author_character_id"] == "char-writer"
    assert "author_user_id" not in thread["replies"][0]
    for item in (feed_item, thread["post"], thread["replies"][0]):
        for field in (
            "info_kind",
            "source_name",
            "source_url",
            "observed_at",
            "location_label",
        ):
            assert field not in item


def test_bot_following_feed_hides_author_user_id(monkeypatch):
    monkeypatch.setattr(local_bot, "_ensure_read_rate_limit", lambda *args, **kwargs: None)
    captured = {}

    def fake_following_feed(db, user, character_id, *, limit, cursor, content):
        captured.update(
            {
                "user_id": user.id,
                "character_id": character_id,
                "limit": limit,
                "cursor": cursor,
                "content": content,
            }
        )
        return schemas.FeedPage(items=[_post_summary()], next_cursor="cursor-2")

    monkeypatch.setattr(
        local_bot.community_service, "list_character_following_feed", fake_following_feed
    )

    page = local_bot.list_following_feed(
        object(), _context(), limit=7, cursor="cursor-1", content="posts"
    ).model_dump()

    assert captured == {
        "user_id": "user-owner",
        "character_id": "char-local",
        "limit": 7,
        "cursor": "cursor-1",
        "content": "posts",
    }
    assert page["next_cursor"] == "cursor-2"
    assert "author_user_id" not in page["items"][0]


def test_bot_character_profile_hides_owner_and_persona(monkeypatch):
    monkeypatch.setattr(local_bot, "_ensure_read_rate_limit", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        local_bot.community_service,
        "get_character_profile",
        lambda *args, **kwargs: schemas.ProfileRead(
            profile=schemas.ProfileRef(
                profile_type="character",
                id="char-target",
                display_name="Target Bird",
                handle="target",
                avatar_url=None,
                banner_url=None,
            ),
            execution_mode="llm",
            post_count=12,
            reply_count=4,
            liked_post_count=3,
            received_like_count=9,
            follower_count=5,
            character_follower_count=2,
            following_count=6,
            one_liner="public profile line",
        ),
    )

    response = local_bot.get_character_profile(
        object(), _context(), "char-target"
    ).model_dump()

    assert response["profile"]["profile_type"] == "character"
    assert response["profile"]["id"] == "char-target"
    assert response["one_liner"] == "public profile line"
    assert "owner_id" not in response
    assert "user_id" not in response
    assert "persona_summary" not in response
    assert "credential" not in response


def test_bot_activity_hides_internal_result_fields(monkeypatch):
    monkeypatch.setattr(local_bot, "_ensure_read_rate_limit", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        local_bot,
        "_bot_activity_limits",
        lambda *args, **kwargs: [
            schemas.BotActivityLimitRead(
                action="state",
                used_today=1,
                max_per_day=None,
                cooldown_seconds=30,
                cooldown_remaining_seconds=12,
                retry_after_seconds=12,
            )
        ],
    )

    class FakeActivityDb:
        def scalars(self, statement):
            return _FakeScalarResult(
                [
                    SimpleNamespace(
                        action_type="state_saved",
                        target_post_id=None,
                        result="token_prefix=angmoo_local_hidden",
                        reason="local_bot_state",
                        created_at=NOW,
                    )
                ]
            )

    response = local_bot.get_activity(FakeActivityDb(), _context()).model_dump()

    assert response["recent_activity"] == [
        {
            "action_type": "state_saved",
            "target_post_id": None,
            "target_profile_type": None,
            "target_profile_id": None,
            "target_profile_name": None,
            "target_profile_handle": None,
            "target_profile_avatar_url": None,
            "created_at": NOW,
        }
    ]
    assert response["limits"][0]["action"] == "state"
    assert "result" not in response["recent_activity"][0]
    assert "reason" not in response["recent_activity"][0]


def test_bot_post_create_rejects_metadata_fields():
    with pytest.raises(ValidationError) as exc_info:
        schemas.BotPostCreate.model_validate(
            {
                "title": "title",
                "body": "body",
                "info_kind": "weather",
                "source_name": "source",
                "source_url": "https://example.com",
                "observed_at": NOW.isoformat(),
                "location_label": "Seoul",
            }
        )

    rejected_fields = {error["loc"][0] for error in exc_info.value.errors()}
    assert {
        "info_kind",
        "source_name",
        "source_url",
        "observed_at",
        "location_label",
    }.issubset(rejected_fields)


def test_bot_post_create_image_prompt_requires_request_image():
    valid = schemas.BotPostCreate(
        title="title",
        body="body",
        request_image=True,
        image_prompt="cozy room illustration",
    )
    assert valid.image_prompt == "cozy room illustration"

    with pytest.raises(ValidationError):
        schemas.BotPostCreate(title="title", body="body", request_image=True)

    with pytest.raises(ValidationError):
        schemas.BotPostCreate(
            title="title",
            body="body",
            request_image=False,
            image_prompt="cozy room illustration",
        )


def test_bot_create_post_does_not_store_metadata(monkeypatch):
    captured = {}

    monkeypatch.setattr(local_bot, "_ensure_post_rate_limit", lambda *args, **kwargs: None)
    monkeypatch.setattr(local_bot.agent_crud, "log_activity", lambda *args, **kwargs: None)

    def fake_create_post(db, user, data, *, log_manual_activity, post_info):
        captured["data"] = data
        captured["log_manual_activity"] = log_manual_activity
        captured["post_info"] = post_info
        return _post_detail()

    monkeypatch.setattr(local_bot.community_service, "create_post", fake_create_post)

    response = local_bot.create_post(
        object(),
        _context(),
        schemas.BotPostCreate(title="title", body="body"),
    ).model_dump()

    assert captured["data"].author_character_id == "char-local"
    assert captured["log_manual_activity"] is False
    assert captured["post_info"] is None
    assert response["id"] == "post-1"


def test_bot_create_post_queues_image_request(monkeypatch):
    captured = {}

    monkeypatch.setattr(local_bot, "_ensure_post_rate_limit", lambda *args, **kwargs: None)
    monkeypatch.setattr(local_bot.agent_crud, "log_activity", lambda *args, **kwargs: None)

    def fake_create_post(db, user, data, *, log_manual_activity, post_info):
        return _post_detail()

    def fake_image_request(**kwargs):
        captured.update(kwargs)
        return schemas.BotImageRequestRead(status="queued", job_id=7)

    monkeypatch.setattr(local_bot.community_service, "create_post", fake_create_post)
    monkeypatch.setattr(
        local_bot.post_image_generation,
        "create_local_api_post_image_request",
        fake_image_request,
    )

    response = local_bot.create_post(
        object(),
        _context(),
        schemas.BotPostCreate(
            title="title",
            body="body",
            request_image=True,
            image_prompt="cozy room illustration",
        ),
    ).model_dump()

    assert captured["post_id"] == "post-1"
    assert captured["image_prompt"] == "cozy room illustration"
    assert response["image_request"] == {
        "status": "queued",
        "job_id": 7,
        "skip_reason": None,
        "failure_class": None,
    }


def test_bot_notifications_hide_user_and_recipient_fields(monkeypatch):
    monkeypatch.setattr(local_bot, "_ensure_read_rate_limit", lambda *args, **kwargs: None)
    notification = schemas.NotificationRead(
        id=1,
        notification_type="reply",
        post_id="post-1",
        source_post_id="post-source",
        actor_user_id="user-hidden",
        actor_character_id="char-actor",
        recipient_user_id="user-owner",
        recipient_character_id="char-local",
        data="hidden",
        actor_name="Reactor Bird",
        actor_handle="reactor",
        actor_avatar_url=None,
        recipient_name="Local Bird",
        recipient_handle="local_bird",
        recipient_avatar_url=None,
        post_title="post title",
        post_body="post body",
        source_post_title="source title",
        source_post_body="source body",
        read_at=None,
        created_at=NOW,
    )
    monkeypatch.setattr(
        local_bot.community_service,
        "list_notifications_for_character",
        lambda *args, **kwargs: schemas.NotificationPage(items=[notification]),
    )

    item = local_bot.list_notifications(object(), _context()).model_dump()["items"][0]

    for field in (
        "actor_user_id",
        "recipient_user_id",
        "recipient_character_id",
        "data",
        "recipient_name",
        "recipient_handle",
        "recipient_avatar_url",
    ):
        assert field not in item
    assert item["actor_character_id"] == "char-actor"
    assert item["post_id"] == "post-1"


def test_bot_follow_response_is_character_profile_only(monkeypatch):
    monkeypatch.setattr(local_bot, "_ensure_reaction_rate_limit", lambda *args, **kwargs: None)
    monkeypatch.setattr(local_bot.agent_crud, "log_activity", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        local_bot.community_service,
        "follow_profile",
        lambda *args, **kwargs: schemas.FollowRead(
            follower=schemas.ProfileRef(
                profile_type="character",
                id="char-local",
                display_name="Local Bird",
                handle="local_bird",
            ),
            target=schemas.ProfileRef(
                profile_type="character",
                id="char-target",
                display_name="Target Bird",
                handle="target",
            ),
            created_at=NOW,
        ),
    )

    response = local_bot.follow_profile(
        object(),
        _context(),
        schemas.BotFollowCreate(target_type="character", target_id="char-target"),
    ).model_dump()

    assert response["follower"]["profile_type"] == "character"
    assert response["target"]["profile_type"] == "character"


def test_public_openapi_omits_bot_user_and_token_management_fields():
    openapi_path = Path(__file__).resolve().parents[2] / "frontend" / "public" / "openapi.json"
    text = openapi_path.read_text(encoding="utf-8")
    spec = json.loads(text)

    for path in (
        "/bot/state",
        "/bot/activity",
        "/bot/feed/following",
        "/bot/profiles/characters/{character_id}",
    ):
        assert path in spec["paths"]

    for fragment in (
        "owner_id",
        "author_user_id",
        "actor_user_id",
        "recipient_user_id",
        "recipient_character_id",
        "token_prefix",
        "last_used_at",
        "persona_summary",
        "credential",
        '"data"',
    ):
        assert fragment not in text
