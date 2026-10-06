"""Independent World keys, subject profiles, image ledgers and restrictions."""
from alembic import op

revision = "20261006_0107"
down_revision = "20261005_0106"
branch_labels = None
depends_on = None


def upgrade():
    from app.runtime.migrations.sqlite_versions import world_activity_v30
    from app.domains.identity.service.migration_secrets import MigrationSecretInterpreter
    connection = op.get_bind()
    if connection.dialect.name != "sqlite":
        from app.domains.identity.models_world_credentials import WorldCredential, WorldCredentialRevision
        from app.domains.media.models_world_policy import WorldImagePolicy, WorldImageAttempt
        from app.domains.memory.models.activity_configuration import MemorySubjectProfile, MemoryIndexPreparation, MemoryEpisodeRestriction
        for model in (WorldCredential, WorldCredentialRevision, WorldImagePolicy, WorldImageAttempt, MemorySubjectProfile, MemoryIndexPreparation, MemoryEpisodeRestriction):
            model.__table__.create(connection)
    with world_activity_v30.secret_interpreter(MigrationSecretInterpreter()):
        before = world_activity_v30.capture_delta(connection)
        world_activity_v30.upgrade(connection)
        world_activity_v30.verify_delta(connection, before)


def downgrade():
    raise RuntimeError("world_activity_credentials_forward_only")
