from types import SimpleNamespace

from app import schemas
from app.cruds import community as community_crud


class DummyDb:
    def add(self, _value):
        pass

    def commit(self):
        pass

    def refresh(self, _value):
        pass


def test_visible_body_converts_literal_newline_escapes() -> None:
    assert community_crud.sanitize_visible_post_body(r"a\n\nb") == "a\n\nb"
    assert community_crud.sanitize_visible_post_body(r"a\r\nb\rc") == "a\nb\nc"
    assert community_crud.sanitize_visible_post_body(r"a\tb") == "a b"


def test_visible_body_preserves_real_newlines_and_limits_blank_runs() -> None:
    assert community_crud.sanitize_visible_post_body("a\n\nb") == "a\n\nb"
    assert community_crud.sanitize_visible_post_body("a\n\n\n\nb") == "a\n\nb"
    assert community_crud.sanitize_visible_post_body("a   \n b  ") == "a\n b"


def test_visible_title_collapses_literal_and_real_newline_escapes() -> None:
    assert community_crud.sanitize_visible_post_title(r"a\n\nb") == "a b"
    assert community_crud.sanitize_visible_post_title("a\n\tb") == "a b"


def test_visible_sanitizer_does_not_decode_general_json_escapes() -> None:
    value = r"a \u003c \" \\ b"
    assert community_crud.sanitize_visible_post_body(value) == value


def test_create_post_sanitizes_visible_title_and_body_at_storage_boundary() -> None:
    post = community_crud.create_post(
        DummyDb(),
        post_id="post-test",
        user=SimpleNamespace(id="user-1", display_name="User"),
        character=SimpleNamespace(id="char-1", name="Character"),
        data=schemas.PostCreate(
            title=r"Title\nLine",
            body=r"first\n\nsecond",
            author_character_id="char-1",
        ),
    )

    assert post.title == "Title Line"
    assert post.body == "first\n\nsecond"


def test_create_timeline_post_sanitizes_reply_and_quote_body_boundary() -> None:
    post = community_crud.create_timeline_post(
        DummyDb(),
        post_id="post-reply",
        user=SimpleNamespace(id="user-1", display_name="User"),
        character=None,
        title=r"Re:\tTitle",
        body=r"reply\n\nbody",
        post_type="reply",
        reply_to_post_id="post-parent",
    )

    assert post.title == "Re: Title"
    assert post.body == "reply\n\nbody"
