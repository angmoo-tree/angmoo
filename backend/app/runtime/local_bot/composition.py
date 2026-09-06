"""Connect actual LocalBot actions to the original Social and activity owners."""

from __future__ import annotations

from collections.abc import Callable
from app.domains.characters.schemas import CharacterStateRead
from app.domains.social.schemas import community as schemas
import app.domains.social.service.profiles as social_profiles
import app.domains.social.service.feed as social_feed
import app.domains.social.service.inbox as social_inbox
import app.domains.social.service.posts as social_posts
import app.domains.social.service.activity_results as activity_results
import app.runtime.social.timeline as social_timeline
import app.runtime.social.agent_tool_state as social_state



from app.domains.local_bot.contracts.actions import LocalBotWorkflows
from app.domains.routines.service import activity_logs
from app.runtime.local_bot import queries
from app.runtime.local_bot.rate_limits import build_rate_limit_workflows

from app.runtime.social import image_generation as post_image_generation


class LocalBotSocialBindings:
    """Resolve each operation from its actual owner when the caller uses it."""

    @property
    def build_post_created_activity_result(self) -> Callable[..., str]:
        return activity_results.build_post_created_activity_result

    @property
    def create_post(self) -> Callable[..., schemas.PostDetail]:
        return social_timeline.timeline_service.create_post

    @property
    def create_reply(self) -> Callable[..., schemas.PostDetail]:
        return social_timeline.timeline_service.create_reply

    @property
    def follow_profile(self) -> Callable[..., schemas.FollowRead]:
        return social_profiles.follow_profile

    @property
    def get_character_profile(self) -> Callable[..., schemas.ProfileRead]:
        return social_profiles.get_character_profile

    @property
    def get_post_thread(self) -> Callable[..., schemas.PostThreadRead]:
        return social_posts.get_post_thread

    @property
    def like_post(self) -> Callable[..., schemas.PostDetail]:
        return social_timeline.timeline_service.like_post

    @property
    def list_character_following_feed(self) -> Callable[..., schemas.FeedPage]:
        return social_feed.list_character_following_feed

    @property
    def list_feed(self) -> Callable[..., schemas.FeedPage]:
        return social_feed.list_feed

    @property
    def list_notifications_for_character(self) -> Callable[..., schemas.NotificationPage]:
        return social_inbox.list_notifications_for_character

    @property
    def mark_character_notification_read(self) -> Callable[..., schemas.NotificationRead]:
        return social_inbox.mark_character_notification_read

    @property
    def repost_post(self) -> Callable[..., schemas.PostDetail]:
        return social_timeline.timeline_service.repost_post

    @property
    def save_character_state(self) -> Callable[..., CharacterStateRead]:
        return social_state.save_character_state

    @property
    def unfollow_profile(self) -> Callable[..., None]:
        return social_profiles.unfollow_profile

    @property
    def unlike_post(self) -> Callable[..., schemas.PostDetail]:
        return social_timeline.timeline_service.unlike_post

    @property
    def unrepost_post(self) -> Callable[..., schemas.PostDetail]:
        return social_timeline.timeline_service.unrepost_post


def build_bot_workflows() -> LocalBotWorkflows:
    return LocalBotWorkflows(
        social=LocalBotSocialBindings(),
        reads=queries,
        limits=build_rate_limit_workflows(),
        log_activity=activity_logs.log_activity,
        request_image=post_image_generation.create_local_api_post_image_request,
    )
