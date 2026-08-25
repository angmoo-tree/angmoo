from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import URL, create_engine

from app import models as _models  # noqa: F401 - register canonical metadata
from app.runtime.migrations.ladybug_versions.registry import (
    GRAPH_REBUILDS,
    LadybugVersionContractError,
    validate_latest_ladybug_contract,
)
from app.runtime.migrations.sqlite_versions.registry import (
    MIGRATIONS,
    SqliteVersionContractError,
    load_sqlite_manifest,
    migration_chain,
)
from app.runtime.persistence.sqlite_schema import (
    SQLITE_SCHEMA_VERSION,
    build_sqlite_baseline_metadata,
    build_sqlite_v1_metadata,
    create_schema_version_table,
    sqlite_schema_contract_digest,
)


def _metadata_contract_digest(tmp_path: Path, *, version: int) -> str:
    path = tmp_path / f"schema-v{version}.sqlite3"
    engine = create_engine(URL.create("sqlite+pysqlite", database=str(path)))
    metadata = (
        build_sqlite_v1_metadata()
        if version == 1
        else build_sqlite_baseline_metadata()
    )
    try:
        with engine.begin() as connection:
            create_schema_version_table(connection)
            metadata.create_all(connection)
            return sqlite_schema_contract_digest(connection)
    finally:
        engine.dispose()


def test_sqlite_manifests_match_frozen_v1_and_latest_model_contract(
    tmp_path: Path,
) -> None:
    v1 = load_sqlite_manifest(1)
    latest = load_sqlite_manifest(SQLITE_SCHEMA_VERSION)

    assert v1.schema_digest == _metadata_contract_digest(tmp_path, version=1)
    assert latest.schema_digest == _metadata_contract_digest(
        tmp_path,
        version=SQLITE_SCHEMA_VERSION,
    )
    assert latest.canonical_table_count == 87
    assert tuple(version for version, _step in migration_chain(1)) == (1,)
    assert 1 in MIGRATIONS


def test_ladybug_manifest_matches_adapter_command_and_query_contract() -> None:
    manifest = validate_latest_ladybug_contract()

    assert manifest.projection_schema_version == 1
    assert manifest.projection_schema_version in GRAPH_REBUILDS


def test_both_embedded_entrypoints_own_the_common_upgrade_coordinator() -> None:
    root = Path(__file__).resolve().parents[1]
    contributor = (root / "app/runtime/contributor_backend.py").read_text(
        encoding="utf-8"
    )
    sidecar = (root / "app/runtime/desktop_sidecar.py").read_text(
        encoding="utf-8"
    )
    ci_workflow = (root.parent / ".github/workflows/ci.yml").read_text(
        encoding="utf-8"
    )

    assert "EmbeddedDataUpgradeCoordinator" in contributor
    assert "EmbeddedDataUpgradeCoordinator" in sidecar
    assert "SqliteCanonicalDatabase(" not in contributor
    assert "check_embedded_data_migration_contract.py" in ci_workflow
    assert "BASE_SHA" in ci_workflow


def test_missing_sqlite_migration_step_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delitem(MIGRATIONS, 1)

    with pytest.raises(
        SqliteVersionContractError,
        match="sqlite_migration_step_missing:v1_to_v2",
    ):
        migration_chain(1)


def test_missing_ladybug_rebuild_target_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delitem(GRAPH_REBUILDS, 1)

    with pytest.raises(
        LadybugVersionContractError,
        match="ladybug_rebuild_target_missing:v1",
    ):
        validate_latest_ladybug_contract()
