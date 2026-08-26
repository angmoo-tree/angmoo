"""SQLite commit owner for digest-bound, all-or-nothing package import."""

from __future__ import annotations

import time
from collections.abc import Callable

from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import Session

from app.core.ids import uuid7_string
from app.domains.characters.public import Character
from app.domains.device_home.public import get_device_home_world
from app.domains.world_characters.public import WorldCharacter
from app.domains.world_packages.domain.errors import (
    WorldPackageContractError,
    WorldPackageReasonCode,
)
from app.domains.world_packages.domain.import_commit import (
    WorldPackageImportCommitRequest,
    WorldPackageImportCommitResult,
)
from app.domains.world_packages.domain.seed import (
    WorldPackageDestinationSeedRequest,
)
from app.domains.world_packages.infrastructure.filesystem_import_media import (
    FilesystemWorldPackageImportMedia,
)
from app.domains.world_packages.infrastructure.sqlalchemy_destination_seed import (
    SqlAlchemyWorldPackageDestinationSeed,
)
from app.domains.world_packages.infrastructure.sqlalchemy_preview_probe import (
    SqlAlchemyWorldPackagePreviewProbe,
)
from app.domains.world_packages.infrastructure.sqlalchemy_registry import (
    SqlAlchemyWorldPackageRegistry,
)
from app.domains.worlds.public import (
    WORLD_CONTRACT_VERSION,
    World,
    WorldMembership,
)


class SqlAlchemyWorldPackageImportCommitter:
    """Serialize imports with BEGIN IMMEDIATE and one canonical commit."""

    def __init__(
        self,
        session_factory: Callable[[], Session],
        *,
        media: FilesystemWorldPackageImportMedia,
        max_attempts: int = 4,
    ) -> None:
        if max_attempts < 1:
            raise ValueError("max_attempts must be positive")
        self._session_factory = session_factory
        self._media = media
        self._max_attempts = max_attempts

    def find_replay(
        self,
        *,
        local_owner_id: str,
        idempotency_key: str,
        expected_content_digest: str,
    ) -> WorldPackageImportCommitResult | None:
        with self._session_factory() as db:
            record = SqlAlchemyWorldPackageRegistry(db).find_import(
                local_owner_id=local_owner_id,
                idempotency_key=idempotency_key,
            )
            if record is None:
                return None
            if record.content_digest != expected_content_digest:
                raise WorldPackageContractError(
                    WorldPackageReasonCode.COMMIT_CONFLICT
                )
            return self._result_from_record(db, record, replayed=True)

    def execute(
        self, request: WorldPackageImportCommitRequest
    ) -> WorldPackageImportCommitResult:
        self._validate_current_contract(request)
        import_id = uuid7_string()
        last_error: IntegrityError | OperationalError | None = None
        for attempt in range(1, self._max_attempts + 1):
            promoted = False
            with self._session_factory() as db:
                try:
                    db.execute(text("BEGIN IMMEDIATE"))
                    registry = SqlAlchemyWorldPackageRegistry(db)
                    replay = registry.find_import(
                        local_owner_id=request.local_owner_id,
                        idempotency_key=request.idempotency_key,
                    )
                    if replay is not None:
                        if replay.content_digest != request.package.manifest.content_digest:
                            raise WorldPackageContractError(
                                WorldPackageReasonCode.COMMIT_CONFLICT
                            )
                        db.rollback()
                        return self._result_from_record(
                            db, replay, replayed=True
                        )

                    assessment = SqlAlchemyWorldPackagePreviewProbe(db).assess(
                        local_owner_id=request.local_owner_id,
                        package=request.package,
                    )
                    self._validate_approved_assessment(request, assessment)
                    imported_assets = self._media.prepare(
                        import_id=import_id,
                        metadata=request.package.normalized_assets,
                        payloads=request.package.normalized_asset_payloads,
                    )
                    seed_result = SqlAlchemyWorldPackageDestinationSeed(db).seed(
                        WorldPackageDestinationSeedRequest(
                            local_owner_id=request.local_owner_id,
                            idempotency_key=request.idempotency_key,
                            package_id=str(request.package.manifest.package_id),
                            package_version=(
                                request.package.manifest.package_version
                            ),
                            content_digest=(
                                request.package.manifest.content_digest
                            ),
                            trust_state=assessment.trust_state.value,
                            license_expression=(
                                request.package.manifest.license.expression
                            ),
                            world=request.package.world,
                            characters=tuple(
                                request.package.characters.characters
                            ),
                            world_characters=tuple(
                                request.package.world_characters.characters
                            ),
                            import_id=import_id,
                            collision_plan=assessment.collision_plan,
                            imported_assets=imported_assets,
                        )
                    )
                    self._validate_seeded_rows(
                        db,
                        request=request,
                        imported_world_id=seed_result.imported_world_id,
                    )
                    self._media.promote(import_id=import_id)
                    promoted = True
                    db.commit()
                except (IntegrityError, OperationalError) as exc:
                    db.rollback()
                    if promoted:
                        committed = self._result_if_commit_landed(
                            request=request,
                            import_id=import_id,
                        )
                        if committed is not None:
                            return committed
                    self._media.rollback(import_id=import_id)
                    last_error = exc
                except WorldPackageContractError:
                    db.rollback()
                    self._media.rollback(import_id=import_id)
                    raise
                except Exception as exc:
                    db.rollback()
                    if promoted:
                        committed = self._result_if_commit_landed(
                            request=request,
                            import_id=import_id,
                        )
                        if committed is not None:
                            return committed
                    self._media.rollback(import_id=import_id)
                    raise WorldPackageContractError(
                        WorldPackageReasonCode.COMMIT_FAILED
                    ) from exc
                except BaseException:
                    db.rollback()
                    self._media.rollback(import_id=import_id)
                    raise
                else:
                    try:
                        self._media.mark_committed(import_id=import_id)
                    except BaseException:
                        self.recover_media()
                    with self._session_factory() as observer:
                        record = SqlAlchemyWorldPackageRegistry(observer).find_import(
                            local_owner_id=request.local_owner_id,
                            idempotency_key=request.idempotency_key,
                        )
                        if record is None:
                            raise WorldPackageContractError(
                                WorldPackageReasonCode.COMMIT_FAILED
                            )
                        return self._result_from_record(
                            observer, record, replayed=False
                        )
            if attempt < self._max_attempts:
                time.sleep(0.05 * attempt)

        assert last_error is not None
        raise last_error

    def recover_media(self) -> None:
        def import_exists(import_id: str) -> bool:
            with self._session_factory() as db:
                return SqlAlchemyWorldPackageRegistry(db).import_exists(
                    import_id=import_id
                )

        self._media.recover(import_exists=import_exists)

    def _import_exists(self, *, import_id: str) -> bool:
        with self._session_factory() as db:
            return SqlAlchemyWorldPackageRegistry(db).import_exists(
                import_id=import_id
            )

    def _result_if_commit_landed(
        self,
        *,
        request: WorldPackageImportCommitRequest,
        import_id: str,
    ) -> WorldPackageImportCommitResult | None:
        if not self._import_exists(import_id=import_id):
            return None
        self.recover_media()
        with self._session_factory() as observer:
            record = SqlAlchemyWorldPackageRegistry(observer).find_import(
                local_owner_id=request.local_owner_id,
                idempotency_key=request.idempotency_key,
            )
            if record is None or record.import_id != import_id:
                raise WorldPackageContractError(
                    WorldPackageReasonCode.COMMIT_FAILED
                )
            return self._result_from_record(
                observer,
                record,
                replayed=False,
            )

    @staticmethod
    def _validate_current_contract(
        request: WorldPackageImportCommitRequest,
    ) -> None:
        package = request.package
        if len(package.world.banner_alt_text) > 160 or any(
            len(item.display_name) > 80
            for item in package.characters.characters
        ):
            raise WorldPackageContractError(
                WorldPackageReasonCode.CONTRACT_UNSUPPORTED
            )
        normalized_digests = [
            item.normalized_sha256 for item in package.normalized_assets
        ]
        if len(normalized_digests) != len(set(normalized_digests)):
            raise WorldPackageContractError(
                WorldPackageReasonCode.INTEGRITY_MISMATCH
            )

    @staticmethod
    def _validate_approved_assessment(request, assessment) -> None:
        preview = request.approved_preview
        if (
            assessment.trust_state is not preview.trust_state
            or assessment.collision_plan != preview.collision_plan
        ):
            raise WorldPackageContractError(
                WorldPackageReasonCode.PREVIEW_CHANGED
            )
        if not assessment.collision_plan.commit_allowed_by_default:
            if request.duplicate_strategy != "independent_copy":
                raise WorldPackageContractError(
                    WorldPackageReasonCode.DUPLICATE
                )

    @staticmethod
    def _validate_seeded_rows(
        db: Session,
        *,
        request: WorldPackageImportCommitRequest,
        imported_world_id: str,
    ) -> None:
        world = db.get(World, imported_world_id)
        if (
            world is None
            or world.status != "published"
            or world.visibility != "unlisted"
            or world.readiness_status != "publish_ready"
            or world.contract_version != WORLD_CONTRACT_VERSION
            or world.contract_hash == "0" * 64
            or world.slug
            != request.approved_preview.collision_plan.planned_world_slug
        ):
            raise WorldPackageContractError(
                WorldPackageReasonCode.COMMIT_FAILED
            )
        memberships = int(
            db.scalar(
                select(func.count())
                .select_from(WorldMembership)
                .where(WorldMembership.world_id == imported_world_id)
            )
            or 0
        )
        world_characters = tuple(
            db.scalars(
                select(WorldCharacter).where(
                    WorldCharacter.world_id == imported_world_id
                )
            )
        )
        character_ids = {item.character_id for item in world_characters}
        characters = tuple(
            db.scalars(select(Character).where(Character.id.in_(character_ids)))
        )
        expected_handles = {
            item.planned_handle
            for item in request.approved_preview.collision_plan.characters
        }
        if (
            memberships != 1
            or len(world_characters)
            != len(request.package.world_characters.characters)
            or len(characters) != len(request.package.characters.characters)
            or {item.handle for item in characters} != expected_handles
            or any(
                item.control_mode != "autonomous"
                or item.owner_user_id is not None
                or item.autonomous_enabled
                for item in world_characters
            )
        ):
            raise WorldPackageContractError(
                WorldPackageReasonCode.COMMIT_FAILED
            )
        outbox_count = int(
            db.execute(
                text(
                    "SELECT COUNT(*) FROM graph_projection_outbox "
                    "WHERE world_id = :world_id"
                ),
                {"world_id": imported_world_id},
            ).scalar_one()
        )
        if outbox_count != 0:
            raise WorldPackageContractError(
                WorldPackageReasonCode.COMMIT_FAILED
            )
        home = get_device_home_world(
            db,
            owner_user_id=request.local_owner_id,
            world_id=imported_world_id,
        )
        if home is None or not home.launchable:
            raise WorldPackageContractError(
                WorldPackageReasonCode.COMMIT_FAILED
            )

    @staticmethod
    def _result_from_record(
        db: Session, record, *, replayed: bool
    ) -> WorldPackageImportCommitResult:
        home = get_device_home_world(
            db,
            owner_user_id=record.local_owner_id,
            world_id=record.imported_world_id,
        )
        if home is None or not home.launchable:
            raise WorldPackageContractError(
                WorldPackageReasonCode.COMMIT_FAILED
            )
        return WorldPackageImportCommitResult(
            import_id=record.import_id,
            imported_world_id=record.imported_world_id,
            device_home_world_id=home.world_id,
            replayed=replayed,
        )


__all__ = ["SqlAlchemyWorldPackageImportCommitter"]
