"""Explicit contributor entrypoint for the canonical embedded runtime.

This command deliberately takes a data root argument instead of inferring the
installed product root or selecting providers from process environment values.
"""

from __future__ import annotations

import argparse
from pathlib import Path
import secrets

import uvicorn

from app.runtime.configuration import (
    RuntimeProfile,
    build_embedded_runtime_config,
    initialize_local_installation_identity,
)
from app.runtime.persistence.sqlite_database import (
    SqliteCanonicalDatabase,
    SqliteCanonicalSettings,
)
from app.runtime.persistence.runtime_data_path import StaticRuntimeDataPath


CONTRIBUTOR_GENERATION = "contributor-v1"


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run Angmoo with the contributor embedded profile",
    )
    parser.add_argument(
        "--data-root",
        type=Path,
        required=True,
        help="Explicit development-only SQLite/LadybugDB data root",
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument(
        "--frontend-origin",
        default="http://127.0.0.1:3000",
    )
    return parser.parse_args()


def _prepare_contributor_data_root(data_root: Path) -> None:
    data_root = data_root.resolve()
    secret_path = data_root / "secrets" / "app-secret"
    if not secret_path.is_file():
        canonical = data_root / "canonical"
        if canonical.exists() and any(canonical.rglob("*")):
            raise RuntimeError("app_secret_missing_for_existing_data")
        secret_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = secret_path.with_suffix(".tmp")
        temporary.write_text(
            secrets.token_urlsafe(48) + "\n",
            encoding="utf-8",
        )
        temporary.replace(secret_path)

    database = SqliteCanonicalDatabase(
        StaticRuntimeDataPath(data_root),
        settings=SqliteCanonicalSettings(generation=CONTRIBUTOR_GENERATION),
    )
    database.open()
    database.close()


def create_contributor_runtime_app(
    *,
    data_root: Path,
    frontend_origin: str = "http://127.0.0.1:3000",
):
    # Import the composition root before materializing the SQLite baseline so
    # every canonical SQLAlchemy model is registered in Base.metadata. This is
    # the same fail-closed ordering used by the packaged desktop sidecar.
    from app.public_main import create_app

    data_root = data_root.resolve()
    _prepare_contributor_data_root(data_root)
    runtime_config = build_embedded_runtime_config(
        profile=RuntimeProfile.CONTRIBUTOR_EMBEDDED,
        data_root=data_root,
        runtime_root=data_root / "runtime",
        generation=CONTRIBUTOR_GENERATION,
        desktop_launch_token="",
        desktop_allowed_origin=frontend_origin,
    )
    app = create_app(runtime_config=runtime_config)
    initialize_local_installation_identity(
        app.state.runtime_composition.session_factory
    )
    return app


def main() -> None:
    args = _parse_args()
    app = create_contributor_runtime_app(
        data_root=args.data_root,
        frontend_origin=args.frontend_origin,
    )
    uvicorn.run(app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
