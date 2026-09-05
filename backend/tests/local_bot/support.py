"""Keep original behavior assertions while injecting the current real workflows."""

from functools import wraps
from types import SimpleNamespace

from app.domains.local_bot.service import actions
from app.runtime.local_bot.composition import build_bot_workflows


def bound_bot_actions():
    def bind(function):
        @wraps(function)
        def call(*args, **kwargs):
            return function(*args, **kwargs, workflows=build_bot_workflows())

        return call

    values = dict(vars(actions))
    for name in (
        "get_me",
        "get_state",
        "save_state",
        "list_feed",
        "list_following_feed",
        "get_post_thread",
        "list_notifications",
        "get_character_profile",
        "get_activity",
        "mark_notification_read",
        "create_post",
        "create_reply",
        "like_post",
        "unlike_post",
        "repost_post",
        "unrepost_post",
        "follow_profile",
        "unfollow_profile",
    ):
        values[name] = bind(getattr(actions, name))
    return SimpleNamespace(**values)
