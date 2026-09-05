"""Stable Social errors shared by HTTP and autonomous callers."""
from dataclasses import dataclass


class CommunityServiceError(Exception):
    pass


class PostNotFoundError(CommunityServiceError):
    pass


class CharacterNotFoundError(CommunityServiceError):
    pass


class AgentRunAuthorizationError(CommunityServiceError):
    pass


class PostWorldScopeError(CommunityServiceError):
    pass


class CharacterOwnershipError(CommunityServiceError):
    pass


class CharacterSuspendedError(CharacterOwnershipError):
    pass


class ProfileNotFoundError(CommunityServiceError):
    pass


class FollowSelfError(CommunityServiceError):
    pass


class NotificationNotFoundError(CommunityServiceError):
    pass


class LegacyCommentsDisabledError(CommunityServiceError):
    pass


class PostReportNotAllowedError(CommunityServiceError):
    pass


class CommunityRateLimitedError(CommunityServiceError):
    def __init__(self, retry_after_seconds: int) -> None:
        self.retry_after_seconds = max(1, retry_after_seconds)
        super().__init__("Community action temporarily rate limited")


@dataclass(frozen=True)
class CommunityQuotaExceeded(Exception):
    retry_after_seconds: int
