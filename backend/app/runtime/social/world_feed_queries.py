"""Same-Session foreign facts for Social search; no eager reads or commits."""

from __future__ import annotations

from sqlalchemy import and_, exists, select
from sqlalchemy.orm import Session, aliased
from app.domains.characters.service.profile import get_character
from app.domains.world_characters.models import WorldCharacter, WorldCommunityProfile
from app.domains.worlds.models import World, WorldMembership
from app.domains.world_packages.models import WorldPackageImport
from app.domains.characters.models import Character
from app.domains.social.models.posts import Post
from app.domains.social.models.feed import WorldCharacterBlock
from app.domains.world_characters.service.setup_validation import (
    character_contract_hash,
)


class WorldFeedQueries:
    def __init__(self, db: Session):
        self.db = db

    def world_character(self, identity: str):
        return self.db.get(WorldCharacter, identity)

    def character(self, identity: str):
        return get_character(self.db, identity)

    def membership(self, identity: str):
        return self.db.get(WorldMembership, identity)

    def world(self, identity: str):
        return self.db.get(World, identity)

    def character_hash(self, character):
        return character_contract_hash(character)

    def ready_profile(self, world_character_id: str):
        return self.db.scalar(
            select(WorldCommunityProfile)
            .where(
                WorldCommunityProfile.world_character_id == world_character_id,
                WorldCommunityProfile.status == "ready",
            )
            .order_by(
                WorldCommunityProfile.approved_at.desc(),
                WorldCommunityProfile.generated_at.desc(),
            )
        )

    def imported_lineage(self, world_id: str):
        return self.db.scalar(
            select(WorldPackageImport.import_id)
            .where(WorldPackageImport.imported_world_id == world_id)
            .limit(1)
        )

    def candidate_rows(self, profile):
        author_wc = aliased(WorldCharacter)
        author_membership = aliased(WorldMembership)
        block_from_actor = exists(
            select(WorldCharacterBlock.id).where(
                WorldCharacterBlock.world_id == profile.world.id,
                WorldCharacterBlock.blocker_world_character_id
                == profile.world_character.id,
                WorldCharacterBlock.blocked_world_character_id
                == Post.author_world_character_id,
            )
        )
        block_to_actor = exists(
            select(WorldCharacterBlock.id).where(
                WorldCharacterBlock.world_id == profile.world.id,
                WorldCharacterBlock.blocker_world_character_id
                == Post.author_world_character_id,
                WorldCharacterBlock.blocked_world_character_id
                == profile.world_character.id,
            )
        )

        def read(post_ids):
            query = (
                select(Post, author_wc)
                .join(author_wc, author_wc.id == Post.author_world_character_id)
                .join(
                    author_membership,
                    and_(
                        author_membership.id == author_wc.membership_id,
                        author_membership.world_id == author_wc.world_id,
                    ),
                )
                .where(
                    Post.world_id == profile.world.id,
                    Post.visibility == "public",
                    Post.deleted_at.is_(None),
                    Post.report_hidden_at.is_(None),
                    Post.reply_to_post_id.is_(None),
                    Post.post_type != "repost",
                    Post.repost_of_post_id.is_(None),
                    Post.author_world_character_id.is_not(None),
                    Post.author_world_character_id != profile.world_character.id,
                    author_wc.status == "active",
                    author_membership.status == "active",
                    Post.id.in_(post_ids),
                    ~block_from_actor,
                    ~block_to_actor,
                )
            )
            canonical_rows = {
                post.id: (post, world_character)
                for post, world_character in self.db.execute(query).all()
            }
            return canonical_rows

        return read

    def post_context(self, post_ids: list[str]):
        return self.db.execute(
            select(Post.id, Post.title, Character.name)
            .join(
                WorldCharacter,
                WorldCharacter.id == Post.author_world_character_id,
            )
            .join(Character, Character.id == Post.author_character_id)
            .where(Post.id.in_(post_ids))
        ).all()
