"""Owned images, purpose credentials and durable generation/interpretation."""
import json
from pathlib import Path
from alembic import op
import sqlalchemy as sa

revision = "20260930_0104"
down_revision = "20260929_0103"
branch_labels = None
depends_on = None


def upgrade():
    connection = op.get_bind()
    if connection.dialect.name == "sqlite":
        from app.runtime.migrations.sqlite_versions.images_v26 import upgrade as sqlite_upgrade
        sqlite_upgrade(connection)
        return
    root = Path(__file__).resolve().parents[2] / "app/runtime/migrations/sqlite_versions"
    ddl = json.loads((root / "image_v26_ddl.json").read_text(encoding="utf-8"))
    old = {"agent_image_generation_settings", "post_media", "post_image_generation_jobs"}
    for name, spec in ddl.items():
        if name not in old:
            op.execute(spec["postgres_create"])
            for index in spec["postgres_indexes"]:
                op.execute(index)
    for name, type_, default in (
        ("generation_provider", sa.String(20), None), ("generation_model", sa.String(120), None),
        ("generation_profiles_json", sa.Text(), "{}"), ("generation_revision", sa.Integer(), "1"),
        ("generation_auto_enabled", sa.Boolean(), sa.false()), ("generation_daily_limit", sa.Integer(), None),
        ("appearance_prompt", sa.Text(), ""), ("style_prompt", sa.Text(), ""), ("negative_prompt", sa.Text(), ""),
        ("reference_asset_id", sa.String(64), None), ("card_asset_id", sa.String(64), None),
    ):
        op.add_column("agent_image_generation_settings", sa.Column(name, type_, nullable=default is None, server_default=default))
    for name in ("reference_asset_id", "card_asset_id"):
        op.create_foreign_key(f"fk_image_setting_{name}", "agent_image_generation_settings", "media_assets", [name], ["id"])
    for name in ("model", "prompt_hash"):
        op.alter_column("post_media", name, nullable=True)
    for name, type_, default in (("asset_id", sa.String(64), None), ("source_kind", sa.String(20), "legacy"), ("generation_intent_id", sa.String(64), None)):
        op.add_column("post_media", sa.Column(name, type_, nullable=default is None, server_default=default))
    op.create_foreign_key("fk_post_media_asset", "post_media", "media_assets", ["asset_id"], ["id"])
    op.create_foreign_key("fk_post_media_intent", "post_media", "post_image_intents", ["generation_intent_id"], ["id"])
    op.create_unique_constraint("uq_post_media_asset", "post_media", ["asset_id"])
    op.drop_index("ix_post_image_generation_jobs_post_id", table_name="post_image_generation_jobs")
    op.create_index("ix_post_image_generation_jobs_post_id", "post_image_generation_jobs", ["post_id"], unique=False)
    for name, type_ in (("intent_id", sa.String(64)), ("lease_token", sa.String(64)), ("lease_until", sa.DateTime(timezone=True)), ("provider_receipt", sa.String(160)), ("result_asset_id", sa.String(64))):
        op.add_column("post_image_generation_jobs", sa.Column(name, type_, nullable=True))
    op.create_unique_constraint("uq_post_image_job_intent", "post_image_generation_jobs", ["intent_id"])
    op.create_foreign_key("fk_post_image_job_intent", "post_image_generation_jobs", "post_image_intents", ["intent_id"], ["id"])
    op.create_foreign_key("fk_post_image_job_result", "post_image_generation_jobs", "media_assets", ["result_asset_id"], ["id"])


def downgrade():
    raise RuntimeError("image_records_forward_only")
