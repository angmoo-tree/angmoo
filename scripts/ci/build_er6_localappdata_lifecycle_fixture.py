#!/usr/bin/env python3
"""Build the synthetic legacy LocalAppData fixture used by the ER6 closeout.

The output is deliberately synthetic and contains no personal data or usable
provider credential.  It exists only to prove that the installed product can
migrate and preserve the canonical LocalAppData contract.
"""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
import hashlib
import json
from pathlib import Path
import shutil
import sys

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = REPOSITORY_ROOT / "backend"
sys.path.insert(0, str(BACKEND_ROOT))

from app import models as _models  # noqa: E402,F401 - register metadata
from app.runtime.persistence.runtime_data_path import (  # noqa: E402
    StaticRuntimeDataPath,
)
from app.runtime.persistence.sqlite_database import (  # noqa: E402
    SqliteCanonicalDatabase,
    SqliteCanonicalSettings,
)
from app.runtime.persistence.sqlite_schema import (  # noqa: E402
    build_sqlite_baseline_metadata,
)

GENERATION = "er6-preview-v1"
FIXTURE_ID = "er6-localappdata-lifecycle-v1"
FIXED_NOW = datetime(2026, 8, 23, 3, 0, tzinfo=UTC)
SYNTHETIC_SECRET = "er6-synthetic-localappdata-secret-not-a-real-key"
PERSISTENT_DIRECTORIES = ("canonical", "graph", "search", "media", "secrets")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-root", required=True, type=Path)
    parser.add_argument("--force", action="store_true")
    return parser


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _persistent_files(root: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    for directory_name in PERSISTENT_DIRECTORIES:
        directory = root / directory_name
        if not directory.exists():
            continue
        for path in sorted(directory.rglob("*")):
            if path.is_file():
                result[path.relative_to(root).as_posix()] = _sha256(path)
    return result


def build_fixture(output_root: Path, *, force: bool = False) -> dict[str, object]:
    output_root = output_root.resolve()
    if output_root.exists() and any(output_root.iterdir()):
        if not force:
            raise RuntimeError("fixture_output_root_not_empty")
        shutil.rmtree(output_root)
    output_root.mkdir(parents=True, exist_ok=True)

    secret_path = output_root / "secrets" / "app-secret"
    secret_path.parent.mkdir(parents=True)
    secret_path.write_text(SYNTHETIC_SECRET + "\n", encoding="utf-8")

    proof_files = {
        "media/world-er6/banner.txt": "synthetic-media-proof\n",
        "graph/ladybug/replay.marker": "world-er6:event-er6\n",
        "search/fts.digest": "synthetic-search-proof\n",
        "runtime/legacy-owner.lock": "must-not-migrate\n",
        "WebView2/Cookies": "must-reconnect-not-copy\n",
    }
    for relative, content in proof_files.items():
        path = output_root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    database = SqliteCanonicalDatabase(
        StaticRuntimeDataPath(output_root),
        settings=SqliteCanonicalSettings(generation=GENERATION),
    )
    database.open()
    metadata = build_sqlite_baseline_metadata()
    with database.engine.begin() as connection:
        connection.execute(
            metadata.tables["users"].insert().values(
                id="owner-er6",
                display_name="ER6 Synthetic Owner",
                display_name_normalized="er6 synthetic owner",
                profile_setup_completed=True,
                created_at=FIXED_NOW,
            )
        )
        connection.execute(
            metadata.tables["characters"].insert().values(
                id="character-er6-mango",
                owner_id="owner-er6",
                name="ER6 Mango",
                handle="er6-mango",
                one_liner="Synthetic installed lifecycle fixture",
                personality="calm",
                speech_style="friendly",
                worldview="curious",
                topic_preferences="local runtime",
                safety_rules="synthetic only",
                status="active",
                moderation_status="active",
                execution_mode="llm",
                persona_summary="Synthetic ER6 Mango",
                created_at=FIXED_NOW,
            )
        )
        connection.execute(
            metadata.tables["worlds"].insert().values(
                id="world-er6",
                slug="er6-installed-world",
                owner_user_id="owner-er6",
                name="ER6 Installed World",
                tagline="Synthetic lifecycle evidence",
                setting_description="A synthetic world for installer verification.",
                daily_life_description="No provider call is allowed.",
                genre_tags=["fixture"],
                tone_tags=["calm"],
                timezone="Asia/Seoul",
                language="ko",
                visibility="private",
                join_policy="approval_required",
                status="published",
                definition_version=1,
                row_version=1,
                contract_version="er6-v1",
                contract_hash="e" * 64,
                readiness_status="publish_ready",
                create_idempotency_key="er6-installed-world-create",
                created_at=FIXED_NOW,
                updated_at=FIXED_NOW,
            )
        )
        connection.execute(
            metadata.tables["world_memberships"].insert().values(
                id="membership-er6",
                world_id="world-er6",
                user_id="owner-er6",
                role="owner",
                status="active",
                requested_by_user_id="owner-er6",
                approved_by_user_id="owner-er6",
                joined_at=FIXED_NOW,
                created_at=FIXED_NOW,
                updated_at=FIXED_NOW,
            )
        )
        connection.execute(
            metadata.tables["world_characters"].insert().values(
                id="world-character-er6-mango",
                world_id="world-er6",
                character_id="character-er6-mango",
                membership_id="membership-er6",
                status="active",
                control_mode="autonomous",
                owner_user_id=None,
                autonomous_enabled=False,
                activity_runtime_mode="routine_resident_v1",
                feed_runtime_mode="keyword_search_v1",
                local_profile={"display_name": "ER6 Mango"},
                version=1,
                created_at=FIXED_NOW,
                updated_at=FIXED_NOW,
            )
        )
        # Metadata is enough for a persistence proof.  A usable key is
        # intentionally absent so this artifact can never call a provider.
        connection.execute(
            metadata.tables["llm_credentials"].insert().values(
                id="credential-er6-metadata",
                owner_id="owner-er6",
                character_id="character-er6-mango",
                provider="gemini",
                purpose="agent",
                model="gemini-fixture",
                auth_profile_id="er6-synthetic-metadata",
                label="Synthetic metadata only",
                encrypted_api_key=None,
                key_fingerprint="er6-metadata",
                enabled=False,
                created_at=FIXED_NOW,
                updated_at=FIXED_NOW,
            )
        )
        connection.execute(
            metadata.tables["posts"].insert().values(
                id="post-er6-installed",
                author_character_id="character-er6-mango",
                world_id="world-er6",
                author_world_character_id="world-character-er6-mango",
                post_type="post",
                visibility="public",
                author_name="ER6 Mango",
                title="Installed lifecycle fixture",
                body="Synthetic post preserved across uninstall and reinstall.",
                search_document="installed lifecycle fixture synthetic post",
                created_at=FIXED_NOW,
                updated_at=FIXED_NOW,
            )
        )
    doctor = database.doctor()
    database.checkpoint(truncate=True)
    database.close()

    files = _persistent_files(output_root)
    manifest: dict[str, object] = {
        "schema_version": 1,
        "fixture_id": FIXTURE_ID,
        "synthetic_fixture": True,
        "contains_real_credentials": False,
        "generation": GENERATION,
        "canonical_schema_version": doctor.schema_version,
        "canonical_table_count": doctor.canonical_table_count,
        "expected_ids": {
            "owner": "owner-er6",
            "world": "world-er6",
            "character": "character-er6-mango",
            "world_character": "world-character-er6-mango",
            "credential": "credential-er6-metadata",
            "post": "post-er6-installed",
        },
        "persistent_files": files,
        "app_secret_sha256": files["secrets/app-secret"],
        "excluded_legacy_paths": ["runtime/legacy-owner.lock", "WebView2/Cookies"],
    }
    (output_root / "fixture-manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    return manifest


def main() -> int:
    args = _parser().parse_args()
    manifest = build_fixture(args.output_root, force=args.force)
    print(
        "ER6 LocalAppData lifecycle fixture built: "
        f"files={len(manifest['persistent_files'])} "
        f"generation={manifest['generation']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
