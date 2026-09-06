"""Same-function compatibility for immutable Alembic revision 0088.

The current ORM and schema builders belong to social.models.subjective_context.
Historical migration source must retain its original import; product code uses
the actual owner directly. No ORM class or second schema implementation is
exported from this historical path.
"""

from app.domains.social.models.subjective_context import (
    create_subjective_context_schema,
    drop_subjective_context_schema,
)

__all__ = ["create_subjective_context_schema", "drop_subjective_context_schema"]
