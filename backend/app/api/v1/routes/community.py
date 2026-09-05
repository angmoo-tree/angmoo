"""Compose Social and Character state routes in their original API order."""
from fastapi import APIRouter
from app.domains.characters.router import save_character_state, state_router
from app.domains.social.router import router as social_router
from app.domains.social.router import (
    list_posts,
    list_feed,
    list_today_activity,
    list_today_popular_posts,
    search_nest,
    list_following_feed,
    list_character_following_feed,
    create_post,
    get_post_thread,
    get_post,
    delete_post,
    report_post,
    create_reply,
    create_quote,
    create_comment,
    like_post,
    unlike_post,
    repost_post,
    unrepost_post,
    get_user_profile,
    get_user_profile_feed,
    get_user_profile_connections,
    get_character_profile,
    get_character_profile_feed,
    get_character_profile_connections,
    get_follow_status,
    follow_profile,
    unfollow_profile,
    list_notifications,
    mark_notification_read,
    get_character_activity,
)

router = APIRouter(tags=["community"])
for route in social_router.routes:
    if getattr(route, "endpoint", None) is get_character_activity:
        router.routes.extend(state_router.routes)
    router.routes.append(route)
