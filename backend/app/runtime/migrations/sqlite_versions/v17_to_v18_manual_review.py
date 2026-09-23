"""Frozen additive manual follow-up schema; no existing data is modified."""
from app.runtime.migrations.sqlite_versions.contracts import SqliteMigrationDeltaError
MUTABLE_IDENTITY_TABLES = frozenset({"relationship_review_requests"})
DDL = ['\nCREATE TABLE relationship_review_requests (\n\tmemory_request_id VARCHAR(64) NOT NULL, \n\tscope_setting_id VARCHAR(64) NOT NULL, \n\tcanonical_request_id VARCHAR(64), \n\tstate VARCHAR(32) NOT NULL, \n\tsnapshot JSON, \n\twork_ids JSON NOT NULL, \n\tlast_code VARCHAR(100), \n\taccepted_at DATETIME NOT NULL, \n\tcompleted_at DATETIME, \n\tPRIMARY KEY (memory_request_id), \n\tFOREIGN KEY(canonical_request_id) REFERENCES relationship_review_requests (memory_request_id), \n\tFOREIGN KEY(scope_setting_id) REFERENCES memory_scope_settings (id) ON DELETE CASCADE, \n\tFOREIGN KEY(memory_request_id) REFERENCES memory_consolidation_requests (id) ON DELETE CASCADE\n)\n\n', 'CREATE INDEX ix_relationship_review_requests_scope_setting_id ON relationship_review_requests (scope_setting_id)', 'CREATE INDEX ix_relationship_review_requests_state ON relationship_review_requests (state)']

def capture_delta(connection):
    return frozenset(r[0] for r in connection.exec_driver_sql("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"))

def upgrade(connection):
    for statement in DDL:
        connection.exec_driver_sql(statement)

def verify_delta(connection, before):
    if capture_delta(connection) != before | MUTABLE_IDENTITY_TABLES or connection.exec_driver_sql("SELECT count(*) FROM relationship_review_requests").scalar_one():
        raise SqliteMigrationDeltaError("sqlite_migration_expected_delta_mismatch")
