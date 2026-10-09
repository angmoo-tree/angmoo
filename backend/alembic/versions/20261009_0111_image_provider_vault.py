"""Image provider vault and Comfy server-key retirement, forward only."""
from alembic import op
from app.domains.identity.service.migration_secrets import MigrationSecretInterpreter
from app.runtime.migrations.sqlite_versions.image_provider_vault_v34 import upgrade as migrate

revision = "20261009_0111"
down_revision = "20261009_0110"
branch_labels = None
depends_on = None


def upgrade():
    migrate(op.get_bind(), interpreter=MigrationSecretInterpreter())


def downgrade():
    raise RuntimeError("image_provider_vault_forward_only")
