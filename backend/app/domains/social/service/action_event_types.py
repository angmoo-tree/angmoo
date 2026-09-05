"""Event names for successful public actions and validated proposal decisions."""

from app.domains.social.contracts.action_scope import PublicActionProposalResponse


def _event_type(
    action_type: str, proposal_response: PublicActionProposalResponse | None
) -> str:
    if proposal_response is not None:
        return {
            "accept": "joint_accepted",
            "reject": "joint_declined",
            "counter": "joint_proposed",
        }[proposal_response.response.decision]
    return {
        "reply": "reply_created",
        "like": "like_added",
        "repost": "repost_added",
        "follow": "follow_added",
        "unfollow": "follow_removed",
    }[action_type]


def world_feed_event_type(action: str, *, has_proposal: bool) -> str:
    return {
        "comment": "joint_proposed" if has_proposal else "comment_created",
        "like": "like_added",
        "repost": "repost_added",
        "follow": "follow_added",
    }[action]
