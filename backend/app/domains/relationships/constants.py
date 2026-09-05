"""Relationship response candidate lifecycle values."""

RELATIONSHIP_POINT_KINDS = {"mention_received", "reply_received"}
RELATIONSHIP_POINT_PENDING = "pending"
RELATIONSHIP_POINT_SELECTED = "selected"
RELATIONSHIP_POINT_CONSUMED = "consumed"
RELATIONSHIP_POINT_EXPIRED = "expired"
RELATIONSHIP_POINT_FAILED = "failed"
RELATIONSHIP_POINT_ACTIVE_STATUSES = {
    RELATIONSHIP_POINT_PENDING,
    RELATIONSHIP_POINT_SELECTED,
}


SOCIAL_EVENT_SCHEMA_VERSION = "social-event-v1"


GRAPH_PAYLOAD_VERSION = "relationship-v1"


SOURCE_EXCLUSION_PAYLOAD_VERSION = "source-exclusion-v1"


_RELATION_EVENT_TYPES = {
    "comment_created",
    "reply_created",
    "mention_created",
    "like_added",
    "like_removed",
    "follow_added",
    "follow_removed",
    "repost_added",
    "repost_removed",
    "joint_accepted",
    "joint_completed",
    "joint_declined",
    "joint_cancelled",
}


SOCIAL_EVENT_TYPES = (
    "post_published",
    "comment_created",
    "reply_created",
    "mention_created",
    "like_added",
    "like_removed",
    "follow_added",
    "follow_removed",
    "repost_added",
    "repost_removed",
    "joint_proposed",
    "joint_accepted",
    "joint_started",
    "joint_completed",
    "joint_declined",
    "joint_cancelled",
)
