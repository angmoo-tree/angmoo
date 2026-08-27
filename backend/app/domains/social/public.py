"""Stable public surface for P5 social discovery and search readiness."""

from app.domains.social.application import (
    KeywordPostLookup,
    SocialSearchBinding,
    current_social_search,
    find_keyword_post_ids,
    register_social_search,
    unregister_social_search,
)
from app.domains.social.domain import SocialSearchState, SocialSearchUnavailable
from app.domains.social.ports import SocialSearchIndexPort

__all__ = [
    "KeywordPostLookup",
    "SocialSearchBinding",
    "SocialSearchIndexPort",
    "SocialSearchState",
    "SocialSearchUnavailable",
    "current_social_search",
    "find_keyword_post_ids",
    "register_social_search",
    "unregister_social_search",
]
