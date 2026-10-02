"""Cross-owner deletion composition; media files use the existing quarantine."""
from sqlalchemy import delete, select, update, or_
from app.domains.media.models import MediaAsset, ImageInterpretation, InterpretationAttempt, InterpretationSetting
from app.domains.identity.models_media import MediaCredential
from app.domains.chat.models import MessageAttachment, MessageMessage, MessageThread
from app.domains.social.models.posts import Post, PostMedia, PostImageGenerationJob
from app.domains.social.models.image_intents import ImageIntent, ImageGenerationAttempt
from app.domains.characters.models import AgentImageGenerationSetting


def _scope(db, character_ids, owner_id):
    jobs = select(PostImageGenerationJob.id).where(PostImageGenerationJob.user_id == owner_id) if owner_id else select(PostImageGenerationJob.id).where(PostImageGenerationJob.character_id.in_(character_ids))
    if owner_id:
        assets = select(MediaAsset.id).where(MediaAsset.owner_id == owner_id)
    else:
        threads = select(MessageThread.id).where(MessageThread.character_id.in_(character_ids))
        generated = select(PostImageGenerationJob.result_asset_id).where(PostImageGenerationJob.id.in_(jobs))
        assets = select(MediaAsset.id).where(or_(
            (MediaAsset.scope_kind == "character") & MediaAsset.scope_id.in_(character_ids),
            (MediaAsset.scope_kind == "thread") & MediaAsset.scope_id.in_(threads), MediaAsset.id.in_(generated)))
    return jobs, assets


def private_paths(db, root, *, character_ids=(), owner_id=None):
    jobs, assets = _scope(db, character_ids, owner_id)
    paths = []
    for asset in db.scalars(select(MediaAsset).where(MediaAsset.id.in_(assets))):
        path = (root / asset.storage_key).resolve()
        if root.resolve() not in path.parents:
            raise ValueError("asset_path_invalid")
        paths.append(path)
    for identity in db.scalars(select(ImageInterpretation.id).where(ImageInterpretation.asset_id.in_(assets))):
        paths.extend(root / "received-interpretations" / f"{identity}{suffix}" for suffix in (".json", ".tmp"))
    for identity in db.scalars(jobs):
        paths.extend(root / "received-results" / f"{identity}{suffix}" for suffix in (".json", ".pixels", ".json.tmp", ".pixels.tmp"))
    return paths


def scrub(db, *, character_ids=(), owner_id=None):
    jobs_query, asset_query = _scope(db, character_ids, owner_id)
    # Materialize owned identities before any dependent row is removed.
    jobs, assets = list(db.scalars(jobs_query)), list(db.scalars(asset_query))
    analyses = list(db.scalars(select(ImageInterpretation.id).where(ImageInterpretation.asset_id.in_(assets))))
    intents = list(db.scalars(select(PostImageGenerationJob.intent_id).where(PostImageGenerationJob.id.in_(jobs))))
    intents.extend(db.scalars(select(ImageIntent.id).where(ImageIntent.post_id.in_(
        select(Post.id).where(Post.author_character_id.in_(character_ids))))))
    if owner_id:
        intents.extend(db.scalars(select(ImageIntent.id).where(ImageIntent.credential_id.in_(
            select(MediaCredential.id).where(MediaCredential.owner_id == owner_id)))))
    else:
        intents.extend(db.scalars(select(ImageIntent.id).where(ImageIntent.credential_id.in_(
            select(MediaCredential.id).where(MediaCredential.character_scope.in_(character_ids))))))
    db.execute(delete(MessageAttachment).where(or_(MessageAttachment.asset_id.in_(assets), MessageAttachment.interpretation_id.in_(analyses))))
    db.execute(delete(PostMedia).where(or_(PostMedia.asset_id.in_(assets), PostMedia.generation_intent_id.in_(intents))))
    db.execute(delete(InterpretationAttempt).where(InterpretationAttempt.interpretation_id.in_(analyses)))
    db.execute(delete(ImageInterpretation).where(ImageInterpretation.id.in_(analyses)))
    db.execute(delete(ImageGenerationAttempt).where(ImageGenerationAttempt.job_id.in_(jobs)))
    db.execute(delete(PostImageGenerationJob).where(PostImageGenerationJob.id.in_(jobs)))
    db.execute(delete(ImageIntent).where(ImageIntent.id.in_(intents)))
    db.execute(update(AgentImageGenerationSetting).where(or_(
        AgentImageGenerationSetting.reference_asset_id.in_(assets), AgentImageGenerationSetting.card_asset_id.in_(assets)))
        .values(reference_asset_id=None, card_asset_id=None, generation_auto_enabled=False, generation_profiles_json="{}"))
    credentials = MediaCredential.owner_id == owner_id if owner_id else MediaCredential.character_scope.in_(character_ids)
    db.execute(delete(MediaCredential).where(credentials))
    db.execute(delete(MediaAsset).where(MediaAsset.id.in_(assets)))
    if owner_id:
        db.execute(delete(InterpretationSetting).where(InterpretationSetting.owner_id == owner_id))
