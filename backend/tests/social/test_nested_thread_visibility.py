from datetime import timedelta

import pytest
from app.domains.social.models.posts import Post
from app.domains.social.repository.manual_feed import resolve_visible_root, reply_counts
from app.domains.social.service.manual_feed import get_owner_world_post_thread
from app.domains.social.contracts.writes import SocialWriteNotFoundError
from app.runtime.social.manual_feed_references import RuntimeManualFeedReferences
from social.test_l4_social_write_uow import _session_factory


def _reply(db, root, name, parent, *, visibility="public"):
    post = Post(id=name, author_user_id=root.author_user_id,
        author_character_id=root.author_character_id, world_id=root.world_id,
        author_world_character_id=root.author_world_character_id,
        post_type="reply", visibility=visibility, author_name="Fixture bird",
        title="", body="Synthetic reply", search_document="fixture",
        reply_to_post_id=parent, created_at=root.created_at + timedelta(seconds=int(name.split("-")[-1])),
        updated_at=root.updated_at)
    db.add(post)
    db.flush()
    return post


def test_nested_target_jumps_to_its_page_and_preserves_parent(tmp_path):
    factory = _session_factory(tmp_path)
    with factory() as db:
        root = db.get(Post, "social-uow-target-post")
        parent = root.id
        for index in range(115):
            parent = _reply(db, root, f"reply-{index}", parent).id
        def read(post_id, **kwargs):
            return get_owner_world_post_thread(db, references=RuntimeManualFeedReferences(db),
                world_id=root.world_id, post_id=post_id, current_user_id=root.author_user_id, **kwargs)
        first = read(root.id)
        assert len(first.items) == 51 and first.next_offset == 50
        assert first.items[0].reply_count == 115
        target = read("reply-114")
        assert target.root_post_id == root.id and target.target_post_id == "reply-114"
        assert target.page_offset == 100 and target.next_offset is None
        assert target.items[-1].reply_to_post_id == "reply-113"
        previous = read("reply-114", offset=0)
        assert previous.page_offset == 0 and previous.next_offset == 50


@pytest.mark.parametrize("hidden", ["private", "deleted", "reported"])
def test_unavailable_ancestor_excludes_descendants_and_counts(tmp_path, hidden):
    factory = _session_factory(tmp_path)
    with factory() as db:
        root = db.get(Post, "social-uow-target-post")
        parent = _reply(db, root, "reply-1", root.id)
        child = _reply(db, root, "reply-2", parent.id)
        if hidden == "private": parent.visibility = "private"
        elif hidden == "deleted": parent.deleted_at = root.created_at
        else: parent.report_hidden_at = root.created_at
        db.flush()
        assert resolve_visible_root(db, world_id=root.world_id, post_id=child.id) is None
        assert reply_counts(db, world_id=root.world_id, post_ids=[root.id]) == {}
        with pytest.raises(SocialWriteNotFoundError):
            get_owner_world_post_thread(db, references=RuntimeManualFeedReferences(db),
                world_id=root.world_id, post_id=child.id, current_user_id=root.author_user_id)


def test_cycles_and_cross_world_ancestors_do_not_resolve(tmp_path):
    factory = _session_factory(tmp_path)
    with factory() as db:
        root = db.get(Post, "social-uow-target-post")
        first = _reply(db, root, "reply-1", root.id)
        second = _reply(db, root, "reply-2", first.id)
        first.reply_to_post_id = second.id
        db.flush()
        assert resolve_visible_root(db, world_id=root.world_id, post_id=second.id) is None
        assert resolve_visible_root(db, world_id="another-world", post_id=root.id) is None
        assert reply_counts(db, world_id=root.world_id, post_ids=[root.id]) == {}
