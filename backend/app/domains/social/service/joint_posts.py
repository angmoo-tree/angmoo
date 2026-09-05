"""Post links assigned by the caller's existing joint-activity transaction."""

from app.domains.social.models.posts import Post


def set_joint_activity_id(post: Post, *, joint_activity_id: str) -> None:
    post.joint_activity_id = joint_activity_id


def set_opening_post_id(post: Post, *, opening_post_id: str) -> None:
    post.opening_post_id = opening_post_id
