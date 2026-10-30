"""Pure validation shared by PostgreSQL configuration and identity storage."""
import re

def require_identifier(value):
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{15,79}", value):
        raise ValueError("postgresql_installation_id_invalid")
    return value
