"""Same-session bounded candidate queries with canonical World authorization."""
from collections import defaultdict, Counter
from datetime import timedelta
from time import perf_counter

from sqlalchemy import and_, exists, or_, select
from sqlalchemy.orm import Session

from app.domains.relationships.models.social import SocialEvent, RelationshipState
from app.domains.social.models.feed import WorldCharacterBlock, WorldCharacterFeedObservation
from app.domains.social.models.posts import Post, ProfileFollow
from app.domains.social.models.topics import RecommendationPost, RecommendationPostTopic, RecommendationTopicSource
from app.domains.social.policies.recommendation import Candidate, compose
from app.domains.social.policies.world_feed import _aware_utc, _age_bucket, _local_datetime, _allowed_actions
from app.domains.social.repository.world_feed import _existing_reactions
from app.domains.social.schemas.feed import WorldFeedCandidateRead
from app.domains.social.contracts.world_feed import CandidateSearchResult
from app.domains.social.service.recommendation_topics import body_digest
from app.domains.world_characters.models import WorldCharacter
from app.domains.worlds.models import WorldMembership
from app.domains.characters.models import Character


def relation_authors(db, profile, now):
    followed = list(db.scalars(select(ProfileFollow.target_world_character_id).where(
        ProfileFollow.world_id == profile.world.id,
        ProfileFollow.follower_world_character_id == profile.world_character.id,
    ).order_by(ProfileFollow.created_at.desc(), ProfileFollow.id.desc()).limit(16)))
    event_query = select(SocialEvent.actor_world_character_id, SocialEvent.target_world_character_id, SocialEvent.occurred_at).where(
        SocialEvent.world_id == profile.world.id,
        SocialEvent.result == "succeeded", SocialEvent.retrieval_status == "eligible",
        SocialEvent.event_type.in_(("comment_created", "reply_created", "like_added", "repost_added", "follow_added")),
        SocialEvent.occurred_at >= now - timedelta(days=30),
    ).order_by(SocialEvent.occurred_at.desc(), SocialEvent.id.desc()).limit(32)
    events = []
    for direction in (SocialEvent.actor_world_character_id, SocialEvent.target_world_character_id):
        events.extend(db.execute(event_query.where(direction == profile.world_character.id)).all())
    events.sort(key=lambda row: row[2], reverse=True)
    result = {identity: 1.0 for identity in followed if identity}
    for actor, target, _ in events:
        other = target if actor == profile.world_character.id else actor
        if other and other != profile.world_character.id and (other in result or len(result) < 16):
            result[other] = max(result.get(other, 0), .7)
    states = db.scalars(select(RelationshipState).where(
        RelationshipState.world_id == profile.world.id,
        RelationshipState.actor_world_character_id == profile.world_character.id,
        RelationshipState.target_world_character_id.in_(result),
    ))
    for state in states:
        result[state.target_world_character_id] = min(1, result[state.target_world_character_id] + .1 * state.familiarity / 100)
    return result


def candidates(db: Session, *, profile, allowed_policy_actions, now, references):
    started = perf_counter()
    current = _aware_utc(now)
    actor = profile.world_character.id
    world = profile.world.id
    interests = list(db.scalars(select(RecommendationTopicSource.topic_id).where(
        RecommendationTopicSource.world_id == world,
        RecommendationTopicSource.world_character_id == actor,
    ).order_by(RecommendationTopicSource.topic_id).limit(24)))
    relations = relation_authors(db, profile, current)
    author_exposures = Counter(db.scalars(select(Post.author_world_character_id).join(
        WorldCharacterFeedObservation, WorldCharacterFeedObservation.post_id == Post.id,
    ).where(WorldCharacterFeedObservation.observer_world_character_id == actor,
            WorldCharacterFeedObservation.status == "observed").order_by(
        WorldCharacterFeedObservation.created_at.desc(), WorldCharacterFeedObservation.id.desc(),
    ).limit(200)))
    seen = exists(select(WorldCharacterFeedObservation.id).where(
        WorldCharacterFeedObservation.observer_world_character_id == actor,
        WorldCharacterFeedObservation.post_id == Post.id,
        or_(WorldCharacterFeedObservation.status == "observed",
            and_(WorldCharacterFeedObservation.status == "claimed", WorldCharacterFeedObservation.lease_expires_at > current)),
    ))
    blocked = exists(select(WorldCharacterBlock.id).where(
        WorldCharacterBlock.world_id == world,
        or_(and_(WorldCharacterBlock.blocker_world_character_id == actor,
                 WorldCharacterBlock.blocked_world_character_id == Post.author_world_character_id),
            and_(WorldCharacterBlock.blocked_world_character_id == actor,
                 WorldCharacterBlock.blocker_world_character_id == Post.author_world_character_id)),
    ))
    base = select(Post.id, Post.author_world_character_id, Post.created_at).join(
        RecommendationPost, RecommendationPost.post_id == Post.id,
    ).join(WorldCharacter, WorldCharacter.id == Post.author_world_character_id).join(
        WorldMembership, WorldMembership.id == WorldCharacter.membership_id,
    ).join(Character, Character.id == WorldCharacter.character_id).where(
        Character.deleted_at.is_(None), Character.owner_id == WorldMembership.user_id,
        Post.world_id == world, RecommendationPost.world_id == world,
        WorldCharacter.world_id == world, WorldCharacter.status == "active",
        WorldMembership.world_id == world, WorldMembership.status == "active",
        Post.visibility == "public", Post.deleted_at.is_(None), Post.report_hidden_at.is_(None),
        Post.reply_to_post_id.is_(None), Post.post_type != "repost", Post.repost_of_post_id.is_(None),
        Post.author_world_character_id != actor, ~seen, ~blocked)
    metadata, sources = {}, defaultdict(set)
    rejected = set()
    body_cache = {}
    reaction_cache = (set(), set(), set(), set())
    cursors = {}
    examined = 0
    for round_index in range(3):
        for lane, size in (("latest", 24), ("interest", 32), ("relation", 16), ("explore", 8)):
            size = min(size, 200 - examined)
            if size <= 0:
                break
            parts = interests if lane == "interest" else list(relations) if lane == "relation" else [None]
            rows = []
            for part_index, part in enumerate(parts):
                take = (size - len(rows) + len(parts) - part_index - 1) // (len(parts) - part_index)
                if take <= 0:
                    break
                # LIMIT applies to the indexed discovery window before exclusions.
                # A mostly-seen World must not scan its entire history to fill a page.
                query = select(RecommendationPost.post_id, Post.author_world_character_id,
                               RecommendationPost.created_at).select_from(RecommendationPost).join(
                    Post, Post.id == RecommendationPost.post_id,
                ).where(RecommendationPost.world_id == world)
                order_time, order_id = RecommendationPost.created_at, RecommendationPost.post_id
                if lane == "interest":
                    query = query.join(RecommendationPostTopic, RecommendationPostTopic.post_id == Post.id).where(
                        RecommendationPostTopic.world_id == world, RecommendationPostTopic.topic_id == part)
                    order_time, order_id = RecommendationPostTopic.created_at, RecommendationPostTopic.post_id
                elif lane == "relation":
                    query = query.where(Post.world_id == world, Post.author_world_character_id == part)
                    order_time, order_id = Post.created_at, Post.id
                cursor_key = (lane, part)
                if lane == "explore" and cursor_key not in cursors:
                    latest = sorted((stamp, identity) for identity, (_, stamp) in metadata.items() if "latest" in sources[identity])
                    if len(latest) >= 10:
                        cursors[cursor_key] = latest[-10]
                if cursor_key in cursors:
                    stamp, identity = cursors[cursor_key]
                    query = query.where(or_(order_time < stamp, and_(order_time == stamp, order_id < identity)))
                page = db.execute(query.order_by(order_time.desc(), order_id.desc()).limit(take)).all()
                rows.extend(page)
                if page:
                    cursors[cursor_key] = (page[-1][2], page[-1][0])
            examined += len(rows)
            eligible = set(db.scalars(base.with_only_columns(Post.id).where(
                Post.id.in_([row[0] for row in rows]),
            ))) if rows else set()
            rows = [row for row in rows if row[0] in eligible]
            overlapping = set()
            if lane == "explore" and rows and interests:
                overlapping = set(db.scalars(select(RecommendationPostTopic.post_id).where(
                    RecommendationPostTopic.world_id == world,
                    RecommendationPostTopic.post_id.in_([row[0] for row in rows]),
                    RecommendationPostTopic.topic_id.in_(interests),
                )))
            for identity, author, stamp in rows:
                if identity in rejected:
                    continue
                if lane == "explore" and identity in overlapping:
                    continue
                metadata[identity] = (author, _aware_utc(stamp))
                sources[identity].add(lane)
        options = [Candidate(identity, author, stamp, float("interest" in sources[identity]),
                   relations.get(author, 0), frozenset(sources[identity]), 1/(1+author_exposures[author])) for identity, (author, stamp) in metadata.items()]
        selection = compose(options, now=current, seed=actor + current.isoformat())
        # Replace selected posts rejected by the canonical body/action checks
        # before deciding that quotas are full. Never read outside the raw budget.
        for _ in range(10):
            missing_ids = [c.id for c, _ in selection if c.id not in body_cache]
            if missing_ids:
                fresh_rows = references.candidate_rows(profile)(missing_ids)
                body_cache.update(fresh_rows)
                fresh_reactions = _existing_reactions(db, actor=profile, posts=[r[0] for r in fresh_rows.values()])
                for cached, fresh in zip(reaction_cache, fresh_reactions):
                    cached.update(fresh)
            invalid = set()
            for candidate, _ in selection:
                row = body_cache.get(candidate.id)
                if row is None:
                    invalid.add(candidate.id)
                    continue
                post = row[0]
                if any(avoid in field.casefold() for avoid in profile.avoid_topics for field in (post.title, post.body)) or not _allowed_actions(
                    actor=profile, post=post, policy_actions=set(allowed_policy_actions),
                    liked=reaction_cache[0], commented=reaction_cache[1],
                    reposted=reaction_cache[2], followed=reaction_cache[3],
                ):
                    invalid.add(candidate.id)
            if not invalid:
                break
            rejected.update(invalid)
            for identity in invalid:
                metadata.pop(identity, None)
            options = [c for c in options if c.id not in rejected]
            selection = compose(options, now=current, seed=actor + current.isoformat())
        lanes = [lane for _, lane in selection]
        quotas_filled = all(lanes.count(lane) >= count for lane, count in (("latest", 10), ("interest", 5), ("relation", 3), ("explore", 2)))
        if (len(selection) >= 20 and quotas_filled) or examined >= 200:
            break
    # Only the selected bodies are materialized, with a second canonical scope check.
    rows = references.candidate_rows(profile)([c.id for c, lane in selection])
    signatures = {identity: (signature, digest) for identity, signature, digest in db.execute(select(
        RecommendationPost.post_id, RecommendationPost.final_signature, RecommendationPost.signature_body_digest,
    ).where(RecommendationPost.post_id.in_(rows), RecommendationPost.world_id == world))}
    reactions = reaction_cache
    results = []
    budget = 18000
    for position, (candidate, lane) in enumerate(selection):
        if candidate.id not in rows:
            continue
        post, author = rows[candidate.id]
        signature, digest = signatures.get(post.id, (None, None))
        signature = signature if digest == body_digest(post.title, post.body) else None
        fields = (post.title, post.body, signature or "")
        if any(avoid in field.casefold() for avoid in profile.avoid_topics for field in fields):
            continue
        actions = _allowed_actions(actor=profile, post=post, policy_actions=set(allowed_policy_actions),
                                   liked=reactions[0], commented=reactions[1], reposted=reactions[2], followed=reactions[3])
        if not actions or budget <= 0:
            continue
        remaining = len(selection) - position
        body_limit = min(1200, budget) if position < 10 else min(1200, budget // remaining)
        body = post.body[:body_limit]
        budget -= len(body)
        age = max(0, int((current-candidate.created_at).total_seconds()))
        results.append(WorldFeedCandidateRead(candidate_index=len(results), post_id=post.id,
            author_world_character_id=author.id, author_character_id=author.character_id, author_name=post.author_name,
            title=post.title[:160], body_preview=body, topic_signature=(signature or "")[:300],
            created_at=candidate.created_at, world_local_datetime=_local_datetime(candidate.created_at, profile.world.timezone),
            age_seconds=age, age_bucket=_age_bucket(age), matched_keywords=[], matched_fields=[],
            rank_score=.45*candidate.interest+.25*candidate.relation, allowed_actions=actions,
            sources=sorted(candidate.sources), allocated_lane=lane))
    from app.runtime.social.feed_relationship_context import refresh
    results = refresh(db, profile, results)
    return CandidateSearchResult(tuple(results), examined, len(selection), int((perf_counter()-started)*1000))
