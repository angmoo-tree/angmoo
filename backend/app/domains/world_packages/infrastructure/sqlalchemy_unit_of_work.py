"""SQLite commit owner for a complete package seed transaction."""

from __future__ import annotations

import time
from collections.abc import Callable

from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import Session

from app.domains.world_packages.domain.seed import (
    WorldPackageDestinationSeedRequest,
    WorldPackageDestinationSeedResult,
    resolve_world_package_import_replay,
)
from app.domains.world_packages.infrastructure.sqlalchemy_destination_seed import (
    SqlAlchemyWorldPackageDestinationSeed,
)
from app.domains.world_packages.infrastructure.sqlalchemy_registry import (
    SqlAlchemyWorldPackageRegistry,
)


class SqlAlchemyWorldPackageSeedUnitOfWork:
    """Own one commit and bounded SQLite idempotency conflict recovery."""

    def __init__(
        self,
        session_factory: Callable[[], Session],
        *,
        max_attempts: int = 4,
    ) -> None:
        if max_attempts < 1:
            raise ValueError("max_attempts must be positive")
        self._session_factory = session_factory
        self._max_attempts = max_attempts

    def execute(
        self, request: WorldPackageDestinationSeedRequest
    ) -> WorldPackageDestinationSeedResult:
        last_error: IntegrityError | OperationalError | None = None
        for attempt in range(1, self._max_attempts + 1):
            with self._session_factory() as db:
                try:
                    result = SqlAlchemyWorldPackageDestinationSeed(db).seed(request)
                    db.commit()
                    return result
                except (IntegrityError, OperationalError) as exc:
                    db.rollback()
                    last_error = exc

            with self._session_factory() as observer:
                replay = SqlAlchemyWorldPackageRegistry(observer).find_import(
                    local_owner_id=request.local_owner_id,
                    idempotency_key=request.idempotency_key,
                )
                if replay is not None:
                    return resolve_world_package_import_replay(request, replay)
            if attempt < self._max_attempts:
                time.sleep(0.05 * attempt)

        assert last_error is not None
        raise last_error


__all__ = ["SqlAlchemyWorldPackageSeedUnitOfWork"]
