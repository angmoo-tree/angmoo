"""Competing real writers in disposable SQLite, with no worker/provider startup."""
import asyncio
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
import json
from threading import Barrier, local
from time import perf_counter
from types import SimpleNamespace

from sqlalchemy import event, select
from sqlalchemy.orm import Session

from world_configuration_fixture_support import seed_configuration_fixture
from test_card_metadata_compatibility import duplicate_png
from app.config import settings
from app.contracts.activity_cancellation import CancellationReason
from app.core import work_observation
from app.domains.characters.models import AgentCreationDraft, CharacterCardSource
from app.domains.characters.schemas import AgentCreationDraftCreate
from app.domains.characters.service import drafts, card_import
from app.domains.identity.models import User
from app.domains.identity.schemas import WorldCredentialWrite
from app.domains.identity.schemas_local_entry import LocalPrepareRequest
from app.domains.identity.service.local_entry import LocalEntryService
from app.domains.identity.service.auth import get_session_for_token
from app.domains.routines.models import AgentRun, AgentSlot, AgentActivitySetting
from app.domains.routines.service.slot_leases import cancel_resident_run
from app.domains.world_characters.models import WorldCharacter
from app.runtime.characters.creator import build_creator_workflows
from app.runtime.world_characters import credentials
from app.runtime.world_characters.management import management_service


def test_prepare_key_png_recovery_and_ui_stop_share_bounded_writers(tmp_path, monkeypatch, deny_external_network):
    monkeypatch.setattr(settings, "MEDIA_ROOT", str(tmp_path / "media"))
    engine = seed_configuration_fixture(tmp_path / "writers.sqlite", browser_ready=True)
    owner = SimpleNamespace(id="fixture-owner")
    now = datetime.now(UTC)
    request = LocalPrepareRequest(protocol=2, installation_id="configuration-fixture",
        client_instance_id="synthetic-writer-client", expected_generation=0, preferred_language="en-US")
    workflows = build_creator_workflows()
    with Session(engine) as db:
        first = LocalEntryService(db).issue(request, secret_ready=True)
        other_request = request.model_copy(update={"client_instance_id": "synthetic-other-client"})
        other = LocalEntryService(db).issue(other_request, secret_ready=True)
        draft = asyncio.run(drafts.create_draft(db, owner, AgentCreationDraftCreate(), workflows=workflows))
        draft_id = draft.id
        db.add(AgentRun(id="synthetic-active-run", agent_id="synthetic-slot", user_id=owner.id,
            character_id="config-actor-a", session_key="synthetic-run", status="running"))
        db.add(AgentSlot(agent_id="synthetic-slot", status="running", locked_by_run_id="synthetic-active-run",
            assigned_user_id=owner.id, assigned_character_id="config-actor-a", lease_expires_at=now+timedelta(minutes=5)))
        db.scalar(select(AgentActivitySetting).where(AgentActivitySetting.character_id == "config-actor-a")).auto_enabled = True
        db.get(WorldCharacter, "config-role-a").autonomous_enabled = True
        db.commit()

    tasks = ("prepare", "credential", "png", "recovery", "stop")
    ready = Barrier(len(tasks)+1)
    context = local()
    measures = {name: {"queries": 0, "events": []} for name in tasks}
    @event.listens_for(engine, "before_cursor_execute")
    def count(_con, _cursor, _statement, _parameters, _ctx, _many):
        name = getattr(context, "name", None)
        if name:
            measures[name]["queries"] += 1

    def run(name):
        context.name = name
        ready.wait(15)
        started = perf_counter()
        with Session(engine) as db, work_observation.local_observer(measures[name]["events"].append, lambda: True):
            if name == "prepare":
                # Retried bootstrap on the already-claimed installation must reuse it.
                result = LocalEntryService(db).prepare(other_request, challenge_token="already-claimed",
                    secret_ready=True).user.user_id
            elif name == "credential":
                result = credentials.write(management_service(db), world_id="config-world-a",
                    world_character_id="config-role-a", user=owner, purpose="sns",
                    data=WorldCredentialWrite(provider="google", model="gemini-3.1-flash-lite",
                        thinking_level="medium", api_key="synthetic-writer-key", expected_revision=0,
                        expected_configuration_revision=1)).has_key
            elif name == "png":
                result = card_import.import_card(db, owner, draft_id, revision=1,
                    content=duplicate_png(), workflows=workflows)["draft"].revision
            elif name == "recovery":
                result = cancel_resident_run(db, agent_id="synthetic-slot", run_id="synthetic-active-run",
                    owner_id=owner.id, character_id="config-actor-a", now=now,
                    reason=CancellationReason.HEARTBEAT, resolve_schedule=lambda *_: now+timedelta(seconds=2))
            else:
                result = LocalEntryService(db).stop(request, current_token=first.token).state
        measures[name]["total_ms"] = round((perf_counter()-started)*1000, 3)
        return result

    try:
        with ThreadPoolExecutor(max_workers=len(tasks)) as pool:
            futures = {name: pool.submit(run, name) for name in tasks}
            ready.wait(15)
            results = {name: future.result(20) for name, future in futures.items()}
        assert results == {"prepare": owner.id, "credential": True, "png": 2, "recovery": None, "stop": "stopped"}
        with Session(engine) as db:
            assert get_session_for_token(db, first.token) is None
            assert get_session_for_token(db, other.token) is not None
            assert db.get(WorldCharacter, "config-role-a").autonomous_enabled
            assert db.scalar(select(AgentActivitySetting).where(AgentActivitySetting.character_id == "config-actor-a")).auto_enabled
            assert db.get(AgentRun, "synthetic-active-run").status == "cancelled"
            assert db.get(AgentSlot, "synthetic-slot").locked_by_run_id is None
            assert db.get(AgentSlot, "synthetic-slot").next_tick_at == (now+timedelta(seconds=2)).replace(tzinfo=None)
            assert db.get(AgentCreationDraft, draft_id).revision == 2
            assert db.scalar(select(CharacterCardSource.source_bytes).where(CharacterCardSource.draft_id == draft_id)) == duplicate_png()
            assert len(list(db.scalars(select(User)))) == 2  # seeded owner + outsider, no new owner
        assert len(list(settings.media_root_path.rglob("*.webp"))) == 1
        # Diagnostic payload contains structural facts/times only, never SQL params.
        for values in measures.values():
            events = values.pop("events")
            boundaries = {e["boundary"]: e["monotonic_ns"] for e in events if e.get("event") == "sqlite"}
            for key, start, end in (("wait_ms", "begin_started", "acquired"), ("hold_ms", "acquired", "committed")):
                values[key] = round((boundaries[end]-boundaries[start])/1e6, 3) if start in boundaries and end in boundaries else None
            values["retry_waits"] = sum(e.get("boundary") == "retry_wait_started" for e in events)
        print("mixed_writer_measurements=" + json.dumps(measures, sort_keys=True))
    finally:
        engine.dispose()
