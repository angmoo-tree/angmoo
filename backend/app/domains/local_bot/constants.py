from datetime import timedelta

POST_COOLDOWN = timedelta(minutes=30)

MAX_POSTS_PER_DAY = 6

REPLY_COOLDOWN = timedelta(minutes=2)

MAX_REPLIES_PER_DAY = 30

REACTION_COOLDOWN = timedelta(seconds=30)

MAX_REACTIONS_PER_DAY = 100

STATE_COOLDOWN = timedelta(seconds=30)

READ_WINDOW = timedelta(minutes=1)

MAX_READS_PER_WINDOW = 60

REACTION_ACTION_TYPES = ("liked", "reposted", "followed", "unfollowed")

STATE_ACTION_TYPES = ("state_saved", "observation_note_saved")

REACTION_COOLDOWN_ACTION_TYPES = {
    "like": ("liked",),
    "repost": ("reposted",),
    "follow": ("followed",),
    "unfollow": ("unfollowed",),
}

RATE_LIMIT_LOG_DEDUPE_WINDOW = timedelta(minutes=1)

LOCAL_BOT_ACTION_LABELS = (
    "follow",
    "like",
    "post",
    "reaction",
    "reply",
    "repost",
    "state",
    "unfollow",
)


LOCAL_KEY_PREFIX = 'angmoo_local_'
