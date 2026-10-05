"""Flush-only canonical set/unset. Runtime owns atomic commit and bounded retry."""
from app.core.ids import uuid7_string
from app.domains.social.models.posts import Post, PostLike
from app.domains.social.repository import manual_feed, owner_reactions
from app.domains.social.schemas.manual import ManualSocialLikeRead
from app.domains.social.service.source_writes import _owner_actor, _owner_reply_target
from app.domains.social.contracts.writes import SocialWriteConflictError


class OwnerReactionService:
    def __init__(self, db, *, references, failure_injector=None):
        self.db, self.references, self.fail = db, references, failure_injector or (lambda _:None)

    def set_like(self, command):
        db = self.db
        actor, character, _ = _owner_actor(self.references, world_id=command.world_id, current_user_id=command.current_user_id)
        post, target = _owner_reply_target(db, references=self.references, world_id=command.world_id,
            actor_world_character_id=actor.id, target_post_id=command.target_post_id)
        root = db.get(Post, manual_feed.canonical_root_id(db, world_id=command.world_id, post_id=post.id))
        row = owner_reactions.owner_like(db, post_id=post.id, character_id=character.id)
        if row is not None:
            if row.user_id != command.current_user_id or row.world_id not in {None, command.world_id} or row.actor_world_character_id not in {None,actor.id} or row.target_world_character_id not in {None,target.id}:
                raise SocialWriteConflictError("owner_like_scope_conflict")
            row.world_id, row.actor_world_character_id, row.target_world_character_id = command.world_id, actor.id, target.id
        changed = False
        if command.liked and row is None:
            db.add(PostLike(post_id=post.id, user_id=command.current_user_id, character_id=character.id,
                world_id=command.world_id, actor_world_character_id=actor.id, target_world_character_id=target.id))
            changed = True
        elif not command.liked and row is not None:
            db.delete(row)
            changed = True
        db.flush()
        self.fail("after_reaction_source")
        if changed:
            self.references.record_source_reaction_event(world_id=command.world_id, actor_world_character_id=actor.id,
                target_world_character_id=target.id, post=post, root_post=root,
                event_type="like_added" if command.liked else "like_removed", transition_key=uuid7_string())
        self.fail("after_reaction_event")
        return ManualSocialLikeRead(world_id=command.world_id, post_id=post.id, owner_world_character_id=actor.id,
            viewer_like_state="liked" if command.liked else "not_liked",
            like_count=manual_feed.like_counts(db, post_ids=[post.id]).get(post.id,0))
