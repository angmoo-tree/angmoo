from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
import time
from typing import Iterable
from uuid import uuid4
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import ValidationError
from sqlalchemy import and_, exists, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, aliased

from app import models, schemas
from app.core.search_text import normalize_search_text
from app.domains.social.public import (
    SocialSearchIndexPort,
    SocialSearchState,
    find_keyword_post_ids,
)
from app.domains.world_characters.domain.runtime_modes import (
    AUTONOMOUS_FEED_RUNTIME_MODE,
)
from app.services import world_character_contracts


KEYWORDS_PER_CYCLE = 2
KEYWORD_COUNT = 8
MIN_KEYWORD_LENGTH = 2
KEYWORD_OFFSETS = (0, 2, 4, 6)
PER_KEYWORD_FETCH_LIMIT = 24
RAW_MERGE_LIMIT = 48
PLANNER_CANDIDATE_LIMIT = 8
AUTHOR_CANDIDATE_LIMIT = 2
OBSERVATION_LEASE = timedelta(minutes=10)


class WorldFeedError(Exception):
    pass


class WorldFeedReadinessError(WorldFeedError):
    def __init__(self, reason_code: str):
        self.reason_code = reason_code
        super().__init__(reason_code)


class WorldFeedStatusNotFoundError(WorldFeedError):
    pass


class WorldFeedStatusForbiddenError(WorldFeedError):
    pass


@dataclass(frozen=True)
class ReadySearchProfile:
    world: models.World
    world_character: models.WorldCharacter
    membership: models.WorldMembership
    character: models.Character
    profile: models.WorldCommunityProfile
    keywords: tuple[str, ...]
    avoid_topics: tuple[str, ...]
    action_profile: dict[str, object]
    imported_world_runtime_locked: bool


@dataclass(frozen=True)
class KeywordClaim:
    cursor_offset: int
    keywords: tuple[str, str]
    duplicate_cycle: bool
    previous_summary: dict[str, object] | None


@dataclass(frozen=True)
class CandidateSearchResult:
    candidates: tuple[schemas.WorldFeedCandidateRead, ...]
    raw_candidate_count: int
    filtered_candidate_count: int
    query_latency_ms: int


@dataclass(frozen=True)
class ObservationClaimResult:
    candidates: tuple[schemas.WorldFeedCandidateRead, ...]
    observations: tuple[models.WorldCharacterFeedObservation, ...]
    claim_conflict_count: int


def _aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _action_weight(action_profile: dict[str, object], action: str) -> int:
    raw = action_profile.get(action)
    if not isinstance(raw, dict):
        return 0
    try:
        return max(0, min(100, int(raw.get("weight") or 0)))
    except (TypeError, ValueError):
        return 0


def load_ready_search_profile(
    db: Session, *, world_character_id: str
) -> ReadySearchProfile:
    world_character = db.get(models.WorldCharacter, world_character_id)
    if world_character is None or world_character.status != "active":
        raise WorldFeedReadinessError("world_character_not_ready")
    if world_character.feed_runtime_mode != AUTONOMOUS_FEED_RUNTIME_MODE:
        raise WorldFeedReadinessError("feed_runtime_mode_not_enabled")
    character = db.get(models.Character, world_character.character_id)
    membership = db.get(models.WorldMembership, world_character.membership_id)
    world = db.get(models.World, world_character.world_id)
    if (
        character is None
        or character.deleted_at is not None
        or membership is None
        or membership.world_id != world_character.world_id
        or membership.user_id != character.owner_id
        or membership.status != "active"
        or world is None
        or world.status != "published"
        or world.readiness_status != "publish_ready"
    ):
        raise WorldFeedReadinessError("world_scope_not_ready")
    profile = db.scalar(
        select(models.WorldCommunityProfile)
        .where(
            models.WorldCommunityProfile.world_character_id == world_character.id,
            models.WorldCommunityProfile.status == "ready",
        )
        .order_by(
            models.WorldCommunityProfile.approved_at.desc(),
            models.WorldCommunityProfile.generated_at.desc(),
        )
    )
    if profile is None:
        raise WorldFeedReadinessError("world_community_profile_not_ready")
    character_hash = world_character_contracts.character_contract_hash(character)
    if (
        world_character.character_contract_hash != character_hash
        or world_character.world_contract_hash != world.contract_hash
        or profile.character_contract_hash != character_hash
        or profile.world_contract_hash != world.contract_hash
    ):
        raise WorldFeedReadinessError("world_community_profile_stale")
    try:
        validated = schemas.WorldCommunityProfilePayload(
            visible_summary=profile.visible_summary,
            core_interests=profile.core_interests,
            adjacent_interests=profile.adjacent_interests,
            avoid_topics=profile.avoid_topics,
            discovery_openness=profile.discovery_openness,
            search_keywords=profile.search_keywords,
            action_profile=profile.action_profile,
        )
    except ValidationError as exc:
        raise WorldFeedReadinessError("world_community_profile_invalid") from exc
    keywords = tuple(
        normalize_search_text(keyword, max_chars=40)
        for keyword in validated.search_keywords
    )
    if len(keywords) != KEYWORD_COUNT or len(set(keywords)) != KEYWORD_COUNT:
        raise WorldFeedReadinessError("world_community_profile_invalid")
    # Two-character Korean keywords remain selective enough inside the mandatory
    # World boundary. The P5 PostgreSQL preflight measured the worst no-result
    # path over 10,000 posts in one World at 1.744 ms. Keep one-character
    # keywords fail-closed because they are both less meaningful and less
    # selective.
    if any(len(keyword) < MIN_KEYWORD_LENGTH for keyword in keywords):
        raise WorldFeedReadinessError("short_keyword_requires_repair")
    avoid_topics = tuple(
        normalize_search_text(topic, max_chars=40)
        for topic in validated.avoid_topics
        if normalize_search_text(topic, max_chars=40)
    )
    imported_world_runtime_locked = _is_imported_world_runtime_locked(
        db,
        world_character=world_character,
    )
    return ReadySearchProfile(
        world=world,
        world_character=world_character,
        membership=membership,
        character=character,
        profile=profile,
        keywords=keywords,
        avoid_topics=avoid_topics,
        action_profile=validated.action_profile.model_dump(mode="json"),
        imported_world_runtime_locked=imported_world_runtime_locked,
    )


def claim_cycle_keywords(
    db: Session,
    *,
    profile: ReadySearchProfile,
    cycle_key: str,
    run_id: str,
) -> KeywordClaim:
    cursor = db.scalar(
        select(models.WorldCharacterFeedCursor)
        .where(
            models.WorldCharacterFeedCursor.world_character_id
            == profile.world_character.id
        )
        .with_for_update()
    )
    if cursor is None:
        cursor = models.WorldCharacterFeedCursor(
            world_character_id=profile.world_character.id,
            world_id=profile.world.id,
            next_keyword_offset=0,
            version=1,
        )
        db.add(cursor)
        try:
            db.flush()
        except IntegrityError:
            db.rollback()
            cursor = db.scalar(
                select(models.WorldCharacterFeedCursor)
                .where(
                    models.WorldCharacterFeedCursor.world_character_id
                    == profile.world_character.id
                )
                .with_for_update()
            )
            if cursor is None:
                raise
    if cursor.world_id != profile.world.id:
        raise WorldFeedReadinessError("world_scope_not_ready")
    offset = int(cursor.next_keyword_offset)
    if offset not in KEYWORD_OFFSETS:
        raise WorldFeedReadinessError("feed_cursor_invalid")
    if cursor.last_cycle_key == cycle_key:
        return KeywordClaim(
            cursor_offset=offset,
            keywords=(
                profile.keywords[offset],
                profile.keywords[(offset + 1) % KEYWORD_COUNT],
            ),
            duplicate_cycle=True,
            previous_summary=(
                dict(cursor.last_cycle_summary)
                if isinstance(cursor.last_cycle_summary, dict)
                else None
            ),
        )
    cursor.last_cycle_key = cycle_key
    cursor.last_run_id = run_id
    cursor.version += 1
    db.add(cursor)
    db.flush()
    return KeywordClaim(
        cursor_offset=offset,
        keywords=(
            profile.keywords[offset],
            profile.keywords[(offset + 1) % KEYWORD_COUNT],
        ),
        duplicate_cycle=False,
        previous_summary=None,
    )


def _age_bucket(age_seconds: int) -> str:
    if age_seconds < 24 * 60 * 60:
        return "recent"
    if age_seconds < 7 * 24 * 60 * 60:
        return "days_old"
    if age_seconds < 28 * 24 * 60 * 60:
        return "weeks_old"
    return "older"


def _local_datetime(value: datetime, timezone_name: str) -> str:
    try:
        zone = ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError:
        zone = UTC
    return _aware_utc(value).astimezone(zone).isoformat()


def _existing_reactions(
    db: Session,
    *,
    actor: ReadySearchProfile,
    posts: Iterable[models.Post],
) -> tuple[set[str], set[str], set[str], set[str]]:
    post_list = list(posts)
    post_ids = [post.id for post in post_list]
    if not post_ids:
        return set(), set(), set(), set()
    liked = set(
        db.scalars(
            select(models.PostLike.post_id).where(
                models.PostLike.post_id.in_(post_ids),
                models.PostLike.character_id == actor.character.id,
            )
        )
    )
    commented = set(
        db.scalars(
            select(models.Post.reply_to_post_id).where(
                models.Post.reply_to_post_id.in_(post_ids),
                models.Post.author_world_character_id == actor.world_character.id,
                models.Post.deleted_at.is_(None),
            )
        )
    )
    reposted = set(
        db.scalars(
            select(models.PostRepost.post_id).where(
                models.PostRepost.post_id.in_(post_ids),
                models.PostRepost.character_id == actor.character.id,
            )
        )
    )
    author_character_ids = {
        post.author_character_id for post in post_list if post.author_character_id
    }
    followed = set(
        db.scalars(
            select(models.ProfileFollow.target_character_id).where(
                models.ProfileFollow.follower_character_id == actor.character.id,
                models.ProfileFollow.target_character_id.in_(author_character_ids),
            )
        )
    )
    return liked, commented, reposted, followed


def _allowed_actions(
    *,
    actor: ReadySearchProfile,
    post: models.Post,
    policy_actions: set[str],
    liked: set[str],
    commented: set[str],
    reposted: set[str],
    followed: set[str],
) -> list[schemas.FeedAction]:
    allowed: list[schemas.FeedAction] = []
    if (
        "like" in policy_actions
        and _action_weight(actor.action_profile, "like") > 0
        and post.id not in liked
    ):
        allowed.append("like")
    if (
        ("comment" in policy_actions or "reply" in policy_actions)
        and _action_weight(actor.action_profile, "comment") > 0
        and post.id not in commented
    ):
        allowed.append("comment")
    if (
        "repost" in policy_actions
        and _action_weight(actor.action_profile, "repost") > 0
        and post.id not in reposted
    ):
        allowed.append("repost")
    if (
        "follow" in policy_actions
        and _action_weight(actor.action_profile, "follow") > 0
        and post.author_character_id not in followed
    ):
        allowed.append("follow")
    return allowed


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
    started = time.perf_counter()
    author_wc = aliased(models.WorldCharacter)
    author_membership = aliased(models.WorldMembership)
    block_from_actor = exists(
        select(models.WorldCharacterBlock.id).where(
            models.WorldCharacterBlock.world_id == profile.world.id,
            models.WorldCharacterBlock.blocker_world_character_id
            == profile.world_character.id,
            models.WorldCharacterBlock.blocked_world_character_id
            == models.Post.author_world_character_id,
        )
    )
    block_to_actor = exists(
        select(models.WorldCharacterBlock.id).where(
            models.WorldCharacterBlock.world_id == profile.world.id,
            models.WorldCharacterBlock.blocker_world_character_id
            == models.Post.author_world_character_id,
            models.WorldCharacterBlock.blocked_world_character_id
            == profile.world_character.id,
        )
    )
    lookup = find_keyword_post_ids(
        search_index,
        search_state=search_state,
        world_id=profile.world.id,
        keywords=keywords,
        per_keyword_limit=PER_KEYWORD_FETCH_LIMIT,
        merged_limit=RAW_MERGE_LIMIT,
    )
    rows_by_post_id: dict[str, tuple[models.Post, models.WorldCharacter]] = {}
    if lookup.post_ids:
        query = (
            select(models.Post, author_wc)
            .join(author_wc, author_wc.id == models.Post.author_world_character_id)
            .join(
                author_membership,
                and_(
                    author_membership.id == author_wc.membership_id,
                    author_membership.world_id == author_wc.world_id,
                ),
            )
            .where(
                models.Post.world_id == profile.world.id,
                models.Post.visibility == "public",
                models.Post.deleted_at.is_(None),
                models.Post.report_hidden_at.is_(None),
                models.Post.reply_to_post_id.is_(None),
                models.Post.post_type != "repost",
                models.Post.repost_of_post_id.is_(None),
                models.Post.author_world_character_id.is_not(None),
                models.Post.author_world_character_id
                != profile.world_character.id,
                author_wc.status == "active",
                author_membership.status == "active",
                models.Post.id.in_(lookup.post_ids),
                ~block_from_actor,
                ~block_to_actor,
            )
        )
        canonical_rows = {
            post.id: (post, world_character)
            for post, world_character in db.execute(query).all()
        }
        rows_by_post_id = {
            post_id: canonical_rows[post_id]
            for post_id in lookup.post_ids
            if post_id in canonical_rows
        }
    # Preserve the pre-FTS diagnostic meaning: this is the number of unique
    # canonical rows that remain after the query-time safety filters, not the
    # projection's duplicate/raw hit count.
    raw_count = len(rows_by_post_id)
    observations = {
        row.post_id: row
        for row in db.scalars(
            select(models.WorldCharacterFeedObservation).where(
                models.WorldCharacterFeedObservation.observer_world_character_id
                == profile.world_character.id,
                models.WorldCharacterFeedObservation.post_id.in_(rows_by_post_id),
            )
        )
    }
    posts = [row[0] for row in rows_by_post_id.values()]
    liked, commented, reposted, followed = _existing_reactions(
        db, actor=profile, posts=posts
    )
    policy_actions = set(allowed_policy_actions)
    ranked: list[tuple[float, models.Post, models.WorldCharacter, list[str], list[str], list[schemas.FeedAction]]] = []
    current = _aware_utc(now)
    for post, world_character in rows_by_post_id.values():
        existing_observation = observations.get(post.id)
        if existing_observation is not None and (
            existing_observation.status == "observed"
            or (
                existing_observation.status == "claimed"
                and _aware_utc(existing_observation.lease_expires_at) > current
            )
        ):
            continue
        title = normalize_search_text(post.title, max_chars=160)
        body = normalize_search_text(post.body, max_chars=4_000)
        topic = normalize_search_text(post.topic_signature, max_chars=300)
        matched_keywords = [
            keyword
            for keyword in keywords
            if keyword in title or keyword in body or keyword in topic
        ]
        if not matched_keywords:
            continue
        if any(
            avoid and (avoid in title or avoid in body or avoid in topic)
            for avoid in profile.avoid_topics
        ):
            continue
        matched_fields: list[str] = []
        score = 0.0
        if any(keyword in topic for keyword in matched_keywords):
            matched_fields.append("topic_signature")
            score += 5
        if any(keyword in title for keyword in matched_keywords):
            matched_fields.append("title")
            score += 4
        if any(keyword in body for keyword in matched_keywords):
            matched_fields.append("body")
            score += 2
        if len(matched_fields) > 1:
            score += 2
        age_seconds = max(
            0,
            int((current - _aware_utc(post.created_at)).total_seconds()),
        )
        score -= min(4.0, age_seconds / (24 * 60 * 60) * 0.05)
        allowed_actions = _allowed_actions(
            actor=profile,
            post=post,
            policy_actions=policy_actions,
            liked=liked,
            commented=commented,
            reposted=reposted,
            followed=followed,
        )
        if not allowed_actions:
            continue
        ranked.append(
            (
                score,
                post,
                world_character,
                matched_keywords,
                matched_fields,
                allowed_actions,
            )
        )
    ranked.sort(
        key=lambda item: (
            -item[0],
            -_aware_utc(item[1].created_at).timestamp(),
            item[1].id,
        )
    )
    selected: list[tuple[float, models.Post, models.WorldCharacter, list[str], list[str], list[schemas.FeedAction]]] = []
    author_counts: dict[str, int] = {}
    for item in ranked:
        author_id = item[2].id
        if author_counts.get(author_id, 0) >= AUTHOR_CANDIDATE_LIMIT:
            continue
        selected.append(item)
        author_counts[author_id] = author_counts.get(author_id, 0) + 1
        if len(selected) >= PLANNER_CANDIDATE_LIMIT:
            break
    candidates: list[schemas.WorldFeedCandidateRead] = []
    for index, (score, post, world_character, matched_keywords, matched_fields, actions) in enumerate(selected):
        created_at = _aware_utc(post.created_at)
        age_seconds = max(0, int((current - created_at).total_seconds()))
        candidates.append(
            schemas.WorldFeedCandidateRead(
                candidate_index=index,
                post_id=post.id,
                author_world_character_id=world_character.id,
                author_character_id=world_character.character_id,
                author_name=post.author_name,
                title=post.title[:160],
                body_preview=post.body[:1_200],
                topic_signature=(post.topic_signature or "")[:300],
                created_at=created_at,
                world_local_datetime=_local_datetime(
                    created_at, profile.world.timezone
                ),
                age_seconds=age_seconds,
                age_bucket=_age_bucket(age_seconds),
                matched_keywords=matched_keywords,
                matched_fields=matched_fields,
                rank_score=round(score, 4),
                allowed_actions=actions,
            )
        )
    elapsed = int((time.perf_counter() - started) * 1000)
    return CandidateSearchResult(
        candidates=tuple(candidates),
        raw_candidate_count=raw_count,
        filtered_candidate_count=len(ranked),
        query_latency_ms=max(0, elapsed),
    )


def claim_feed_observations(
    db: Session,
    *,
    profile: ReadySearchProfile,
    candidates: tuple[schemas.WorldFeedCandidateRead, ...],
    cycle_key: str,
    run_id: str,
    now: datetime,
) -> ObservationClaimResult:
    current = _aware_utc(now)
    claimed_candidates: list[schemas.WorldFeedCandidateRead] = []
    observations: list[models.WorldCharacterFeedObservation] = []
    conflicts = 0
    for candidate in candidates:
        observation = db.scalar(
            select(models.WorldCharacterFeedObservation)
            .where(
                models.WorldCharacterFeedObservation.observer_world_character_id
                == profile.world_character.id,
                models.WorldCharacterFeedObservation.post_id == candidate.post_id,
            )
            .with_for_update()
        )
        if observation is not None and (
            observation.status == "observed"
            or (
                observation.status == "claimed"
                and _aware_utc(observation.lease_expires_at) > current
            )
        ):
            conflicts += 1
            continue
        if observation is None:
            observation = models.WorldCharacterFeedObservation(
                id=f"feed-observation-{uuid4().hex}",
                world_id=profile.world.id,
                observer_world_character_id=profile.world_character.id,
                post_id=candidate.post_id,
                status="claimed",
                claim_token=uuid4().hex,
                lease_expires_at=current + OBSERVATION_LEASE,
                cycle_key=cycle_key,
                run_id=run_id,
                matched_keywords=list(candidate.matched_keywords),
                matched_fields=list(candidate.matched_fields),
                rank_score=candidate.rank_score,
                post_created_at=candidate.created_at,
                claimed_at=current,
            )
            try:
                with db.begin_nested():
                    db.add(observation)
                    db.flush()
            except IntegrityError:
                conflicts += 1
                continue
        else:
            observation.status = "claimed"
            observation.claim_token = uuid4().hex
            observation.lease_expires_at = current + OBSERVATION_LEASE
            observation.cycle_key = cycle_key
            observation.run_id = run_id
            observation.matched_keywords = list(candidate.matched_keywords)
            observation.matched_fields = list(candidate.matched_fields)
            observation.rank_score = candidate.rank_score
            observation.post_created_at = candidate.created_at
            observation.claimed_at = current
            observation.observed_at = None
            db.add(observation)
            db.flush()
        claimed_candidates.append(
            candidate.model_copy(
                update={"candidate_index": len(claimed_candidates)}
            )
        )
        observations.append(observation)
    return ObservationClaimResult(
        candidates=tuple(claimed_candidates),
        observations=tuple(observations),
        claim_conflict_count=conflicts,
    )


def revalidate_candidate_actions(
    db: Session,
    *,
    profile: ReadySearchProfile,
    candidate: schemas.WorldFeedCandidateRead,
    allowed_policy_actions: Iterable[str],
) -> tuple[models.Post, list[schemas.FeedAction]] | None:
    post = db.get(models.Post, candidate.post_id)
    if (
        post is None
        or post.world_id != profile.world.id
        or post.author_world_character_id != candidate.author_world_character_id
        or post.author_character_id != candidate.author_character_id
        or post.visibility != "public"
        or post.deleted_at is not None
        or post.report_hidden_at is not None
        or post.reply_to_post_id is not None
        or post.post_type == "repost"
        or post.repost_of_post_id is not None
    ):
        return None
    actor_wc = db.get(models.WorldCharacter, profile.world_character.id)
    actor_membership = (
        db.get(models.WorldMembership, actor_wc.membership_id) if actor_wc else None
    )
    author_wc = db.get(models.WorldCharacter, candidate.author_world_character_id)
    author_membership = (
        db.get(models.WorldMembership, author_wc.membership_id) if author_wc else None
    )
    if (
        actor_wc is None
        or actor_wc.status != "active"
        or actor_wc.world_id != profile.world.id
        or actor_membership is None
        or actor_membership.status != "active"
        or actor_membership.world_id != profile.world.id
        or author_wc is None
        or author_wc.status != "active"
        or author_wc.world_id != profile.world.id
        or author_membership is None
        or author_membership.status != "active"
        or author_membership.world_id != profile.world.id
    ):
        return None
    blocked = db.scalar(
        select(models.WorldCharacterBlock.id).where(
            models.WorldCharacterBlock.world_id == profile.world.id,
            or_(
                and_(
                    models.WorldCharacterBlock.blocker_world_character_id
                    == profile.world_character.id,
                    models.WorldCharacterBlock.blocked_world_character_id
                    == author_wc.id,
                ),
                and_(
                    models.WorldCharacterBlock.blocker_world_character_id
                    == author_wc.id,
                    models.WorldCharacterBlock.blocked_world_character_id
                    == profile.world_character.id,
                ),
            ),
        )
    )
    if blocked is not None:
        return None
    liked, commented, reposted, followed = _existing_reactions(
        db, actor=profile, posts=[post]
    )
    actions = _allowed_actions(
        actor=profile,
        post=post,
        policy_actions=set(allowed_policy_actions),
        liked=liked,
        commented=commented,
        reposted=reposted,
        followed=followed,
    )
    return post, actions


def mark_claims_retryable(
    db: Session,
    *,
    observations: Iterable[models.WorldCharacterFeedObservation],
    now: datetime,
) -> None:
    current = _aware_utc(now)
    for observation in observations:
        observation.status = "retryable_failed"
        observation.lease_expires_at = current
        db.add(observation)
    db.flush()


def finalize_feed_cycle(
    db: Session,
    *,
    profile: ReadySearchProfile,
    claim: KeywordClaim,
    observations: tuple[models.WorldCharacterFeedObservation, ...],
    selected_index: int | None,
    selected_action: schemas.FeedAction | None,
    interaction_intent: schemas.FeedInteractionIntent | None,
    comment_purpose: schemas.FeedCommentPurpose | None,
    reason_code: schemas.FeedNoActionReason | None,
    public_action_execution_id: int | None,
    summary: dict[str, object],
    now: datetime,
) -> None:
    current = _aware_utc(now)
    for index, observation in enumerate(observations):
        observation.status = "observed"
        observation.observed_at = current
        if selected_index is None:
            observation.decision_outcome = "no_action"
            observation.reason_code = reason_code
        elif index == selected_index:
            observation.decision_outcome = "action_selected"
            observation.selected_action = selected_action
            observation.interaction_intent = interaction_intent
            observation.comment_purpose = comment_purpose
            observation.public_action_execution_id = public_action_execution_id
        else:
            observation.decision_outcome = "not_selected"
        db.add(observation)
    cursor = db.scalar(
        select(models.WorldCharacterFeedCursor)
        .where(
            models.WorldCharacterFeedCursor.world_character_id
            == profile.world_character.id
        )
        .with_for_update()
    )
    if cursor is None or cursor.world_id != profile.world.id:
        raise WorldFeedReadinessError("feed_cursor_invalid")
    cursor.next_keyword_offset = (claim.cursor_offset + KEYWORDS_PER_CYCLE) % KEYWORD_COUNT
    cursor.last_cycle_summary = summary
    cursor.version += 1
    db.add(cursor)
    db.flush()


def world_feed_cycle_status(
    db: Session,
    *,
    world_character: models.WorldCharacter,
    recent_limit: int = 12,
) -> schemas.WorldFeedCycleStatusRead:
    cursor = db.get(models.WorldCharacterFeedCursor, world_character.id)
    profile = db.scalar(
        select(models.WorldCommunityProfile)
        .where(
            models.WorldCommunityProfile.world_character_id == world_character.id,
            models.WorldCommunityProfile.status == "ready",
        )
        .order_by(
            models.WorldCommunityProfile.approved_at.desc(),
            models.WorldCommunityProfile.generated_at.desc(),
        )
    )
    keywords = tuple(
        keyword
        for raw_keyword in (profile.search_keywords if profile else [])
        if (keyword := normalize_search_text(raw_keyword, max_chars=40))
    )
    keyword_contract_ready = (
        len(keywords) == KEYWORD_COUNT
        and len(set(keywords)) == KEYWORD_COUNT
        and all(len(keyword) >= MIN_KEYWORD_LENGTH for keyword in keywords)
    )
    offset = cursor.next_keyword_offset if cursor else 0
    next_keywords = (
        [keywords[offset], keywords[(offset + 1) % KEYWORD_COUNT]]
        if keyword_contract_ready and offset in KEYWORD_OFFSETS
        else []
    )
    rows = list(
        db.scalars(
            select(models.WorldCharacterFeedObservation)
            .where(
                models.WorldCharacterFeedObservation.observer_world_character_id
                == world_character.id
            )
            .order_by(
                models.WorldCharacterFeedObservation.created_at.desc(),
                models.WorldCharacterFeedObservation.id.desc(),
            )
            .limit(max(1, min(recent_limit, 50)))
        )
    )
    post_ids = [row.post_id for row in rows]
    post_context: dict[str, tuple[str, str]] = {}
    if post_ids:
        context_rows = db.execute(
            select(models.Post.id, models.Post.title, models.Character.name)
            .join(
                models.WorldCharacter,
                models.WorldCharacter.id == models.Post.author_world_character_id,
            )
            .join(models.Character, models.Character.id == models.Post.author_character_id)
            .where(models.Post.id.in_(post_ids))
        ).all()
        post_context = {
            post_id: (title, author_name)
            for post_id, title, author_name in context_rows
        }
    return schemas.WorldFeedCycleStatusRead(
        world_id=world_character.world_id,
        world_character_id=world_character.id,
        feed_runtime_mode=world_character.feed_runtime_mode,
        runtime_state=_feed_runtime_state(
            db,
            world_character=world_character,
            cursor=cursor,
        ),
        profile_keyword_count=len(keywords),
        profile_keywords_ready=keyword_contract_ready,
        next_keywords=next_keywords,
        next_keyword_offset=offset,
        last_cycle_key=cursor.last_cycle_key if cursor else None,
        last_cycle_at=cursor.updated_at if cursor and cursor.last_cycle_key else None,
        last_run_id=cursor.last_run_id if cursor else None,
        last_cycle_summary=(
            dict(cursor.last_cycle_summary)
            if cursor and isinstance(cursor.last_cycle_summary, dict)
            else None
        ),
        recent_observations=[
            schemas.WorldFeedObservationRead(
                observation_id=row.id,
                post_id=row.post_id,
                post_title=post_context.get(row.post_id, ("삭제된 게시글", "알 수 없음"))[0],
                author_name=post_context.get(row.post_id, ("삭제된 게시글", "알 수 없음"))[1],
                post_created_at=row.post_created_at,
                status=row.status,
                decision_outcome=row.decision_outcome,
                selected_action=row.selected_action,
                interaction_intent=row.interaction_intent,
                comment_purpose=row.comment_purpose,
                reason_code=row.reason_code,
                matched_keywords=list(row.matched_keywords or []),
                matched_fields=list(row.matched_fields or []),
                rank_score=row.rank_score,
                observed_at=row.observed_at,
            )
            for row in rows
        ],
    )


def _feed_runtime_state(
    db: Session,
    *,
    world_character: models.WorldCharacter,
    cursor: models.WorldCharacterFeedCursor | None,
) -> str:
    if _is_imported_world_runtime_locked(db, world_character=world_character):
        return "imported_locked"
    if world_character.feed_runtime_mode != AUTONOMOUS_FEED_RUNTIME_MODE:
        return "routine_only_legacy_feed"
    if not world_character.autonomous_enabled:
        return "autonomy_disabled"
    summary = cursor.last_cycle_summary if cursor is not None else None
    reason_code = summary.get("reason_code") if isinstance(summary, dict) else None
    if reason_code in {
        "search_rebuilding",
        "search_schema_mismatch",
        "search_digest_stale",
        "search_unavailable",
    }:
        return "feed_search_degraded"
    return "three_lane_ready"


def _is_imported_world_runtime_locked(
    db: Session,
    *,
    world_character: models.WorldCharacter,
) -> bool:
    """Read package lineage without coupling this service to another service."""

    return bool(
        not world_character.autonomous_enabled
        and db.scalar(
            select(models.WorldPackageImport.import_id)
            .where(
                models.WorldPackageImport.imported_world_id
                == world_character.world_id
            )
            .limit(1)
        )
        is not None
    )


def owner_world_feed_cycle_status(
    db: Session,
    *,
    world_character_id: str,
    user: models.User,
) -> schemas.WorldFeedCycleStatusRead:
    world_character = db.get(models.WorldCharacter, world_character_id)
    if world_character is None:
        raise WorldFeedStatusNotFoundError(world_character_id)
    character = db.get(models.Character, world_character.character_id)
    if character is None or character.deleted_at is not None:
        raise WorldFeedStatusNotFoundError(world_character_id)
    if character.owner_id != user.id:
        raise WorldFeedStatusForbiddenError(world_character_id)
    membership = db.get(models.WorldMembership, world_character.membership_id)
    if (
        membership is None
        or membership.world_id != world_character.world_id
        or membership.user_id != user.id
    ):
        raise WorldFeedStatusForbiddenError(world_character_id)
    return world_feed_cycle_status(db, world_character=world_character)
