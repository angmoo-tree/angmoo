"""Task-owned file SQLite and synthetic World instances; never user configuration."""
from datetime import UTC, datetime
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session
from app.models import Base
from app.runtime.persistence.model_registration import register_models
from app.domains.identity.models import User, InstallationIdentity, LlmCredential
from app.domains.characters.models import Character
from app.domains.routines.models import AgentActivitySetting
from app.domains.worlds.models import World, WorldMembership, WorldRole
from app.domains.world_characters.models import WorldCharacter, CharacterWorldBinding, CharacterActiveWorld
from app.domains.characters.models_import import CharacterImportOrigin
from app.domains.characters.service.import_snapshots import get_import_snapshot
from app.domains.world_characters.service.configuration import initialize_configuration
from app.runtime.world_characters.creation_configuration import initialize_created_world_character, creation_configuration
from app.domains.world_characters.service.owner_identity import OwnerControlledIdentityService


def seed_configuration_fixture(path, *, legacy=False, browser_ready=False):
    register_models()
    engine = create_engine(f"sqlite:///{path}", connect_args={"check_same_thread": False, "timeout": 10})
    @event.listens_for(engine, "connect")
    def _fk(connection, _):
        connection.execute("PRAGMA foreign_keys=ON")
    if legacy:
        from app.runtime.persistence.sqlite_schema import build_sqlite_v27_metadata, create_schema_version_table
        build_sqlite_v27_metadata().create_all(engine)
        with engine.begin() as connection:
            create_schema_version_table(connection)
    else:
        Base.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as db:
        owner = User(id="fixture-owner", email="owner@example.test", display_name="Owner", display_name_normalized="owner",
            privacy_policy_version="test", terms_version="test", profile_setup_completed=True)
        outsider = User(id="fixture-outsider", email="outsider@example.test", display_name="Outsider", display_name_normalized="outsider",
            privacy_policy_version="test", terms_version="test", profile_setup_completed=True)
        db.add_all([owner, outsider])
        db.flush()
        db.add(InstallationIdentity(singleton_key="local-installation", installation_id="configuration-fixture",
            owner_user_id=owner.id, bootstrap_state="claimed", local_label="fixture", claimed_at=datetime.now(UTC)))
        for suffix in ("a", "b"):
            wid, cid, wc = f"config-world-{suffix}", f"config-actor-{suffix}", f"config-role-{suffix}"
            db.add(World(id=wid, slug=wid, owner_user_id=owner.id, name=f"World {suffix}", tagline="fixture", setting_description="fixture",
                daily_life_description="fixture", genre_tags=[], tone_tags=[], banner_alt_text="", timezone="Asia/Seoul", language="ko",
                visibility="public", join_policy="open", status="published", definition_version=1, row_version=1,
                contract_version="world-v1", contract_hash=suffix*64, readiness_status="publish_ready", additional_generation_guidance="",
                create_idempotency_key=f"fixture-create-{suffix}"))
            db.flush()
            db.add(WorldMembership(id=f"config-member-{suffix}", world_id=wid, user_id=owner.id, role="owner", status="active", joined_at=datetime.now(UTC)))
            db.add(WorldRole(id=f"config-world-role-{suffix}", world_id=wid, role_key="no_specific_role", name="No specific role",
                description="", responsibilities=[], allowed_activity_scope=[], autonomous_allowed=True, status="enabled"))
            character = Character(id=cid, owner_id=owner.id, name="Bram", handle=f"bram_{suffix}", one_liner="Original intro",
                personality="Original persona", speech_style="Original speech", worldview="Original world", character_background="Original history",
                topic_preferences="Nature", safety_rules="Be kind", persona_summary="Original summary", status="active", execution_mode="llm")
            db.add(character)
            db.flush()
            role = WorldCharacter(id=wc, world_id=wid, character_id=cid, membership_id=f"config-member-{suffix}", role_key="no_specific_role",
                status="active", control_mode="autonomous", autonomous_enabled=False, activity_runtime_mode="routine_resident_v1",
                feed_runtime_mode="topic_recommendation_v1", local_profile={}, version=1)
            db.add(role)
            db.add(AgentActivitySetting(character_id=cid, auto_enabled=False, activity_interval_minutes=30,
                active_hours_start="09:00" if browser_ready else "00:00", active_hours_end="02:00" if browser_ready else "00:00",
                max_posts_per_day=8, max_comments_per_day=12,
                tendency_summary="fixture", tendency_action_ranges={"post": {"min": 0, "max": 8, "label": "게시글"}} if browser_ready else {"post": [0, 8]}, tendency_updated_at=datetime.now(UTC),
                planner_tendency_profile={"feed_seed_interest_criteria": "Natural interests"}))
            db.add(LlmCredential(id=f"config-credential-{suffix}", owner_id=owner.id, character_id=cid, provider="gemini",
                model="gemini-3.1-flash-lite", purpose="agent", auth_profile_id=f"fixture:{cid}", label="synthetic", enabled=True,
                encrypted_api_key=None, key_fingerprint=None))
            db.flush()
            db.add(CharacterWorldBinding(character_id=cid, world_id=wid))
            db.add(CharacterActiveWorld(character_id=cid, world_character_id=wc, selected_at=datetime.now(UTC), idempotency_key=f"fixture:{wc}", version=1))
            db.flush()
            if not legacy:
                if suffix == "a":
                    initialize_created_world_character(db, character=character, world_character=role)
                else:
                    origin, configuration = get_import_snapshot(db, "config-actor-a")
                    db.add(CharacterImportOrigin(character_id=cid, snapshot_id=origin.id))
                    db.flush()
                    initialize_configuration(db, world_character=role, snapshot_id=origin.id,
                        configuration=creation_configuration(db, character, inherited=configuration.settings))
        db.commit()
        if not legacy:
            for suffix in ("a", "b"):
                OwnerControlledIdentityService(db).ensure(world_id=f"config-world-{suffix}", current_user_id=owner.id)
    return engine


def fixture_owner(db):
    return db.get(User, "fixture-owner")


def install_configuration_image_fixture(db, character_id):
    """Controlled, synthetic local workflow profile; no key or Provider call."""
    import json
    from app.domains.characters.models import AgentImageGenerationSetting
    model = "fixture-workflow"
    workflow = {"prompt": {"1": {"class_type": "SyntheticImage", "inputs": {"positive": "", "negative": ""}}},
        "bindings": {"positive": {"node_id": "1", "input_name": "positive"},
            "negative": {"node_id": "1", "input_name": "negative"}}, "output_node": "1"}
    profile = {"active": True, "connection": {"ready": True, "synthetic_test_only": True},
        "options": {"base_url": "http://127.0.0.1:8188", "workflow": workflow}, "reference_effective": False}
    row = AgentImageGenerationSetting(character_id=character_id, generation_provider="comfyui", generation_model=model,
        generation_profiles_json=json.dumps({f"comfyui:{model}:": profile}), generation_auto_enabled=True,
        generation_revision=2, generation_daily_limit=4, style_prompt="Common ink", appearance_prompt="Common appearance", negative_prompt="blur")
    db.add(row)
    db.flush()
    return "comfyui:" + model
