"""Embedded lifecycle for the canonical social FTS5 projection."""

from __future__ import annotations

from collections.abc import Iterable
import logging

from sqlalchemy import event, select
from sqlalchemy.orm import Session, sessionmaker

from app import models
from app.core.search_text import build_post_search_document
from app.domains.runtime.public import SearchIndexDocument
from app.domains.social.public import (
    SocialSearchState,
    register_social_search,
    unregister_social_search,
)
from app.runtime.search.sqlite_fts5 import (
    SqliteFts5Error,
    SqliteFts5SchemaError,
    SqliteFts5SearchIndex,
)


logger = logging.getLogger(__name__)
_PENDING_POST_IDS = "angmoo_social_search_pending_post_ids"


def _post_search_document(post: models.Post) -> SearchIndexDocument | None:
    searchable = (
        post.world_id is not None
        and post.author_world_character_id is not None
        and post.visibility == "public"
        and post.deleted_at is None
        and post.report_hidden_at is None
        and post.reply_to_post_id is None
        and post.post_type != "repost"
        and post.repost_of_post_id is None
    )
    if not searchable:
        return None
    text = post.search_document or build_post_search_document(
        title=post.title,
        body=post.body,
        topic_signature=post.topic_signature,
    )
    return SearchIndexDocument(
        document_id=post.id,
        world_id=post.world_id,
        kind="world_post",
        text=text,
        metadata={
            "visibility": post.visibility,
            "author_world_character_id": post.author_world_character_id,
        },
        character_id=post.author_character_id,
        source_id=post.id,
        occurred_at=post.created_at.isoformat() if post.created_at else None,
    )


class _SqlAlchemySocialSearchDocumentSource:
    """Temporary L4 adapter from legacy Post rows to neutral documents."""

    def __init__(self, factory: sessionmaker[Session]) -> None:
        self._factory = factory

    def all_documents(self) -> tuple[SearchIndexDocument, ...]:
        with self._factory() as db:
            posts = db.scalars(select(models.Post).order_by(models.Post.id)).all()
            return tuple(
                document
                for post in posts
                if (document := _post_search_document(post)) is not None
            )

    def documents_for_ids(
        self,
        post_ids: Iterable[str],
    ) -> dict[str, SearchIndexDocument]:
        ids = tuple(dict.fromkeys(str(post_id) for post_id in post_ids if post_id))
        if not ids:
            return {}
        with self._factory() as db:
            posts = db.scalars(
                select(models.Post).where(models.Post.id.in_(ids))
            ).all()
            documents: dict[str, SearchIndexDocument] = {}
            for post in posts:
                document = _post_search_document(post)
                if document is not None:
                    documents[post.id] = document
            return documents


class EmbeddedSocialSearchProjection:
    """Rebuild FTS5 from SQLite and mirror committed post changes.

    Projection failures never cause canonical writes to roll back.  Instead the
    P5 keyword lane becomes explicitly degraded while Inbox and Routine lanes
    continue independently.  The next application startup performs a complete
    deterministic rebuild from canonical SQLite.
    """

    def __init__(
        self,
        *,
        index: SqliteFts5SearchIndex,
        session_factory: sessionmaker[Session],
    ) -> None:
        self.index = index
        self._factory = session_factory
        self._source = _SqlAlchemySocialSearchDocumentSource(session_factory)
        self._listening = False

    def start(self) -> None:
        register_social_search(
            self.index,
            state=SocialSearchState.REBUILDING,
        )
        try:
            self.index.open()
            doctor = self.index.rebuild(self._source.all_documents())
            if not doctor.healthy:
                register_social_search(
                    self.index,
                    state=SocialSearchState.DIGEST_STALE,
                )
                return
            self._listen()
            register_social_search(
                self.index,
                state=SocialSearchState.READY,
            )
        except SqliteFts5SchemaError:
            logger.exception("social_search_projection_schema_mismatch")
            register_social_search(
                self.index,
                state=SocialSearchState.SCHEMA_MISMATCH,
            )
        except (SqliteFts5Error, OSError, ValueError):
            logger.exception("social_search_projection_unavailable")
            register_social_search(
                self.index,
                state=SocialSearchState.UNAVAILABLE,
            )
        except Exception:
            # Canonical schema/read failures are also projection failures.  The
            # backend must remain available so the independent P5 lanes and
            # owner-controlled writes can continue without a silent SQL scan.
            logger.exception("social_search_projection_rebuild_failed")
            register_social_search(
                self.index,
                state=SocialSearchState.UNAVAILABLE,
            )

    def stop(self) -> None:
        self._unlisten()
        unregister_social_search(self.index)
        self.index.close()

    def _listen(self) -> None:
        if self._listening:
            return
        event.listen(self._factory, "after_flush", self._after_flush)
        event.listen(self._factory, "after_commit", self._after_commit)
        event.listen(self._factory, "after_rollback", self._after_rollback)
        self._listening = True

    def _unlisten(self) -> None:
        if not self._listening:
            return
        event.remove(self._factory, "after_flush", self._after_flush)
        event.remove(self._factory, "after_commit", self._after_commit)
        event.remove(self._factory, "after_rollback", self._after_rollback)
        self._listening = False

    def _after_flush(self, session: Session, _flush_context: object) -> None:
        pending = session.info.setdefault(_PENDING_POST_IDS, set())
        for entity in session.new | session.dirty | session.deleted:
            if isinstance(entity, models.Post):
                pending.add(entity.id)

    def _after_commit(self, session: Session) -> None:
        post_ids = tuple(session.info.pop(_PENDING_POST_IDS, ()))
        if not post_ids:
            return
        try:
            documents = self._source.documents_for_ids(post_ids)
            for post_id in sorted(post_ids):
                document = documents.get(post_id)
                if document is None:
                    self.index.remove(document_id=post_id)
                else:
                    self.index.upsert(document)
            doctor = self.index.doctor()
            register_social_search(
                self.index,
                state=(
                    SocialSearchState.READY
                    if doctor.healthy
                    else SocialSearchState.DIGEST_STALE
                ),
            )
        except Exception:
            logger.exception("social_search_projection_commit_sync_failed")
            register_social_search(
                self.index,
                state=SocialSearchState.DIGEST_STALE,
            )

    def _after_rollback(self, session: Session) -> None:
        session.info.pop(_PENDING_POST_IDS, None)


__all__ = ["EmbeddedSocialSearchProjection"]
