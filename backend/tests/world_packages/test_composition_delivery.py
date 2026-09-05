from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from fastapi import FastAPI, Request
from sqlalchemy.exc import IntegrityError

from app.domains.world_packages import dependencies
from app.domains.world_packages.contracts.runtime import WorldPackageRuntimeFactories
from app.domains.world_packages.exceptions import (
    WorldPackageContractError,
    WorldPackageReasonCode,
)
from app.domains.world_packages.service import delivery


def test_application_supplied_factories_keep_the_request_session_and_one_recovery(tmp_path):
    db, session_factory = object(), object()
    source, probe, committer = Mock(), Mock(), Mock()
    factories = WorldPackageRuntimeFactories(
        source_snapshot=Mock(return_value=source),
        preview_probe=Mock(return_value=probe),
        import_committer=Mock(return_value=committer),
    )
    app = FastAPI()
    app.state.world_package_factories = factories
    app.state.runtime_config = None
    app.state.runtime_settings = SimpleNamespace(
        media_root_path=tmp_path / "media", media_url_path="/media",
    )
    app.state.runtime_composition = SimpleNamespace(session_factory=session_factory)
    request = Request({"type": "http", "app": app})

    exporter = dependencies._exporter(request, db)
    stager = dependencies._stager(request, db)
    first = dependencies._import_committer(request, db)
    second = dependencies._import_committer(request, db)

    assert exporter._source is source
    assert stager._preview_probe is probe
    assert factories.source_snapshot.call_args.args == (db,)
    assert factories.preview_probe.call_args.args == (db,)
    assert first is second is committer
    assert factories.import_committer.call_args.args == (session_factory,)
    assert factories.import_committer.call_count == 1
    assert committer.recover_media.call_count == 1


@pytest.mark.parametrize("failure", [
    IntegrityError("insert lineage", {}, RuntimeError("fixture constraint")),
    RuntimeError("fixture commit failure"),
])
def test_prepared_export_commit_failure_rolls_back_and_discards_only_its_artifact(failure):
    db = Mock()
    db.commit.side_effect = failure
    exporter, store = Mock(), Mock()
    preview = SimpleNamespace(
        recommended_filename="fixture.angmoo-world", package_id="fixture-package",
        package_version=1, seed_digest="fixture-seed",
        license=SimpleNamespace(expression="CC0-1.0"),
    )
    archive = SimpleNamespace(content=b"fixture", manifest_digest="fixture-manifest", archive_digest="fixture-archive")
    exporter.build.return_value = preview, archive
    store.create.return_value = object(), "fixture-token", False
    expected = WorldPackageContractError if isinstance(failure, IntegrityError) else RuntimeError

    with pytest.raises(expected) as caught:
        delivery.prepare_export(
            db=db, exporter=exporter, artifact_store=store,
            operation_id="owned-operation", source_world_id="fixture-world",
            local_owner_id="fixture-owner", license=preview.license,
            license_text=None, idempotency_key="fixture-request",
        )

    assert db.rollback.call_count == 1
    assert store.discard.call_args.args == ("owned-operation",)
    assert store.discard.call_count == 1
    if isinstance(failure, IntegrityError):
        assert caught.value.reason_code is WorldPackageReasonCode.COMMIT_CONFLICT
    else:
        assert caught.value is failure


def test_native_ack_commit_failure_keeps_artifact_for_retry(monkeypatch):
    db, store, registry = Mock(), Mock(), Mock()
    failure = RuntimeError("fixture commit unknown")
    db.commit.side_effect = failure
    store.claim.return_value = SimpleNamespace(
        operation_id="owned-operation", package_id="fixture-package",
        package_version=1, source_world_id="fixture-world", seed_digest="fixture-seed",
        manifest_digest="fixture-manifest", license_expression="CC0-1.0",
    )
    monkeypatch.setattr(delivery, "SqlAlchemyWorldPackageRegistry", lambda session: registry if session is db else None)

    with pytest.raises(RuntimeError) as caught:
        delivery.acknowledge_export_delivery(
            db=db, artifact_store=store, operation_id="owned-operation",
            owner_id="fixture-owner", token="fixture-token",
        )

    assert caught.value is failure
    assert db.rollback.call_count == 1
    assert registry.record_export_delivery.call_count == 1
    assert registry.record_export_delivery.call_args.args[0].delivery_mode == "tauri_save_as"
    assert store.discard.call_count == 0
