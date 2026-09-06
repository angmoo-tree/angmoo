"""World feed readiness, discovery, claims and owner-visible cycle status."""

from __future__ import annotations

from datetime import datetime
import time
from typing import Iterable
from uuid import uuid4
from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from app.core.search_text import normalize_search_text
from app.domains.social.contracts.search_index import SocialSearchIndexPort
from app.domains.social.contracts.search_state import SocialSearchState
from app.domains.social.contracts.world_feed import (
    ReadySearchProfile,
    KeywordClaim,
    CandidateSearchResult,
    ObservationClaimResult,
    WorldFeedReferences,
    FeedWorldCharacter,
    FeedOwner,
)
from app.domains.social.exceptions import (
    WorldFeedError,
    WorldFeedReadinessError,
    WorldFeedStatusNotFoundError,
    WorldFeedStatusForbiddenError,
)
from app.domains.social.constants import (
    KEYWORDS_PER_CYCLE,
    KEYWORD_COUNT,
    MIN_KEYWORD_LENGTH,
    KEYWORD_OFFSETS,
    PER_KEYWORD_FETCH_LIMIT,
    RAW_MERGE_LIMIT,
    PLANNER_CANDIDATE_LIMIT,
    AUTHOR_CANDIDATE_LIMIT,
    OBSERVATION_LEASE,
)
from app.domains.social.models.feed import (
    WorldCharacterFeedCursor,
    WorldCharacterFeedObservation,
)
from app.domains.social.models.posts import Post
from app.domains.social.policies.world_feed import (
    _aware_utc,
    _age_bucket,
    _local_datetime,
    _allowed_actions,
)
from app.domains.social.repository import world_feed as repository
from app.domains.social.schemas import feed as feed_schemas
from app.domains.social.service.keyword_feed import find_keyword_post_ids
from app.domains.world_characters.contracts.runtime_modes import (
    AUTONOMOUS_FEED_RUNTIME_MODE,
)
from app.domains.world_characters.schemas.setup import WorldCommunityProfilePayload


def load_ready_search_profile(
    db: Session, *, references: WorldFeedReferences, world_character_id: str
) -> ReadySearchProfile:
    world_character = references.world_character(world_character_id)
    if world_character is None or world_character.status != "active":
        raise WorldFeedReadinessError("world_character_not_ready")
    if world_character.feed_runtime_mode != AUTONOMOUS_FEED_RUNTIME_MODE:
        raise WorldFeedReadinessError("feed_runtime_mode_not_enabled")
    character = references.character(world_character.character_id)
    membership = references.membership(world_character.membership_id)
    world = references.world(world_character.world_id)
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
    profile = references.ready_profile(world_character.id)
    if profile is None:
        raise WorldFeedReadinessError("world_community_profile_not_ready")
    character_hash = references.character_hash(character)
    if (
        world_character.character_contract_hash != character_hash
        or world_character.world_contract_hash != world.contract_hash
        or profile.character_contract_hash != character_hash
        or profile.world_contract_hash != world.contract_hash
    ):
        raise WorldFeedReadinessError("world_community_profile_stale")
    try:
        validated = WorldCommunityProfilePayload(
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
        references=references,
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
    cursor = repository.cursor_for_update(
        db, world_character_id=profile.world_character.id
    )
    if cursor is None:
        cursor = WorldCharacterFeedCursor(
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
            cursor = repository.cursor_for_update(
                db, world_character_id=profile.world_character.id
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


def search_world_feed_candidates(
    db: Session,
    *,
    references: WorldFeedReferences,
    profile: ReadySearchProfile,
    keywords: tuple[str, str],
    allowed_policy_actions: Iterable[str],
    now: datetime,
    search_index: SocialSearchIndexPort | None,
    search_state: SocialSearchState,
) -> CandidateSearchResult:
    started = time.perf_counter()
    candidate_rows = references.candidate_rows(profile)
    lookup = find_keyword_post_ids(
        search_index,
        search_state=search_state,
        world_id=profile.world.id,
        keywords=keywords,
        per_keyword_limit=PER_KEYWORD_FETCH_LIMIT,
        merged_limit=RAW_MERGE_LIMIT,
    )
    rows_by_post_id: dict[str, tuple[Post, FeedWorldCharacter]] = {}
    if lookup.post_ids:
        canonical_rows = candidate_rows(lookup.post_ids)
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
        for row in repository.observations_for_posts(
            db, observer_id=profile.world_character.id, post_ids=rows_by_post_id
        )
    }
    posts = [row[0] for row in rows_by_post_id.values()]
    liked, commented, reposted, followed = repository._existing_reactions(
        db, actor=profile, posts=posts
    )
    policy_actions = set(allowed_policy_actions)
    ranked: list[
        tuple[
            float,
            Post,
            FeedWorldCharacter,
            list[str],
            list[str],
            list[feed_schemas.FeedAction],
        ]
    ] = []
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
    selected: list[
        tuple[
            float,
            Post,
            FeedWorldCharacter,
            list[str],
            list[str],
            list[feed_schemas.FeedAction],
        ]
    ] = []
    author_counts: dict[str, int] = {}
    for item in ranked:
        author_id = item[2].id
        if author_counts.get(author_id, 0) >= AUTHOR_CANDIDATE_LIMIT:
            continue
        selected.append(item)
        author_counts[author_id] = author_counts.get(author_id, 0) + 1
        if len(selected) >= PLANNER_CANDIDATE_LIMIT:
            break
    candidates: list[feed_schemas.WorldFeedCandidateRead] = []
    for index, (
        score,
        post,
        world_character,
        matched_keywords,
        matched_fields,
        actions,
    ) in enumerate(selected):
        created_at = _aware_utc(post.created_at)
        age_seconds = max(0, int((current - created_at).total_seconds()))
        candidates.append(
            feed_schemas.WorldFeedCandidateRead(
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
    candidates: tuple[feed_schemas.WorldFeedCandidateRead, ...],
    cycle_key: str,
    run_id: str,
    now: datetime,
) -> ObservationClaimResult:
    current = _aware_utc(now)
    claimed_candidates: list[feed_schemas.WorldFeedCandidateRead] = []
    observations: list[WorldCharacterFeedObservation] = []
    conflicts = 0
    for candidate in candidates:
        observation = repository.observation_for_update(
            db, observer_id=profile.world_character.id, post_id=candidate.post_id
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
            observation = WorldCharacterFeedObservation(
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
            candidate.model_copy(update={"candidate_index": len(claimed_candidates)})
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
    references: WorldFeedReferences,
    profile: ReadySearchProfile,
    candidate: feed_schemas.WorldFeedCandidateRead,
    allowed_policy_actions: Iterable[str],
) -> tuple[Post, list[feed_schemas.FeedAction]] | None:
    post = repository.get_post(db, candidate.post_id)
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
    actor_wc = references.world_character(profile.world_character.id)
    actor_membership = (
        references.membership(actor_wc.membership_id) if actor_wc else None
    )
    author_wc = references.world_character(candidate.author_world_character_id)
    author_membership = (
        references.membership(author_wc.membership_id) if author_wc else None
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
    blocked = repository.is_blocked(
        db,
        world_id=profile.world.id,
        actor_id=profile.world_character.id,
        author_id=author_wc.id,
    )
    if blocked is not None:
        return None
    liked, commented, reposted, followed = repository._existing_reactions(
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
    observations: Iterable[WorldCharacterFeedObservation],
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
    observations: tuple[WorldCharacterFeedObservation, ...],
    selected_index: int | None,
    selected_action: feed_schemas.FeedAction | None,
    interaction_intent: feed_schemas.FeedInteractionIntent | None,
    comment_purpose: feed_schemas.FeedCommentPurpose | None,
    reason_code: feed_schemas.FeedNoActionReason | None,
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
    cursor = repository.cursor_for_update(
        db, world_character_id=profile.world_character.id
    )
    if cursor is None or cursor.world_id != profile.world.id:
        raise WorldFeedReadinessError("feed_cursor_invalid")
    cursor.next_keyword_offset = (
        claim.cursor_offset + KEYWORDS_PER_CYCLE
    ) % KEYWORD_COUNT
    cursor.last_cycle_summary = summary
    cursor.version += 1
    db.add(cursor)
    db.flush()


def world_feed_cycle_status(
    db: Session,
    *,
    references: WorldFeedReferences,
    world_character: FeedWorldCharacter,
    recent_limit: int = 12,
) -> feed_schemas.WorldFeedCycleStatusRead:
    cursor = repository.get_cursor(db, world_character.id)
    profile = references.ready_profile(world_character.id)
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
        repository.recent_observations(
            db, observer_id=world_character.id, recent_limit=recent_limit
        )
    )
    post_ids = [row.post_id for row in rows]
    post_context: dict[str, tuple[str, str]] = {}
    if post_ids:
        context_rows = references.post_context(post_ids)
        post_context = {
            post_id: (title, author_name)
            for post_id, title, author_name in context_rows
        }
    return feed_schemas.WorldFeedCycleStatusRead(
        world_id=world_character.world_id,
        world_character_id=world_character.id,
        feed_runtime_mode=world_character.feed_runtime_mode,
        runtime_state=_feed_runtime_state(
            db,
            references=references,
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
            feed_schemas.WorldFeedObservationRead(
                observation_id=row.id,
                post_id=row.post_id,
                post_title=post_context.get(
                    row.post_id, ("삭제된 게시글", "알 수 없음")
                )[0],
                author_name=post_context.get(
                    row.post_id, ("삭제된 게시글", "알 수 없음")
                )[1],
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
    references: WorldFeedReferences,
    world_character: FeedWorldCharacter,
    cursor: WorldCharacterFeedCursor | None,
) -> str:
    if _is_imported_world_runtime_locked(
        db, references=references, world_character=world_character
    ):
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
    references: WorldFeedReferences,
    world_character: FeedWorldCharacter,
) -> bool:
    """Read package lineage without coupling this service to another service."""

    return bool(
        not world_character.autonomous_enabled
        and references.imported_lineage(world_character.world_id) is not None
    )


def owner_world_feed_cycle_status(
    db: Session,
    *,
    references: WorldFeedReferences,
    world_character_id: str,
    user: FeedOwner,
) -> feed_schemas.WorldFeedCycleStatusRead:
    world_character = references.world_character(world_character_id)
    if world_character is None:
        raise WorldFeedStatusNotFoundError(world_character_id)
    character = references.character(world_character.character_id)
    if character is None or character.deleted_at is not None:
        raise WorldFeedStatusNotFoundError(world_character_id)
    if character.owner_id != user.id:
        raise WorldFeedStatusForbiddenError(world_character_id)
    membership = references.membership(world_character.membership_id)
    if (
        membership is None
        or membership.world_id != world_character.world_id
        or membership.user_id != user.id
    ):
        raise WorldFeedStatusForbiddenError(world_character_id)
    return world_feed_cycle_status(
        db, references=references, world_character=world_character
    )
