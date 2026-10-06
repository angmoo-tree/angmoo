"""Loopback browser fixture using product routes and a task-owned migrated SQLite.

Run with scripts/testing/offline-python first in PYTHONPATH. Authentication metadata
is fixture-owned; authorization, CAS, import/registration, and admission use the
actual product services. Only the worker after a real slot admission is controlled.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path
import sys
from uuid import uuid4

import uvicorn
from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select
from sqlalchemy.orm import Session


def build_fixture(state_dir: Path, frontend_origins: list[str], basis_kind: str = "legacy_transition") -> FastAPI:
    repo = Path(__file__).resolve().parents[2]
    allowed = (repo.parent / "docs" / "temp" / "world-ui-2026-10-05").resolve()
    state_dir = state_dir.resolve()
    if not state_dir.is_relative_to(allowed) or state_dir == allowed:
        raise ValueError("fixture_state_directory_outside_task")
    if "sitecustomize" not in sys.modules or "offline-python" not in str(getattr(sys.modules["sitecustomize"], "__file__", "")):
        raise RuntimeError("fixture_offline_guard_required")
    if basis_kind not in {"creation", "legacy_transition"}:
        raise ValueError("unsupported_character_fixture_basis")
    state_dir.mkdir(parents=True, exist_ok=True)
    sqlite = state_dir / "configuration.sqlite3"
    if sqlite.exists():
        raise ValueError("fixture_database_already_exists_use_a_new_task_directory")

    from app.config import settings
    settings.BROWSER_SESSION_ALLOWED_ORIGINS = ",".join(frontend_origins + ["http://127.0.0.1:3356"])
    settings.MEDIA_ROOT = str(state_dir / "media")
    settings.LADYBUG_DATABASE_ROOT = str(state_dir / "graph")
    # Exercise the supported canonical fallback without opening any user's
    # projection directory. Projection-backed reads have separate domain tests.
    settings.GRAPH_PROJECTION_ENABLED = False
    settings.DAILY_PREPARATION_ENABLED = True
    settings.AGENT_ACTIVITY_ENGINE = "langgraph"
    settings.OPENCLAW_AGENT_IDS = "fixture-slot-1,fixture-slot-2"
    settings.APP_ENV = "development"
    from world_configuration_fixture_support import seed_configuration_fixture
    from app.runtime.migrations.sqlite_versions import world_configuration_v28 as v28
    engine = seed_configuration_fixture(sqlite, legacy=basis_kind == "legacy_transition", browser_ready=True)
    with engine.begin() as connection:
        from app.domains.worlds.contracts import NO_SPECIFIC_ROLE_NAME, NO_SPECIFIC_ROLE_DESCRIPTION
        connection.exec_driver_sql("UPDATE world_roles SET name=?, description=? WHERE role_key='no_specific_role'",
            (NO_SPECIFIC_ROLE_NAME, NO_SPECIFIC_ROLE_DESCRIPTION))
        # Historical fixture values must satisfy the existing UI's canonical
        # 17-hour policy before taking the immutable migration basis.
        connection.exec_driver_sql("UPDATE agent_activity_settings SET active_hours_start='09:00', active_hours_end='02:00'")
        connection.exec_driver_sql("UPDATE agent_activity_settings SET tendency_action_ranges=?",
            ('{"post":{"min":0,"max":8,"label":"fixture"}}',))
        # Unit fixtures use short World text. A browser registration invokes the
        # real definition refresh, so use a legitimately publishable synthetic
        # definition rather than overriding launchability or readiness results.
        connection.exec_driver_sql("UPDATE worlds SET tagline=?, setting_description=?, daily_life_description=?, genre_tags=?, tone_tags=?",
            ("A quiet synthetic fixture World", "A synthetic neighborhood for local character tests. " * 6,
             "Residents share ordinary daily routines in this synthetic World. " * 4,
             '["daily-life"]', '["calm"]'))
    from app.domains.worlds.models import World
    from app.domains.worlds.service.definition import refresh_world_contract, evaluate_world_readiness
    with Session(engine) as db:
        for world in db.scalars(select(World)):
            refresh_world_contract(db, world)
            if not evaluate_world_readiness(db, world).ready_for_publish:
                raise RuntimeError("fixture_world_definition_not_publishable")
        db.commit()
    if basis_kind == "legacy_transition":
        with engine.begin() as connection:
            before = v28.capture_delta(connection)
            v28.upgrade(connection)
            v28.verify_delta(connection, before)

    from app.database import get_db
    from app.api.identity_dependencies import get_current_user, get_optional_current_user
    from app.domains.identity.models import User
    from app.domains.world_characters.service.owner_identity import OwnerControlledIdentityService
    from app.domains.routines.models import AgentSlot, AgentRun
    with Session(engine, expire_on_commit=False) as db:
        from app.domains.relationships.models.social import RelationshipState
        user_roles = {}
        for suffix in ("a", "b"):
            OwnerControlledIdentityService(db).ensure(world_id=f"config-world-{suffix}", current_user_id="fixture-owner")
            from app.domains.world_characters.models import WorldCharacter
            user_roles[suffix] = db.scalar(select(WorldCharacter).where(WorldCharacter.world_id == f"config-world-{suffix}",
                WorldCharacter.control_mode == "owner_controlled"))
        db.add(RelationshipState(id="fixture-directed-friendship", world_id="config-world-a",
            actor_world_character_id="config-role-a", target_world_character_id=user_roles["a"].id,
            familiarity=2, affinity=1, trust=3, tension=0, interaction_count=4,
            relationship_label="Synthetic World friendship", perception="A synthetic directed perception"))
        db.add_all([AgentSlot(agent_id=f"fixture-slot-{index}", status="idle") for index in (1, 2)])
        db.commit()

    def task_db():
        with Session(engine, expire_on_commit=False) as db:
            yield db

    def task_owner(request: Request):
        # Return a detached ORM user. Sharing request Sessions across permission
        # and mutation services would hide the actual lock/CAS transaction order.
        with Session(engine, expire_on_commit=False) as db:
            user = db.get(User, "fixture-outsider" if request.headers.get("x-fixture-user") == "outsider" else "fixture-owner")
            db.expunge(user)
            return user

    app = FastAPI()
    app.add_middleware(CORSMiddleware, allow_origins=frontend_origins, allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"], allow_headers=["*"])
    app.dependency_overrides[get_db] = task_db
    app.dependency_overrides[get_current_user] = task_owner
    app.dependency_overrides[get_optional_current_user] = task_owner
    app.state.runtime_settings = settings
    from app.core.public_media import mount_public_media
    mount_public_media(app, settings)
    from app.runtime.characters.creator import build_creator_workflows
    from app.runtime.characters.management import build_character_management_workflows
    app.state.creator_workflows = build_creator_workflows
    app.state.character_management_workflows = build_character_management_workflows
    from app.runtime.social.composition import configure_social_runtime
    from app.runtime.graph_projection.composition import configure_relationships_runtime
    configure_social_runtime(app)
    configure_relationships_runtime(app)
    from app.runtime.chat.message_composition import configure_chat_services
    configure_chat_services(app)
    from app.api.v1.routes.agents import router as agents
    from app.domains.device_home.router import router as device_home
    from app.domains.worlds.router import router as worlds
    from app.domains.world_characters.router.management import router as management
    from app.domains.world_characters.router.profile import router as profiles
    from app.domains.world_characters.router.entry import router as entries
    from app.domains.social.router import router as social, manual_router as manual_social
    from app.domains.relationships.router import router as relationships
    from app.domains.chat.router.world_chat import router as chat
    from app.domains.chat.router.world_chat import entry_router as chat_entries
    from app.domains.chat.router.world_chat_response import router as chat_responses
    from app.domains.chat.router.retrieval_diagnostics import router as chat_diagnostics
    for router in (device_home, worlds, management, profiles, entries, social, manual_social, agents, chat, chat_entries, chat_responses, chat_diagnostics):
        app.include_router(router, prefix="/api/v1")
    app.include_router(relationships, prefix="/api/v1/characters")

    from app.runtime.resident import execution
    from app.domains.routines.service import runs
    from app.domains.routines import schemas as routine_schemas
    async def controlled_worker(db, *, slot, **kwargs):
        # This is after the actual manual admission, credential and resource
        # checks, and actual slot claim. Preserve precisely the admitted input.
        if slot.status != "running" or not slot.admission_metadata:
            raise RuntimeError("fixture_worker_without_actual_admission")
        snapshot = deepcopy(slot.admission_metadata)
        run_id, session_key = str(uuid4()), f"fixture:{slot.agent_id}:{uuid4()}"
        runs.create_agent_run(db, run_id=run_id, user_id=slot.assigned_user_id,
            character_id=slot.assigned_character_id, post_id=None, credential_id=slot.assigned_credential_id,
            agent_id=slot.agent_id, session_key=session_key, input_snapshot=snapshot)
        result = {"status": "completed", "summary": "Controlled worker; no provider call or public write.",
            "provider_call_count": 0, "public_write_count": 0}
        runs.mark_agent_run_finished(db, run_id, "completed", gateway_result=result)
        db.commit()
        return routine_schemas.OpenClawAgentRunRead(run_id=run_id, status="completed", summary=result["summary"],
            agent_id=slot.agent_id, session_key=session_key, character_id=slot.assigned_character_id,
            post_id=None, gateway_result=result)
    execution._run_resident_slot_once = controlled_worker

    @app.get("/api/v1/auth/me")
    def me(user=Depends(task_owner)):
        return {"id": user.id, "display_name": user.display_name, "email": None, "profile_setup_completed": True,
            "ui_language": "ko", "ui_preference_revision": 1, "feed_content_filter": "all", "is_admin": True}

    @app.get("/api/v1/auth/local/environment")
    @app.post("/api/v1/auth/local/environment")
    def environment(db=Depends(task_db)):
        from app.domains.identity.service.environment import read_environment
        return read_environment(db, "fixture-owner")

    @app.get("/api/v1/runtime/status")
    def status():
        return {"schema_version": "local-runtime-status-v1", "installation_state": "ready"}

    @app.get("/__fixture__/health")
    def health():
        return {"scope": "task-owned-configuration", "schema_version": 28,
            "formal_migration": basis_kind == "legacy_transition", "basis_kind": basis_kind, "provider_calls": 0}

    @app.get("/__fixture__/state")
    def state(db=Depends(task_db)):
        from app.domains.characters.models import Character
        from app.domains.characters.models_import import CharacterImportSnapshot, CharacterImportOrigin
        from app.domains.world_characters.models import WorldCharacter
        from app.domains.world_characters.configuration_models import WorldCharacterConfiguration
        return {
            "characters": [{"id": row.id, "name": row.name, "personality": row.personality, "avatar_url": row.avatar_url} for row in db.scalars(select(Character))],
            "snapshots": [{"id": row.id, "source_character_id": row.source_character_id, "kind": row.kind,
                "digest": row.digest, "payload": row.payload} for row in db.scalars(select(CharacterImportSnapshot))],
            "origins": [{"character_id": row.character_id, "snapshot_id": row.snapshot_id} for row in db.scalars(select(CharacterImportOrigin))],
            "roles": [{"id": row.id, "world_id": row.world_id, "character_id": row.character_id,
                "control_mode": row.control_mode, "autonomous_enabled": row.autonomous_enabled, "revision": row.version} for row in db.scalars(select(WorldCharacter))],
            "configs": [{"id": row.world_character_id, "profile": row.profile, "settings": row.settings} for row in db.scalars(select(WorldCharacterConfiguration))],
            "runs": [{"id": row.id, "character_id": row.character_id, "status": row.status,
                "input_snapshot": row.input_snapshot, "gateway_result": row.gateway_result} for row in db.scalars(select(AgentRun))],
        }

    @app.post("/__fixture__/prepare/{character_id}")
    def prepare(character_id: str, db=Depends(task_db)):
        from app.domains.characters.models import Character
        from app.domains.identity.models import LlmCredential
        from app.domains.routines.models import AgentActivitySetting
        character = db.get(Character, character_id)
        if character is None or character.owner_id != "fixture-owner":
            raise ValueError("fixture_character_missing")
        db.add(LlmCredential(id=f"fixture-copy-credential-{character_id}", owner_id="fixture-owner", character_id=character_id,
            provider="gemini", model="gemini-3.1-flash-lite", purpose="agent", auth_profile_id=f"fixture:{character_id}",
            label="synthetic no key", enabled=True, encrypted_api_key=None, key_fingerprint=None))
        setting = db.get(AgentActivitySetting, character_id)
        setting.tendency_summary = "fixture"
        setting.tendency_action_ranges = {"post": {"min": 0, "max": 8, "label": "fixture"}}
        setting.tendency_updated_at = datetime.now(UTC)
        setting.planner_tendency_profile = {"feed_seed_interest_criteria": "Natural interests"}
        db.commit()
        return {"prepared": character_id, "provider_calls": 0}
    return app


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--state-dir", required=True, type=Path)
    parser.add_argument("--frontend-origin", action="append", required=True)
    parser.add_argument("--port", type=int, default=3356)
    parser.add_argument("--basis-kind", choices=("creation", "legacy_transition"), default="legacy_transition")
    args = parser.parse_args()
    uvicorn.run(build_fixture(args.state_dir, args.frontend_origin, args.basis_kind), host="127.0.0.1", port=args.port)
