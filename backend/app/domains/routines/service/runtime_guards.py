"""Explicit imported-World autonomy admission."""
from sqlalchemy.orm import Session
from app.domains.routines.contracts.activity_management import ActivityCharacter
from app.domains.routines.contracts.activity_presentation import ImportedWorldLockRead


def _ensure_imported_world_runtime_enabled(
    db: Session,
    *,
    character: ActivityCharacter,
    locked: ImportedWorldLockRead,
    execution_mode_error: type[Exception],
) -> None:
    """Keep an imported World inert until its explicit autonomy enable step.

    A normal local character may use the user-initiated Run-now path while
    scheduled autonomy is disabled.  World Package imports have a stricter
    activation contract: their seeded runtime must not enter P5-P7 before the
    user completes setup and explicitly enables autonomy.  Scope the guard to
    the active World when one exists so another, direct-created World owned by
    the same character is not affected.
    """

    if locked(
        db, character_id=character.id
    ):
        raise execution_mode_error(
            "가져온 World는 자율활동을 먼저 켠 뒤 지금 한 번 활동을 실행할 수 있어요."
        )
