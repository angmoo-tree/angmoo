"""SQLite canonical write invariants for accepted World erasure.

Application admission checks provide friendly errors. These triggers close the
race between an old reader/provider and a committing deletion request. They
never disable FK/source validation or grant authority to the deletion worker.
"""
from sqlalchemy.dialects.sqlite import dialect
from app.runtime.world_deletion.inventory import ErasureInventory

# Operational receipts may settle an admitted lease; all new content INSERTs
# and scope moves remain fenced. Purge deletes them after drain, not before.
SETTLEMENT_TABLES = frozenset({"agent_runs", "agent_public_action_executions", "chat_response_requests", "image_interpretations",
    "post_image_generation_jobs", "memory_batch_runs", "memory_situation_runs", "activity_graph_runs",
    "activity_beats", "activity_event_consumptions", "joint_activity_representation_claims",
    "activity_preparation_jobs", "social_recommendation_preparations", "world_character_setup_attempts"})


def install_fences(connection, *, metadata=None):
    if connection.dialect.name != "sqlite":
        raise ValueError("world_deletion_requires_canonical_sqlite")
    inventory = ErasureInventory(metadata) if metadata is not None else ErasureInventory.for_connection(connection)
    for name in sorted(inventory.rules):
        table = inventory.tables[name]
        # NEW pseudo-table is represented by a correlated alias for compiler-safe identifiers.
        expression = inventory.predicate(name, "__WORLD__", table=table.alias("NEW"))
        sql = str(expression.compile(dialect=dialect(), compile_kwargs={"literal_binds": True}))
        sql = sql.replace("'__WORLD__'", "d.world_id")
        old = str(inventory.predicate(name, "__WORLD__", table=table.alias("OLD")).compile(
            dialect=dialect(), compile_kwargs={"literal_binds": True})).replace("'__WORLD__'", "d.world_id")
        nullable_links = {element.parent.name for fk in table.foreign_key_constraints
            if fk.referred_table.name in inventory.rules for element in fk.elements if element.parent.nullable}
        protected = [column.name for column in table.columns if column.name not in nullable_links and column.name != "updated_at"]
        changed = " OR ".join([f'NEW."{column}" IS NOT OLD."{column}"' for column in protected] +
            [f'(NEW."{column}" IS NOT NULL AND NEW."{column}" IS NOT OLD."{column}")' for column in sorted(nullable_links)]) or "0"
        # Operational settlement is permitted only for a previously admitted
        # active work item; it cannot acquire a new lease after the intent.
        if name in SETTLEMENT_TABLES:
            field = "state" if "state" in table.c else "status" if "status" in table.c else "representation_status" if "representation_status" in table.c else None
            if field:
                if name == "chat_response_requests":
                    active = "('lease_acquired','preflighted','routing','resolving','current_context_ready','canonical_planning','graph_planning','both_coordinating','clarification_prepared','optional_retrieving','evidence_frozen','response_generating','response_streaming','committing')"
                else:
                    active = "('pending','running','processing','submitted')" if name == "agent_public_action_executions" else "('running','processing','submitted','claimed')"
                identity_columns = sorted({column.name for column in table.primary_key} |
                    {element.parent.name for fk in table.foreign_key_constraints for element in fk.elements} |
                    ({inventory.rules[name]["world_column"]} if "world_column" in inventory.rules[name] else set()) |
                    ({"input_snapshot"} if name == "agent_runs" else set()))
                scope_changed = " OR ".join(f'NEW."{column}" IS NOT OLD."{column}"' for column in identity_columns)
                changed = f'(NEW."{field}" IN {active} AND OLD."{field}" NOT IN {active}) OR ({scope_changed})'
        # Scope-changing updates must not move data out of the erased World.
        for event in ("INSERT", "UPDATE"):
            trigger = f"world_erasure_{name}_{event.lower()}"
            condition = sql if event == "INSERT" else f"({sql} OR {old}) AND ({changed})"
            connection.exec_driver_sql(f'CREATE TRIGGER IF NOT EXISTS "{trigger}" BEFORE {event} ON "{name}" '
                f"WHEN EXISTS (SELECT 1 FROM world_deletion_requests d WHERE {condition}) "
                "BEGIN SELECT RAISE(ABORT, 'world_deleting'); END")
    connection.exec_driver_sql('CREATE TRIGGER IF NOT EXISTS world_erasure_world_insert BEFORE INSERT ON worlds '
        "WHEN EXISTS(SELECT 1 FROM world_deletion_requests WHERE world_id=NEW.id) "
        "BEGIN SELECT RAISE(ABORT, 'world_deleting'); END")
    for event in ("INSERT", "UPDATE"):
        changed = "1" if event == "INSERT" else "(OLD.status != 'running' OR NEW.locked_by_run_id IS NOT OLD.locked_by_run_id OR NEW.admission_metadata IS NOT OLD.admission_metadata)"
        connection.exec_driver_sql(f'CREATE TRIGGER IF NOT EXISTS world_erasure_slot_{event.lower()} BEFORE {event} ON agent_slots '
            "WHEN NEW.status='running' AND " + changed + " AND EXISTS(SELECT 1 FROM world_deletion_requests d "
            "WHERE json_extract(NEW.admission_metadata,'$._world_credential.world_id')=d.world_id) "
            "BEGIN SELECT RAISE(ABORT, 'world_deleting'); END")
    connection.exec_driver_sql('CREATE TRIGGER IF NOT EXISTS world_erasure_world_update BEFORE UPDATE ON worlds '
        "WHEN EXISTS(SELECT 1 FROM world_deletion_requests WHERE world_id=NEW.id) AND "
        "(NEW.name != '' OR NEW.tagline != '' OR NEW.setting_description != '' OR NEW.daily_life_description != '' "
        "OR NEW.additional_generation_guidance != '' OR NEW.banner_media_id IS NOT NULL OR NEW.icon_media_id IS NOT NULL "
        "OR NEW.banner_alt_text != '' OR NEW.genre_tags != '[]' OR NEW.tone_tags != '[]' "
        "OR NEW.visibility != 'private' OR NEW.join_policy != 'private' OR NEW.status != 'archived' OR NEW.readiness_status != 'not_ready') "
        "BEGIN SELECT RAISE(ABORT, 'world_deleting'); END")
