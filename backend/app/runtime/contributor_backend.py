"""Explicit contributor entrypoint for the canonical embedded runtime.

This command deliberately takes a data root argument instead of inferring the
installed product root or selecting providers from process environment values.
"""

from __future__ import annotations

import argparse
import importlib
import json
import os
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


def _register_canonical_models() -> None:
    """Load the composition root before the SQLite baseline is inspected.

    Domain-owned SQLAlchemy models are registered as the public API routers
    are imported.  A diagnostics-only process must perform the same import as
    the serving path; otherwise a fresh checkout would materialize only the
    small set of models imported by the runtime module itself.
    """

    importlib.import_module("app.public_main")


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
    parser.add_argument(
        "--reload",
        action="store_true",
        help="Reload the contributor backend when Python source changes",
    )
    parser.add_argument(
        "--diagnostics",
        action="store_true",
        help="Print one privacy-safe embedded runtime status document",
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
    _register_canonical_models()
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


def create_contributor_runtime_app_from_environment():
    """Create the reload child from fail-closed contributor inputs.

    The environment carries lifecycle arguments across Uvicorn's reloader
    boundary. It does not select persistence, graph, or component providers;
    those remain fixed by ``CONTRIBUTOR_EMBEDDED``.
    """

    raw_data_root = os.environ.get("ANGMOO_CONTRIBUTOR_DATA_ROOT", "").strip()
    if not raw_data_root:
        raise RuntimeError("contributor_data_root_required")
    frontend_origin = os.environ.get("ANGMOO_FRONTEND_ORIGIN", "").strip()
    if not frontend_origin:
        raise RuntimeError("contributor_frontend_origin_required")
    return create_contributor_runtime_app(
        data_root=Path(raw_data_root),
        frontend_origin=frontend_origin,
    )


def contributor_runtime_status_payload(
    *,
    data_root: Path,
    frontend_origin: str = "http://127.0.0.1:3000",
) -> dict[str, object]:
    """Read contributor status through the same typed composition as the API.

    The launcher invokes this inside the backend container. It intentionally
    accepts only lifecycle paths and never lets environment variables select
    persistence, graph, or worker providers.
    """

    _register_canonical_models()

    from app.core.redaction import sanitize_support_bundle_metadata
    from app.domains.runtime.public import (
        ReadApplicationRuntimeStatus,
        SqlAlchemyApplicationRuntimeProbe,
        runtime_status_read,
    )
    from app.runtime.configuration import compose_runtime

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
    composition = compose_runtime(runtime_config)
    try:
        with composition.session_factory() as db:
            status = ReadApplicationRuntimeStatus(
                SqlAlchemyApplicationRuntimeProbe(
                    db,
                    config=composition.settings,
                )
            ).execute()
            payload = runtime_status_read(
                status,
                runtime_profile=runtime_config.profile.value,
                canonical_generation=runtime_config.generation,
                persistence_provider="sqlite",
                graph_provider="ladybug",
            ).model_dump(mode="json")
    finally:
        composition.dispose()
    return sanitize_support_bundle_metadata(payload)


def main() -> None:
    args = _parse_args()
    if args.diagnostics:
        payload = contributor_runtime_status_payload(
            data_root=args.data_root,
            frontend_origin=args.frontend_origin,
        )
        print(json.dumps(payload, ensure_ascii=False, separators=(",", ":")))
        return
    if args.reload:
        os.environ["ANGMOO_CONTRIBUTOR_DATA_ROOT"] = str(
            args.data_root.resolve()
        )
        os.environ["ANGMOO_FRONTEND_ORIGIN"] = args.frontend_origin
        uvicorn.run(
            "app.runtime.contributor_backend:"
            "create_contributor_runtime_app_from_environment",
            factory=True,
            host=args.host,
            port=args.port,
            reload=True,
            reload_dirs=[str(Path(__file__).resolve().parents[2])],
        )
        return
    app = create_contributor_runtime_app(
        data_root=args.data_root,
        frontend_origin=args.frontend_origin,
    )
    uvicorn.run(app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()


__all__ = [
    "CONTRIBUTOR_GENERATION",
    "create_contributor_runtime_app",
    "create_contributor_runtime_app_from_environment",
    "contributor_runtime_status_payload",
    "main",
]
