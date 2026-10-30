"""Reviewed deletion fences and vector mutation producers for PostgreSQL."""
import hashlib
from sqlalchemy.dialects.postgresql import dialect
from app.runtime.persistence.world_erasure_inventory import ErasureInventory, SETTLEMENT_TABLES
from app.runtime.persistence.vector_mutations import statements as vector_statements


def trigger(connection,name,table,event,body,*,timing="BEFORE"):
    key="angmoo_"+hashlib.sha256(name.encode()).hexdigest()[:24]
    result="OLD" if event=="DELETE" else "NEW"
    connection.exec_driver_sql(f'CREATE OR REPLACE FUNCTION "{key}"() RETURNS trigger LANGUAGE plpgsql AS $body$ BEGIN {body} RETURN {result}; END $body$')
    # Reinstallation changes only a known trigger definition, never its data.
    connection.exec_driver_sql(f'DROP TRIGGER IF EXISTS "{key}" ON "{table}"')
    connection.exec_driver_sql(f'CREATE TRIGGER "{key}" {timing} {event} ON "{table}" FOR EACH ROW EXECUTE FUNCTION "{key}"()')


def predicate(inventory,name,alias,world):
    expression=inventory.predicate(name,"__WORLD__",table=inventory.tables[name].alias(alias))
    return str(expression.compile(dialect=dialect(),compile_kwargs={"literal_binds":True})).replace("'__WORLD__'",world).replace('"NEW".','NEW.').replace('"OLD".','OLD.')


def deletion_fences(connection,metadata):
    inventory=ErasureInventory(metadata)
    # Accepted deletion changes the root row version. Writers take a shared
    # row lock before the tombstone check: concurrent ordinary writes coexist;
    # a stale SERIALIZABLE writer must abort after deletion wins this lock.
    trigger(connection,"world_erasure_accept","world_deletion_requests","INSERT",
        "UPDATE worlds SET updated_at=updated_at WHERE id=NEW.world_id;")
    for name in sorted(inventory.rules):
        table=inventory.tables[name]
        links={e.parent.name for fk in table.foreign_key_constraints if fk.referred_table.name in inventory.rules for e in fk.elements if e.parent.nullable}
        protected=[c.name for c in table.columns if c.name not in links and c.name!="updated_at"]
        changed=" OR ".join([f'NEW."{c}" IS DISTINCT FROM OLD."{c}"' for c in protected]+
            [f'(NEW."{c}" IS NOT NULL AND NEW."{c}" IS DISTINCT FROM OLD."{c}")' for c in sorted(links)]) or "false"
        if name in SETTLEMENT_TABLES:
            field=next((c for c in ("state","status","representation_status") if c in table.c),None)
            if field:
                states=("'lease_acquired','preflighted','routing','resolving','current_context_ready','canonical_planning','graph_planning','both_coordinating','clarification_prepared','optional_retrieving','evidence_frozen','response_generating','response_streaming','committing'" if name=="chat_response_requests" else
                    "'pending','running','processing','submitted'" if name=="agent_public_action_executions" else "'running','processing','submitted','claimed'")
                identities={c.name for c in table.primary_key}|{e.parent.name for fk in table.foreign_key_constraints for e in fk.elements}
                if "world_column" in inventory.rules[name]:identities.add(inventory.rules[name]["world_column"])
                if name=="agent_runs":identities.add("input_snapshot")
                changed=f'(NEW."{field}" IN ({states}) AND OLD."{field}" NOT IN ({states})) OR ('+" OR ".join(f'NEW."{c}" IS DISTINCT FROM OLD."{c}"' for c in sorted(identities))+")"
        for event in ("INSERT","UPDATE"):
            scope=predicate(inventory,name,"NEW","w.id")
            condition=predicate(inventory,name,"NEW","d.world_id")
            if event=="UPDATE":
                scope=f'({scope}) OR ({predicate(inventory,name,"OLD","w.id")})'
                condition=f'({condition} OR {predicate(inventory,name,"OLD","d.world_id")}) AND ({changed})'
            body=f'PERFORM w.id FROM worlds w WHERE {scope} ORDER BY w.id FOR SHARE; '
            body+=f"IF EXISTS(SELECT 1 FROM world_deletion_requests d WHERE {condition}) THEN RAISE EXCEPTION 'world_deleting' USING ERRCODE='23514'; END IF;"
            trigger(connection,f'world_erasure_{name}_{event}',name,event,body)
    trigger(connection,"world_erasure_world_insert","worlds","INSERT",
        "IF EXISTS(SELECT 1 FROM world_deletion_requests WHERE world_id=NEW.id) THEN RAISE EXCEPTION 'world_deleting' USING ERRCODE='23514'; END IF;")
    for event in ("INSERT","UPDATE"):
        changed="true" if event=="INSERT" else "(OLD.status != 'running' OR NEW.locked_by_run_id IS DISTINCT FROM OLD.locked_by_run_id OR NEW.admission_metadata IS DISTINCT FROM OLD.admission_metadata)"
        trigger(connection,f'world_erasure_slot_{event}',"agent_slots",event,
            "PERFORM id FROM worlds WHERE id=json_extract(NEW.admission_metadata,'$._world_credential.world_id') FOR SHARE; "
            f"IF NEW.status='running' AND {changed} AND EXISTS(SELECT 1 FROM world_deletion_requests d WHERE json_extract(NEW.admission_metadata,'$._world_credential.world_id')=d.world_id) THEN RAISE EXCEPTION 'world_deleting' USING ERRCODE='23514'; END IF;")
    trigger(connection,"world_erasure_world_update","worlds","UPDATE",
        "IF EXISTS(SELECT 1 FROM world_deletion_requests WHERE world_id=NEW.id) AND "
        "(NEW.name != '' OR NEW.tagline != '' OR NEW.setting_description != '' OR NEW.daily_life_description != '' "
        "OR NEW.additional_generation_guidance != '' OR NEW.banner_media_id IS NOT NULL OR NEW.icon_media_id IS NOT NULL "
        "OR NEW.banner_alt_text != '' OR NEW.genre_tags != '[]' OR NEW.tone_tags != '[]' "
        "OR NEW.visibility != 'private' OR NEW.join_policy != 'private' OR NEW.status != 'archived' OR NEW.readiness_status != 'not_ready') "
        "THEN RAISE EXCEPTION 'world_deleting' USING ERRCODE='23514'; END IF;")


def vector_producers(connection):
    # Shared reviewed catalog/body prevents the PostgreSQL adapter omitting a
    # bulk-write or FK-cascade producer that the existing implementation owns.
    import re
    from app.runtime.persistence.postgresql_epochs import write_key
    for sql in vector_statements(epoch_key=write_key):
        match=re.fullmatch(r'CREATE TRIGGER IF NOT EXISTS "([^"]+)" (AFTER|BEFORE) (INSERT|UPDATE|DELETE) ON "([^"]+)"(.*?) BEGIN (.*) END',sql)
        if not match:raise RuntimeError("vector_trigger_contract_drift")
        name,timing,event,table,condition,body=match.groups()
        body=body.replace("revision=revision+1","revision=memory_vector_validation_revisions.revision+1")
        if condition:
            condition=condition.removeprefix(" WHEN ").replace(" IS NOT "," IS DISTINCT FROM ")
            body=f"IF {condition} THEN {body} END IF;"
        trigger(connection,name,table,event,body,timing=timing)


def install(connection,metadata):
    deletion_fences(connection,metadata)
    vector_producers(connection)
    for table in ("memory_experience_snapshots", "memory_experience_dependencies"):
        trigger(connection,table+"_immutable",table,"UPDATE",
            "IF to_jsonb(NEW) IS DISTINCT FROM to_jsonb(OLD) THEN RAISE EXCEPTION 'memory_snapshot_immutable' USING ERRCODE='23514'; END IF;")
