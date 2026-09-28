"""Assemble owned execution receipts with canonical Post records on this Session."""
from app.domains.routines.repository.public_action_executions import successful_social_replies
from app.domains.social.models.posts import Post
from app.domains.routine_posts.service.original_post import validate_original_post


def completed_replies(ctx, *, world_id: str, actor_id: str) -> list[dict]:
    result = []
    for execution in successful_social_replies(ctx.db, activity_id=ctx.run_id, world_id=world_id, actor_id=actor_id):
        post_id = (execution.result or {}).get("post_id")
        post = ctx.db.get(Post, post_id, populate_existing=True) if post_id else None
        if post is None or post.world_id != world_id or post.author_world_character_id != actor_id or post.author_character_id != ctx.character.id or post.reply_to_post_id is None:
            continue
        result.append({"post_id": post.id, "lane": execution.scope, "reply_to_post_id": post.reply_to_post_id,
            "title": post.title, "body": post.body, "purpose": "already_published_reply"})
    return result


def check_original(ctx, *, world_id: str, actor_id: str, title: str, body: str):
    validate_original_post(title=title, body=body, completed_replies=completed_replies(ctx, world_id=world_id, actor_id=actor_id))


def reply_prompt_context(replies, today_activity):
    """Reference a supplied actual record instead of repeating its entire text."""
    records = {row.get("source_post_id"): row for row in today_activity.get("records", [])}
    result = []
    for reply in replies:
        row = records.get(reply["post_id"])
        if row is not None and row.get("title") == reply["title"] and row.get("body") == reply["body"]:
            result.append({key: value for key, value in reply.items() if key not in {"title", "body"}} | {
                "content_ref": "today_activity.records:" + str(row["record_key"])})
        else:
            result.append(dict(reply))
    return result
