"""Wire canonical preflight policy to the original same-Session SQL reads."""

from sqlalchemy.orm import Session
from app.domains.chat.service.retrieval_policy import RetrievalPolicyResolver
from app.runtime.chat import retrieval_queries
from app.domains.social.repository.blocks import world_character_pair_is_blocked


def build_retrieval_policy(session: Session) -> RetrievalPolicyResolver:
    return RetrievalPolicyResolver(
        session, retrieval_queries, world_character_pair_is_blocked
    )


SqlAlchemyRetrievalPolicyResolver = build_retrieval_policy

__all__ = ["build_retrieval_policy", "SqlAlchemyRetrievalPolicyResolver"]
