"""Frozen image context, separate from post text and its existing revision guard."""
import json
from sqlalchemy import select
from app.domains.social.models.posts import Post, PostMedia
from app.domains.social.models.image_intents import ImageIntent
from app.domains.media.generation_contracts import ImagePreparationError
from app.domains.social.service.image_intent_generation import source_revision
from app.runtime.media.binding import current


def snapshots(db, owner_id, post_ids):
    media = current()
    if media is None:
        return []
    result = []
    for post_id in post_ids:
        post = db.get(Post, post_id)
        if post is None or post.deleted_at or post.report_hidden_at or post.visibility != "public":
            continue
        row = db.scalar(select(PostMedia).where(PostMedia.post_id == post_id).order_by(PostMedia.id.desc()))
        if row is None or row.asset_id is None:
            continue
        asset = media.assets.owned(db, owner_id=owner_id, asset_id=row.asset_id, scope_kind="world", scope_id=post.world_id)
        value = {"post_id": post.id, "media_id": row.id, "asset_id": asset.id,
            "asset_revision": asset.revision, "asset_hash": asset.content_hash, "source": "unrecognized",
            "context": None, "recall_hint": None, "selector_delivered": False}
        if analysis := media.interpretation.cached(db, owner_id, asset.id):
            value.update(source="actual_image_analysis", context=analysis.description, recall_hint=analysis.recall_hint,
                interpretation_id=analysis.id)
        elif row.generation_intent_id:
            intent = db.get(ImageIntent, row.generation_intent_id)
            if intent and intent.state == "attached" and intent.source_revision == source_revision(post):
                value.update(source="generation_intent", context=json.loads(intent.request_json).get("positive"))
        result.append(value)
    return result


def allocate(candidates, budget=8192):
    """Whole context or explicit omission; never clip a negation or correction."""
    remaining = budget
    for candidate in candidates:
        for value in candidate.get("images", []):
            context = value.get("context")
            size = len((context or "").encode("utf-8"))
            if context and size <= min(remaining, 2000):
                value["selector_delivered"] = True
                remaining -= size
            elif context:
                value["selector_delivered"] = False
                value["context"] = None
                value["omission_reason"] = "selector_image_budget"
    return candidates


def assert_current(db, owner_id, values):
    media = current()
    if not values:
        return
    if media is None:
        raise ImagePreparationError("image_runtime_unavailable")
    for value in values:
        row = db.get(PostMedia, value["media_id"])
        if row is None or row.asset_id != value["asset_id"] or row.post_id != value["post_id"]:
            raise ImagePreparationError("sns_attachment_changed")
        asset, _ = media.assets.read(db, owner_id=owner_id, asset_id=value["asset_id"], digest=value["asset_hash"])
        if asset.revision != value["asset_revision"] or asset.content_hash != value["asset_hash"]:
            raise ImagePreparationError("sns_image_changed")


async def prepare_selected(db, owner_id, candidate):
    values = [dict(value) for value in candidate.get("images", [])]
    assert_current(db, owner_id, values)
    media = current()
    for value in values:
        if value.get("source") in {"actual_image_analysis", "generation_intent"} and value.get("context"):
            continue
        fresh = next((item for item in snapshots(db, owner_id, [value["post_id"]]) if item["asset_id"] == value["asset_id"]), None)
        if fresh and fresh["context"]:
            value.update({key: fresh[key] for key in ("source", "context", "recall_hint")})
            continue
        if value.get("source") == "generation_intent":
            continue
        asset_id = value["asset_id"]
        db.commit()  # This lane owns the preceding preparation boundary.
        try:
            analysis = await media.interpretation.interpret(db, owner_id, asset_id)
            value.update(source="actual_image_analysis", context=analysis.description, recall_hint=analysis.recall_hint,
                interpretation_id=analysis.id)
        except (ImagePreparationError, RuntimeError):
            value.update(source="unrecognized", context=None, recall_hint=None, reason="analysis_unavailable")
        assert_current(db, owner_id, values)
    return values


def freeze_query(query, images):
    hints = []
    for value in images:
        hint = value.get("recall_hint")
        eligible = not value.get("selector_delivered") or query.get("origin") != "selector"
        if eligible and value.get("source") == "actual_image_analysis" and isinstance(hint, str) and 0 < len(hint.strip()) <= 120:
            if hint.strip() not in hints:
                hints.append(hint.strip())
    kept = []
    for item in hints:
        if len(" ".join([*kept, item])) <= 120:
            kept.append(item)
    hint = " ".join(kept)
    text = query["query"]
    # An image hint cannot create a search where the original query was empty.
    final = f"{text} {hint}".strip() if text and hint else text
    if len(text) > 1000:
        raise ImagePreparationError("image_recall_query_limit")
    omitted = None
    if len(final) > 1000:
        final, hint, omitted = text, "", "final_query_char_budget"
    return {"version": 1, "base_query": dict(query), "final_query": {**query, "query": final},
        "image_hint": hint, "hint_omitted_reason": omitted, "images": images}
