"""HTTP translation of cooperating World access errors for World and WorldCharacter requests."""
from fastapi import HTTPException, status
from app.domains.worlds import service as world_service


def _raise_world_error(exc: Exception) -> None:
    if isinstance(exc, world_service.WorldNotFoundError):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=exc.reason_code,
        ) from exc
    if isinstance(
        exc,
        (
            world_service.WorldArchivedError,
            world_service.WorldRowVersionConflictError,
        ),
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=exc.reason_code,
        ) from exc
    if isinstance(exc, world_service.WorldDefinitionIncompleteError):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "code": exc.reason_code,
                "readiness": exc.readiness.model_dump(mode="json"),
            },
        ) from exc
    if isinstance(
        exc,
        (
            world_service.WorldDefinitionValidationError,
            world_service.WorldBannerValidationError,
        ),
    ):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=exc.reason_code,
        ) from exc
    if isinstance(
        exc,
        (
            world_service.WorldMembershipRequiredError,
            world_service.WorldCreatorRoleRequiredError,
            world_service.WorldOwnerRoleRequiredError,
        ),
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=exc.reason_code,
        ) from exc
    raise exc
