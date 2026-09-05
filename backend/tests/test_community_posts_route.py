
from app.domains.social.service import presentation as post_presentation
from datetime import datetime, timezone
from types import SimpleNamespace

from app import schemas
from app.api.v1.routes import community as community_routes
from app.services import community as community_service


def test_list_posts_route_passes_limit(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def fake_list_posts(db, *, limit: int):
        captured["db"] = db
        captured["limit"] = limit
        return []

    monkeypatch.setattr(community_routes.community_service, "list_posts", fake_list_posts)

    db = object()
    assert community_routes.list_posts(limit=1, db=db) == []
    assert captured == {"db": db, "limit": 1}


def test_list_posts_service_uses_feed_limit(monkeypatch) -> None:
    captured: dict[str, object] = {}
    page = schemas.FeedPage(items=[], next_cursor=None)

    def fake_list_feed(db, *, limit: int, content: schemas.FeedContentFilter):
        captured["db"] = db
        captured["limit"] = limit
        captured["content"] = content
        return page

    monkeypatch.setattr(community_service, "list_feed", fake_list_feed)

    db = object()
    assert community_service.list_posts(db, limit=1) == []
    assert captured == {"db": db, "limit": 1, "content": "all"}


class _MentionDb:
    def __init__(self, characters):
        self.characters = characters

    def scalars(self, _statement):
        return self.characters


def test_mentioned_characters_for_texts_resolves_existing_handles_once() -> None:
    db = _MentionDb(
        [
            SimpleNamespace(id="char-zog", handle="zogwangbae", name="조광배"),
            SimpleNamespace(id="char-hon", handle="honagyn", name="호나냔"),
        ]
    )

    mentions = community_service._mentioned_characters_for_texts(
        db,
        "오늘 @zogwangbae 이야기",
        "@zogwangbae 다시, @honagyn도 같이",
    )

    assert [mention.handle for mention in mentions] == ["zogwangbae", "honagyn"]
    assert [mention.character_id for mention in mentions] == ["char-zog", "char-hon"]


def test_mentioned_characters_for_texts_ignores_unknown_and_mid_word_at() -> None:
    db = _MentionDb(
        [
            SimpleNamespace(id="char-zog", handle="zogwangbae", name="조광배"),
        ]
    )

    mentions = community_service._mentioned_characters_for_texts(
        db,
        "메일 test@zogwangbae.example 은 mention 아님",
        "없는 @missing_handle 과 유저 @user_handle 은 제외, @zogwangbae만 포함",
    )

    assert [mention.handle for mention in mentions] == ["zogwangbae"]


def test_mentioned_characters_for_texts_accepts_trailing_period_punctuation() -> None:
    db = _MentionDb(
        [
            SimpleNamespace(id="char-zog", handle="zogwangbae", name="zog"),
        ]
    )

    mentions = community_service._mentioned_characters_for_texts(
        db,
        "say hello to @zogwangbae.",
        "@zogwangbae. next sentence",
        "@zogwangbae.)",
    )

    assert [mention.handle for mention in mentions] == ["zogwangbae"]


def test_mentioned_characters_for_texts_does_not_link_domain_like_dot_suffix() -> None:
    db = _MentionDb(
        [
            SimpleNamespace(id="char-zog", handle="zogwangbae", name="zog"),
        ]
    )

    mentions = community_service._mentioned_characters_for_texts(
        db,
        "email test@zogwangbae.example is not a mention",
        "@zogwangbae.example should not partially link",
        "unknown @missing_handle. is still excluded",
    )

    assert mentions == []


def test_notify_mentioned_characters_creates_mention_notifications(monkeypatch) -> None:
    mentions = [
        schemas.MentionedCharacterRef(
            handle="zogwangbae",
            character_id="char-zog",
            name="Zog",
        ),
        schemas.MentionedCharacterRef(
            handle="honagyn",
            character_id="char-hon",
            name="Hon",
        ),
    ]
    created: list[dict[str, object]] = []

    monkeypatch.setattr(
        community_service,
        "_mentioned_characters_for_texts",
        lambda db, *texts: mentions,
    )
    monkeypatch.setattr(
        community_service.community_crud,
        "create_notification",
        lambda _db, **kwargs: created.append(kwargs),
    )

    community_service._notify_mentioned_characters(
        object(),
        post=SimpleNamespace(id="post-mention", title="hi @zogwangbae", body="@honagyn"),
        actor_user_id=None,
        actor_character_id="char-author",
    )

    assert created == [
        {
            "notification_type": "mention",
            "recipient_character_id": "char-zog",
            "actor_user_id": None,
            "actor_character_id": "char-author",
            "post_id": "post-mention",
            "source_post_id": None,
        },
        {
            "notification_type": "mention",
            "recipient_character_id": "char-hon",
            "actor_user_id": None,
            "actor_character_id": "char-author",
            "post_id": "post-mention",
            "source_post_id": None,
        },
    ]


def test_notify_mentioned_characters_skips_actor_and_owner_duplicates(
    monkeypatch,
) -> None:
    mentions = [
        schemas.MentionedCharacterRef(
            handle="author",
            character_id="char-author",
            name="Author",
        ),
        schemas.MentionedCharacterRef(
            handle="owner",
            character_id="char-owner",
            name="Owner",
        ),
        schemas.MentionedCharacterRef(
            handle="target",
            character_id="char-target",
            name="Target",
        ),
    ]
    created: list[dict[str, object]] = []

    monkeypatch.setattr(
        community_service,
        "_mentioned_characters_for_texts",
        lambda db, *texts: mentions,
    )
    monkeypatch.setattr(
        community_service.community_crud,
        "create_notification",
        lambda _db, **kwargs: created.append(kwargs),
    )

    community_service._notify_mentioned_characters(
        object(),
        post=SimpleNamespace(id="post-mention", title="@author @owner @target", body=""),
        actor_user_id=None,
        actor_character_id="char-author",
        skip_character_ids=["char-owner"],
    )

    assert [item["recipient_character_id"] for item in created] == ["char-target"]


def test_post_reference_includes_mention_metadata(monkeypatch) -> None:
    post = SimpleNamespace(
        id="post-1",
        author_name="호나냔",
        author_user_id=None,
        author_character_id="char-hon",
        title="제목 @zogwangbae",
        body="본문",
        info_kind=None,
        source_name=None,
        source_url=None,
        observed_at=None,
        location_label=None,
        created_at=datetime.now(timezone.utc),
        post_type="post",
    )
    mention = schemas.MentionedCharacterRef(
        handle="zogwangbae",
        character_id="char-zog",
        name="조광배",
    )

    monkeypatch.setattr(post_presentation.post_repository, "get_post", lambda db, post_id: post)
    monkeypatch.setattr(post_presentation, "_is_post_public_context_visible", lambda db, post: True)
    monkeypatch.setattr(
        post_presentation,
        "_post_author_identity",
        lambda db, post: {"name": "호나냔", "handle": "honagyn", "avatar_url": None},
    )
    monkeypatch.setattr(post_presentation, "_post_media_reads", lambda db, post: [])
    monkeypatch.setattr(
        post_presentation,
        "_mentioned_characters_for_texts",
        lambda db, *texts: [mention],
    )

    reference = community_service._post_reference(object(), "post-1")

    assert reference is not None
    assert reference.mentioned_characters == [mention]
