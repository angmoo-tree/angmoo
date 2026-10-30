"""Installation-owned PostgreSQL identity, shared by platforms and migration."""
import re
from sqlalchemy import text

IDENTITY_TABLE = "angmoo_postgresql_installation"


def require_identifier(value):
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{15,79}", value):
        raise ValueError("postgresql_installation_id_invalid")
    return value


def create(connection, installation_id):
    require_identifier(installation_id)
    connection.exec_driver_sql("""CREATE TABLE IF NOT EXISTS angmoo_postgresql_installation(
        singleton boolean PRIMARY KEY CHECK(singleton), installation_id text NOT NULL,
        product text NOT NULL CHECK(product='angmoo'), contract integer NOT NULL CHECK(contract=1))""")
    connection.execute(text("INSERT INTO angmoo_postgresql_installation VALUES(true,:id,'angmoo',1) ON CONFLICT DO NOTHING"), {"id": installation_id})
    verify(connection, installation_id)


def verify(connection, installation_id):
    require_identifier(installation_id)
    actual = connection.execute(text("SELECT installation_id,product,contract FROM angmoo_postgresql_installation WHERE singleton=true")).one()
    if tuple(actual) != (installation_id, "angmoo", 1):
        raise ValueError("postgresql_installation_identity_mismatch")
