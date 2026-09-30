"""Remove v26 additions when constructing an immutable historical schema."""
from sqlalchemy import UniqueConstraint

IMAGE_TABLES = (
    "media_credentials", "media_assets", "image_interpretation_settings",
    "image_interpretations", "image_interpretation_attempts", "message_attachments",
    "post_image_intents", "post_image_generation_attempts", "image_generation_policy",
)
IMAGE_COLUMNS = {
    "agent_image_generation_settings": (
        "generation_provider", "generation_model", "generation_profiles_json", "generation_revision",
        "generation_auto_enabled", "generation_daily_limit", "appearance_prompt", "style_prompt",
        "negative_prompt", "reference_asset_id", "card_asset_id",
    ),
    "post_media": ("asset_id", "source_kind", "generation_intent_id"),
    "post_image_generation_jobs": ("intent_id", "lease_token", "lease_until", "provider_receipt", "result_asset_id"),
}


def remove_image_schema(metadata):
    for name, columns in IMAGE_COLUMNS.items():
        table = metadata.tables.get(name)
        if table is None:
            continue
        for constraint in tuple(table.constraints):
            if any(column.name in columns for column in constraint.columns):
                table.constraints.remove(constraint)
        for column in columns:
            if column in table.c:
                table._columns.remove(table.c[column])
    if "post_media" in metadata.tables:
        metadata.tables["post_media"].c.model.nullable = False
        metadata.tables["post_media"].c.prompt_hash.nullable = False
    if "post_image_generation_jobs" in metadata.tables:
        # Released schema expresses post uniqueness as its unique index.
        for index in metadata.tables["post_image_generation_jobs"].indexes:
            if index.name == "ix_post_image_generation_jobs_post_id":
                index.unique = True
    for name in reversed(IMAGE_TABLES):
        if name in metadata.tables:
            metadata.remove(metadata.tables[name])
