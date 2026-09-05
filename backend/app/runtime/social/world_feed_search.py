"""Bind World feed operations to current caller-Session facts without eager IO."""

from __future__ import annotations
from datetime import datetime
from typing import Iterable
from sqlalchemy.orm import Session
from app.domains.social.contracts.world_feed import (
    ReadySearchProfile,
    CandidateSearchResult,
    FeedWorldCharacter,
    FeedOwner,
)
from app.domains.social.models.posts import Post
from app.domains.social.schemas import feed as schemas
from app.domains.social.contracts.search_index import SocialSearchIndexPort
from app.domains.social.contracts.search_state import SocialSearchState
from app.domains.social.service import world_feed as service
from app.runtime.social.world_feed_queries import WorldFeedQueries


def load_ready_search_profile(
    db: Session, *, world_character_id: str
) -> ReadySearchProfile:
    return service.load_ready_search_profile(
        db, references=WorldFeedQueries(db), world_character_id=world_character_id
    )


def search_world_feed_candidates(
    db: Session,
    *,
    profile: ReadySearchProfile,
    keywords: tuple[str, str],
    allowed_policy_actions: Iterable[str],
    now: datetime,
    search_index: SocialSearchIndexPort | None,
    search_state: SocialSearchState,
) -> CandidateSearchResult:
    return service.search_world_feed_candidates(
        db,
        references=WorldFeedQueries(db),
        profile=profile,
        keywords=keywords,
        allowed_policy_actions=allowed_policy_actions,
        now=now,
        search_index=search_index,
        search_state=search_state,
    )


def revalidate_candidate_actions(
    db: Session,
    *,
    profile: ReadySearchProfile,
    candidate: schemas.WorldFeedCandidateRead,
    allowed_policy_actions: Iterable[str],
) -> tuple[Post, list[schemas.FeedAction]] | None:
    return service.revalidate_candidate_actions(
        db,
        references=WorldFeedQueries(db),
        profile=profile,
        candidate=candidate,
        allowed_policy_actions=allowed_policy_actions,
    )


def world_feed_cycle_status(
    db: Session, *, world_character: FeedWorldCharacter, recent_limit: int = 12
) -> schemas.WorldFeedCycleStatusRead:
    return service.world_feed_cycle_status(
        db,
        references=WorldFeedQueries(db),
        world_character=world_character,
        recent_limit=recent_limit,
    )


def owner_world_feed_cycle_status(
    db: Session, *, world_character_id: str, user: FeedOwner
) -> schemas.WorldFeedCycleStatusRead:
    return service.owner_world_feed_cycle_status(
        db,
        references=WorldFeedQueries(db),
        world_character_id=world_character_id,
        user=user,
    )
