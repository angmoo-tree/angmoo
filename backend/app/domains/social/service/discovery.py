"""Search admission, visible results and Today activity scoring."""
from sqlalchemy.orm import Session
from app.domains.social.contracts.discovery import DiscoveryReads
from app.domains.social.schemas import community as schemas
from app.domains.social.service.feed import _today_start_utc
from app.domains.social.service.profiles import _character_search_result
from app.domains.social.service.presentation import _post_summary
from app.domains.social.service.visibility import _is_post_public_context_visible
from app.domains.social.utils.limits import _safe_limit
from app.domains.characters.service import search as character_search


class SocialDiscoveryService:
    def __init__(self, reads: DiscoveryReads):
        self.reads = reads

    def search_nest(
        self, db: Session, *, query: str, limit: int = 20, offset: int = 0
    ) -> schemas.SearchResults:
        normalized_query = query.strip()
        if not normalized_query:
            return schemas.SearchResults(query="", posts=[], characters=[])
        safe_limit = _safe_limit(limit)
        safe_offset = max(0, offset)
        posts, posts_next_offset = self.reads.search_posts(
            db, normalized_query, limit=safe_limit, offset=safe_offset
        )
        characters, characters_next_offset = character_search.search_characters(
            db, normalized_query, limit=safe_limit, offset=safe_offset
        )
        return schemas.SearchResults(
            query=normalized_query,
            posts=[
                _post_summary(db, post)
                for post in posts
                if _is_post_public_context_visible(db, post)
            ],
            characters=[_character_search_result(character) for character in characters],
            posts_next_offset=posts_next_offset,
            characters_next_offset=characters_next_offset,
        )

    def list_today_activity(self, db: Session, *, limit: int = 3) -> list[schemas.TodayActivityRead]:
        day_start = _today_start_utc()
        post_types = ("post_created", "quoted")
        reply_types = ("commented", "replied")
        like_types = ("liked",)

        rows = self.reads.list_today_activity_rows(db, day_start=day_start, post_types=post_types, reply_types=reply_types, like_types=like_types)

        rankings = []
        for row in rows:
            post_count = int(row.post_count or 0)
            reply_count = int(row.reply_count or 0)
            like_count = int(row.like_count or 0)
            score = post_count * 3 + reply_count * 2 + like_count
            if score <= 0:
                continue
            rankings.append(
                schemas.TodayActivityRead(
                    character_id=row.id,
                    name=row.name,
                    handle=row.handle,
                    avatar_url=row.avatar_url,
                    post_count=post_count,
                    reply_count=reply_count,
                    like_count=like_count,
                    score=score,
                )
            )

        safe_limit = max(1, min(limit, 50))
        return sorted(rankings, key=lambda item: (-item.score, item.name))[:safe_limit]
