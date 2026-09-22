"""Inbox candidate grouping and explicit, selected-notification settlement."""
from datetime import UTC, datetime

from app.domains.social.models.posts import Notification
from app.domains.social.service.activity_inbox import pending_conversations
from app.runtime.autonomous_activity.contracts import Candidate, identity_key
from app.runtime.autonomous_activity.social_lane import SocialLane
from app.runtime.relationships.experience_metrics import post_revision


class InboxLane(SocialLane):
    async def load(self, state):
        candidates, data = [], {}
        for group in pending_conversations(self.ctx.db, actor=self.actor,
                allowed_actions=self.ctx.activity_policy.allowed_actions):
            posts, notifications = group["posts"], group["notifications"]
            post = posts[-1]
            key = identity_key(self.actor.id, group["counterpart_id"], group["branch_id"], *(str(n.id) for n in notifications))
            from app.runtime.social.langgraph_actions import proposal_for_notification
            proposal = proposal_for_notification(self.ctx.db, recipient_character_id=self.ctx.character.id, source_post_id=post.id)
            proposal_input = None if proposal is None else {"proposal_id": proposal.id, "activity_seed": proposal.activity_seed, "place_key": proposal.place_key, "target_daypart": proposal.target_daypart, "date_policy": proposal.date_policy, "target_date": str(proposal.target_date) if proposal.target_date else None}
            allowed = ["comment" if a == "reply" else a for a in group["affordance"]["available_actions"]]
            revisions = {p.id: post_revision(p) for p in posts}
            if group["parent"] is not None:
                revisions[group["parent"].id] = post_revision(group["parent"])
            candidates.append(Candidate(target_id=key, counterpart_id=group["counterpart_id"],
                source_ids=[p.id for p in posts], source_revisions=revisions,
                text="\n".join(f"{p.author_name}: {p.body}" for p in posts),
                parent_text=group["parent"].body if group["parent"] else "",
                allowed_actions=allowed, activity_proposal=proposal_input, relationship=self.relationship(group["counterpart_id"]),
                waiting_since=notifications[0].created_at.isoformat()).model_dump())
            data[key] = {"post_id": post.id, "notification_id": notifications[-1].id,
                "notification_ids": [n.id for n in notifications]}
        return {"candidates": candidates, "lane_data": data}

    async def finalize(self, state):
        from app.runtime.social.langgraph_actions import mark_notification_handled_without_public_action
        for result in state.get("executions", []):
            # Failure/retry and omitted decisions leave notifications pending.
            if result["status"] not in {"no_action", "succeeded", "reused"}:
                continue
            for identifier in state["lane_data"][result["target_id"]]["notification_ids"]:
                row = self.ctx.db.get(Notification, identifier, populate_existing=True)
                if row is None or row.world_id != self.actor.world_id or row.recipient_world_character_id != self.actor.id or row.handled_at:
                    continue
                mark_notification_handled_without_public_action(self.ctx.db,
                    actor_character_id=self.ctx.character.id, notification_id=identifier,
                    handling_outcome="LLM_DECIDED_NO_ACTION",
                    occurred_at=datetime.now(UTC))
        self.ctx.db.commit()
        return await super().finalize(state)
