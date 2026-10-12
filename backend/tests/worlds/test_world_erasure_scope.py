"""Populated canonical scopes, durable recovery and shared-resource preservation."""
from datetime import UTC, datetime, timedelta
import json
import pytest
from sqlalchemy import select, text, update
from sqlalchemy.exc import IntegrityError
from app.domains.worlds.models import World, WorldMembership, OwnerDefaultWorld
from app.domains.worlds.models_deletion import WorldDeletionRequest, WorldDeletionCleanupItem
from app.domains.worlds.service import deletion
from app.domains.worlds.contracts_deletion import WorldDeletionError
from app.runtime.world_deletion.worker import WorldDeletionWorker
from app.runtime.world_deletion.ports import stop_admission
from worlds.test_world_deletion import environment, admitted, finish, command


@pytest.mark.parametrize("status,visibility", [("draft", "private"), ("published", "private"),
    ("published", "public"), ("published", "unlisted"), ("archived", "private")])
def test_every_owned_nondefault_stage_uses_same_erasure_contract(environment, status, visibility):
    sessions, ports, _ = environment
    with sessions() as db:
        world = db.get(World, "a")
        world.name, world.status, world.visibility = "SNS", status, visibility
        db.commit()
        assert deletion.preview(db, "a", "owner").can_delete
    admitted(sessions, confirmed_name="SNS")
    assert finish(sessions, ports).state == "completed"


def test_default_binding_survives_rename_and_missing_legacy_binding_is_not_guessed(environment):
    sessions, _, _ = environment
    with sessions() as db:
        from types import SimpleNamespace
        from app.domains.worlds.service.creator import update_world, archive_world
        from app.domains.worlds.schemas import WorldUpdate, WorldMutationRequest
        from app.domains.worlds.exceptions import WorldDefinitionValidationError
        db.add(OwnerDefaultWorld(owner_id="owner", world_id="a"))
        db.commit()
        update_world(db,world_id="a",user=SimpleNamespace(id="owner"),data=WorldUpdate(row_version=1,name="Renamed default space",tagline="Editable default",genre_tags=["everyday"]))
        assert db.get(World,"a").name=="Renamed default space"
        assert db.get(OwnerDefaultWorld,"owner").world_id=="a"
        with pytest.raises(WorldDefinitionValidationError,match="default_space_cannot_be_archived"):
            archive_world(db,world_id="a",user=SimpleNamespace(id="owner"),data=WorldMutationRequest(row_version=db.get(World,"a").row_version))
        assert deletion.preview(db, "a", "owner").is_default_space
        with pytest.raises(WorldDeletionError, match="default_space_cannot_be_deleted"):
            deletion.accept(db, "a", "owner", command(confirmed_name="Renamed default space"), stop_admission=stop_admission)
        db.delete(db.get(OwnerDefaultWorld, "owner"))
        db.get(World, "a").create_idempotency_key = "default-sns:owner"
        db.commit()
        with pytest.raises(WorldDeletionError, match="default_space_recovery_required"):
            deletion.preview(db, "a", "owner")


@pytest.mark.parametrize("role", ["editor", "member"])
def test_membership_role_does_not_grant_world_deletion(environment, role):
    sessions, _, _ = environment
    with sessions() as db:
        db.get(WorldMembership, "member-a").role = role
        db.commit()
        with pytest.raises(WorldDeletionError):
            deletion.accept(db, "a", "owner", command(), stop_admission=stop_admission)


def test_populated_memory_unsaved_experiences_image_and_received_files_are_erased(environment):
    from memory.test_p8_l_h_canonical_recall import _accept_chat_memory
    from app.domains.characters.models import Character
    from app.domains.characters.service.import_snapshots import capture_creation
    from app.domains.characters.service.import_configuration import ImportConfiguration, ImportProfile, ImportSettings
    from app.domains.chat.models import MessageMessage
    from app.domains.memory.models.items import MemoryCandidate, MemoryScopeSettingModel
    from app.domains.memory.contracts.provenance import MemorySourceTypeV1, MemoryKindV1
    from app.domains.memory.service.items import MemoryWriteLifecycleService
    from app.runtime.memory.composition import memory_repository
    from app.runtime.memory.source_composition import source_evidence_reader
    from app.domains.media.models import MediaAsset, ImageInterpretation
    from app.domains.memory.models.activity_situation import MemorySituationManifest, MemorySituationReceipt
    from app.domains.world_characters.activity_models import ActivityGraphRun
    from app.runtime.autonomous_activity.checkpoints import erase_activity_checkpoint
    from functools import partial
    sessions, ports, effects = environment
    scope, counterpart, thread, message, item = _accept_chat_memory(sessions)
    ports.checkpoint_cleanup = partial(erase_activity_checkpoint, ports.media_root.parent)
    path = ports.media_root / "private-image-assets" / "image-a.webp"
    path.parent.mkdir(parents=True)
    path.write_bytes(b"only this temporary image")
    spool = path.parent / "received-interpretations" / ("1" * 32 + ".json")
    spool.parent.mkdir()
    spool.write_text('{"analysis":"private observation"}', encoding="utf-8")
    with sessions() as db:
        from app.domains.identity.models import InstallationIdentity
        db.get(InstallationIdentity, "local-installation").owner_user_id = scope.owner_id
        for character in db.scalars(select(Character).where(Character.owner_id == scope.owner_id)):
            capture_creation(db, character_id=character.id,
                configuration=ImportConfiguration(profile=ImportProfile(display_name=character.name, handle=character.handle), settings=ImportSettings()), provenance="test first registration")
        second = MessageMessage(thread_id=thread, role="user", content="unsaved experience body")
        db.add(second)
        db.flush()
        lifecycle = MemoryWriteLifecycleService(memory_repository(db), source_evidence_reader(db))
        proposed = lifecycle.propose_candidate(scope=scope, source_type=MemorySourceTypeV1.OWNER_MEMORY_REQUEST,
            source_id=str(second.id), memory_kind=MemoryKindV1.AUTOBIOGRAPHICAL_EVENT)
        assert proposed.candidate is not None
        setting = db.scalar(select(MemoryScopeSettingModel).where(MemoryScopeSettingModel.world_id == scope.world_id))
        db.add(MemorySituationManifest(id="manifest-fixture", scope_setting_id=setting.id, call_identity="routine-fixture",
            content_digest="e" * 64, payload={"private_thought": "erase this private basis"}, created_at=datetime.now(UTC)))
        db.flush()
        db.add(MemorySituationReceipt(scope_setting_id=setting.id, logical_activity_id="graph-fixture", lane="routine",
            target_key="routine", manifest_id="manifest-fixture", policy_version="fixture-v1", activation_epoch="fixture",
            scope_version=1, content_digest="f" * 64, description="unsaved situation description", description_status="valid",
            result={"private_thought": "erase this result"}, occurred_at=datetime.now(UTC), captured_at=datetime.now(UTC), state="blocked"))
        db.add(ActivityGraphRun(activity_id="graph-fixture", world_id=scope.world_id, world_character_id=scope.subject_world_character_id,
            engine="graph-v2", contract_version=2, status="completed", stage="finished", result={"private_thought":"erase this checkpoint"},
            started_at=datetime.now(UTC), finished_at=datetime.now(UTC)))
        db.add(MediaAsset(id="image-a", owner_id=scope.owner_id, scope_kind="thread", scope_id=thread,
            storage_key="image-a.webp", content_type="image/webp", content_hash="a" * 64, byte_size=20, width=1, height=1))
        db.flush()
        db.add(ImageInterpretation(id="1" * 32, cache_key="b" * 64, asset_id="image-a", owner_id=scope.owner_id,
            scope_key=thread, asset_revision=1, model="fixture", thinking_level="medium", credential_revision=1,
            status="queued", description="private description"))
        db.commit()
        deletion.accept(db, scope.world_id, scope.owner_id, command(confirmed_name="Recall World"), stop_admission=stop_admission)
    # This fixture also contains unrelated Worlds a and b.
    worker = WorldDeletionWorker(sessions, ports)
    for _ in range(600):
        worker.tick()
        with sessions() as db:
            receipt = db.scalar(select(WorldDeletionRequest))
            if receipt.state in {"completed", "failed"}:
                break
    assert receipt.state == "completed", (receipt.stage, receipt.failure_code)
    assert item in effects["index"] and not path.exists() and not spool.exists()
    with sessions() as db:
        assert list(db.scalars(select(MemoryCandidate))) == []
        assert list(db.scalars(select(MemoryScopeSettingModel))) == []
        assert list(db.scalars(select(MessageMessage))) == []
        assert db.get(MediaAsset, "image-a") is None
        assert db.get(ImageInterpretation, "1" * 32) is None
        assert db.get(MemorySituationManifest, "manifest-fixture") is None
        assert db.scalar(select(MemorySituationReceipt)) is None
        assert db.get(ActivityGraphRun, "graph-fixture") is None
        assert db.get(World, "b").name == "World b"
        assert tuple(db.execute(text("PRAGMA foreign_key_check"))) == ()


def test_unsettled_public_effect_is_not_completed_by_timeout_and_can_resume(environment):
    from worlds.test_foundation import _character
    from app.domains.routines.models.resident import AgentRun, AgentPublicActionExecution
    sessions, ports, _ = environment
    with sessions() as db:
        db.add(_character("runner", "owner"))
        db.flush()
        db.add(AgentRun(id="run-a", user_id="owner", character_id="runner", agent_id="slot-a", session_key="fixture",
            status="succeeded", input_snapshot={"_world_credential": {"world_id": "a"}}))
        db.flush()
        db.add(AgentPublicActionExecution(run_id="run-a", character_id="runner", signature="fixture", scope="world",
            action_type="post", world_id="a", status="outcome_unknown"))
        db.commit()
    accepted = admitted(sessions)
    worker = WorldDeletionWorker(sessions, ports)
    with sessions() as db:
        row = db.get(WorldDeletionRequest, accepted.request_id)
        row.accepted_at = datetime.now(UTC) - timedelta(minutes=6)
        db.commit()
    for _ in range(3):
        worker.tick()
        with sessions() as db:
            row = db.get(WorldDeletionRequest, accepted.request_id)
            row.next_attempt_at = None
            db.commit()
    with sessions() as db:
        row = db.get(WorldDeletionRequest, accepted.request_id)
        assert row.state == "failed" and row.stage == "draining"
        assert db.scalar(select(AgentPublicActionExecution)).status == "outcome_unknown"
        # Actual owner settlement, not an elapsed-time assumption.
        db.scalar(select(AgentPublicActionExecution)).status = "failed"
        db.commit()
        deletion.retry(db, row.id, "owner")
    assert finish(sessions, ports).state == "completed"


def test_expired_worker_lease_resumes_same_request_and_stale_commit_is_rejected(environment):
    from sqlalchemy.orm.exc import StaleDataError
    sessions, ports, _ = environment
    accepted = admitted(sessions)
    with sessions() as db:
        row = db.get(WorldDeletionRequest, accepted.request_id)
        row.lease_until = datetime.now(UTC) + timedelta(minutes=1)
        db.commit()
    assert not WorldDeletionWorker(sessions, ports).tick()
    with sessions() as old, sessions() as fresh:
        stale = old.get(WorldDeletionRequest, accepted.request_id)
        fresh.execute(update(WorldDeletionRequest).where(WorldDeletionRequest.id == accepted.request_id).values(
            lease_epoch=WorldDeletionRequest.lease_epoch + 1, lease_until=None))
        fresh.commit()
        stale.cursor = 99
        with pytest.raises(StaleDataError):
            old.commit()
        old.rollback()
    assert finish(sessions, ports).state == "completed"


def test_shared_managed_file_and_external_download_survive_target_cleanup(environment, tmp_path):
    sessions, ports, _ = environment
    shared = ports.media_root / "worlds/a/shared.webp"
    shared.parent.mkdir(parents=True)
    shared.write_bytes(b"shared managed image")
    external = tmp_path / "Downloads/export.angmoo-world"
    external.parent.mkdir()
    external.write_bytes(b"user-owned exported file")
    with sessions() as db:
        db.get(World, "a").icon_media_id = "/media/worlds/a/shared.webp"
        db.get(World, "b").icon_media_id = "/media/worlds/a/shared.webp"
        db.commit()
    admitted(sessions)
    assert finish(sessions, ports).state == "completed"
    assert shared.read_bytes() == b"shared managed image"
    assert external.read_bytes() == b"user-owned exported file"


def test_missing_file_and_permission_failure_keep_exact_journal_and_retry(environment, monkeypatch):
    from pathlib import Path
    sessions, ports, _ = environment
    missing = ports.media_root / "worlds/a/missing.webp"
    with sessions() as db:
        db.get(World, "a").banner_media_id = "/media/worlds/a/missing.webp"
        db.commit()
    receipt = admitted(sessions)
    original = Path.unlink
    def denied(path, *args, **kwargs):
        if path == missing:
            raise PermissionError("synthetic permission failure")
        return original(path, *args, **kwargs)
    worker = WorldDeletionWorker(sessions, ports)
    with monkeypatch.context() as patch:
        patch.setattr(Path, "unlink", denied)
        for _ in range(200):
            worker.tick()
            with sessions() as db:
                row = db.get(WorldDeletionRequest, receipt.request_id)
                if row.state == "retry_wait":
                    row.next_attempt_at = None
                    db.commit()
                if row.state == "failed":
                    assert row.stage == "cleaning"
                    assert db.scalar(select(WorldDeletionCleanupItem).where(WorldDeletionCleanupItem.kind == "file")).state == "pending"
                    break
    with sessions() as db:
        deletion.retry(db, receipt.request_id, "owner")
    assert finish(sessions, ports).state == "completed"


def test_managed_child_link_cannot_erase_an_external_directory(environment, tmp_path):
    import os
    sessions, ports, _ = environment
    outside=tmp_path / "outside-sentinel"
    outside.mkdir()
    sentinel=outside / "keep.webp"
    sentinel.write_bytes(b"outside owned data")
    link=ports.media_root / "worlds/a"
    link.parent.mkdir(parents=True)
    if os.name=="nt":
        import _winapi
        _winapi.CreateJunction(str(outside),str(link))
    else:
        link.symlink_to(outside,target_is_directory=True)
    try:
        with pytest.raises(ValueError,match="world_erasure_path_link"):
            ports._safe_path("worlds/a/keep.webp")
        assert sentinel.read_bytes()==b"outside owned data"
    finally:
        if os.name=="nt":link.rmdir()
        else:link.unlink()


def test_package_lineage_is_minimal_shared_and_old_import_replay_cannot_restore_world(environment):
    from app.domains.world_packages.models import WorldPackageSource, WorldPackageImport, WorldPackageImportIdMap
    from app.runtime.world_packages.import_commit import SqlAlchemyWorldPackageImportCommitter
    from app.domains.world_packages.exceptions import WorldPackageContractError
    sessions, ports, _ = environment
    with sessions() as db:
        db.add(WorldPackageSource(package_id="package-a", source_world_id="a"))
        db.add(WorldPackageImport(import_id="import-a", local_owner_id="owner", package_id="external-package", package_version=1,
            content_digest="d" * 64, imported_world_id="a", import_mode="new_world", trust_state="checksum_verified_unsigned",
            license_expression="CC0-1.0", idempotency_key="import-fixture"))
        db.flush()
        db.add(WorldPackageImportIdMap(id="map-a", import_id="import-a", source_ref="world", entity_kind="world", local_id="a"))
        db.commit()
    admitted(sessions)
    assert finish(sessions, ports).state == "completed"
    with sessions() as db:
        assert db.get(WorldPackageSource, "package-a").source_world_id == "a"
        record = db.get(WorldPackageImport, "import-a")
        assert record is not None and db.get(WorldPackageImportIdMap, "map-a") is None
        with pytest.raises(WorldPackageContractError):
            SqlAlchemyWorldPackageImportCommitter._result_from_record(db, record, replayed=True)


def test_only_target_slot_is_cleared_and_new_target_lease_is_fenced(environment):
    from app.domains.routines.models import AgentSlot
    sessions, _, _ = environment
    with sessions() as db:
        for world in ("a", "b"):
            db.add(AgentSlot(agent_id="slot-" + world, status="idle", admission_metadata={"_world_credential": {"world_id": world}}))
        db.commit()
    admitted(sessions)
    with sessions() as db:
        assert db.get(AgentSlot, "slot-a").admission_metadata is None
        assert db.get(AgentSlot, "slot-b").admission_metadata["_world_credential"]["world_id"] == "b"
        db.get(AgentSlot, "slot-a").admission_metadata = {"_world_credential": {"world_id": "a"}}
        db.get(AgentSlot, "slot-a").status = "running"
        with pytest.raises(IntegrityError, match="world_deleting"):
            db.commit()
        db.rollback()


def test_small_batches_allow_other_world_admission_and_receipts_contain_no_confirmation_text(environment):
    from app.domains.worlds.models import WorldPlace
    sessions, ports, _ = environment
    with sessions() as db:
        for index in range(25):
            db.add(WorldPlace(id=f"extra-{index}", world_id="a", place_key=f"place-{index}", name="temporary place"))
        db.commit()
    receipt = admitted(sessions)
    worker = WorldDeletionWorker(sessions, ports, batch_size=2)
    for _ in range(10):
        worker.tick()
        with sessions() as db:
            assert db.get(World, "b").name == "World b"
    with sessions() as db:
        row = db.get(WorldDeletionRequest, receipt.request_id)
        assert row.idempotency_key != command().idempotency_key
        assert "World a" not in json.dumps({column.name: str(getattr(row, column.name)) for column in row.__table__.columns})
        db.add(WorldMembership(id="new-other-world", world_id="b", user_id="other", role="member", status="active"))
        db.commit()
    assert finish(sessions,ports).state=="completed"
    with sessions() as db:
        assert list(db.scalars(select(WorldPlace).where(WorldPlace.world_id=="a")))==[]
        assert db.get(WorldMembership,"new-other-world") is not None
