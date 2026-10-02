"""Authenticated image settings, drafts and private pixel reads."""
import base64
import json
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from app.database import get_db
from app.domains.identity.service.http_auth import get_current_user, require_local_frontend_request
from app.domains.identity.service.demo_access import ensure_demo_user_mutable
from app.domains.media.contracts import InvalidProfileMediaError
from app.domains.media.generation_contracts import ImagePreparationError, ImageSubmissionError
from app.domains.media.setting_schemas import AssetUpload, GenerationSettingsWrite, InterpretationSettingsWrite, InstallationUsageWrite
from app.domains.media.service.interpretation import read_interpretation_settings, write_interpretation_settings

router = APIRouter(tags=["media"])


def runtime(request: Request):
    value = getattr(request.app.state, "media_runtime", None)
    if value is None:
        raise HTTPException(503, detail="image_runtime_unavailable")
    return value


def guarded(call, db):
    try:
        return call()
    except (ImagePreparationError, InvalidProfileMediaError) as exc:
        db.rollback()
        code = str(exc)
        raise HTTPException(409 if "revision_conflict" in code else 422, detail=code) from exc
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, detail="image_record_revision_conflict") from exc


@router.get("/media/catalog")
def catalog(request: Request, user=Depends(get_current_user)):
    return runtime(request).catalog()


@router.get("/media/usage-settings")
def usage(request: Request, db: Session = Depends(get_db), user=Depends(get_current_user)):
    return runtime(request).usage(db, user.id)


@router.put("/media/usage-settings", dependencies=[Depends(require_local_frontend_request)])
def save_usage(data: InstallationUsageWrite, request: Request, db: Session = Depends(get_db), user=Depends(get_current_user)):
    ensure_demo_user_mutable(user)
    guarded(lambda: runtime(request).limits.write(db, data.daily_limit, expected_revision=data.expected_revision), db)
    db.commit()
    return runtime(request).usage(db, user.id)


@router.get("/agents/{character_id}/generation-settings")
def read_generation(character_id: str, request: Request, db: Session = Depends(get_db), user=Depends(get_current_user)):
    value = guarded(lambda: runtime(request).read_generation(db, user, character_id), db)
    db.commit()
    return value


@router.put("/agents/{character_id}/generation-settings", dependencies=[Depends(require_local_frontend_request)])
def save_generation(character_id: str, data: GenerationSettingsWrite, request: Request, db: Session = Depends(get_db), user=Depends(get_current_user)):
    value = guarded(lambda: runtime(request).write_generation(db, user, character_id, data), db)
    db.commit()
    return value


@router.post("/agents/{character_id}/generation-settings/check", dependencies=[Depends(require_local_frontend_request)])
async def check_generation(character_id: str, data: GenerationSettingsWrite, request: Request, db: Session = Depends(get_db), user=Depends(get_current_user)):
    media = runtime(request)
    ensure_demo_user_mutable(user)
    try:
        connection = await media.validate_connection(db, user, character_id, data)
        value = media.write_generation(db, user, character_id, data, validated_connection=connection)
        db.commit()
        return value
    except (ImagePreparationError, ImageSubmissionError, ValueError) as exc:
        db.rollback()
        code = str(exc) if isinstance(exc, (ImagePreparationError, ImageSubmissionError)) else "image_connection_invalid"
        raise HTTPException(409 if "revision_conflict" in code else 422, detail=code) from exc
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, detail="image_record_revision_conflict") from exc


@router.get("/media/interpretation-settings")
def read_interpretation(db: Session = Depends(get_db), user=Depends(get_current_user)):
    return read_interpretation_settings(db, user.id)


@router.put("/media/interpretation-settings", dependencies=[Depends(require_local_frontend_request)])
def save_interpretation(data: InterpretationSettingsWrite, db: Session = Depends(get_db), user=Depends(get_current_user)):
    ensure_demo_user_mutable(user)
    value = guarded(lambda: write_interpretation_settings(db, user.id, data), db)
    db.commit()
    return value


@router.post("/media/assets", dependencies=[Depends(require_local_frontend_request)], status_code=201)
def upload(data: AssetUpload, request: Request, db: Session = Depends(get_db), user=Depends(get_current_user)):
    ensure_demo_user_mutable(user)
    try:
        content = base64.b64decode(data.data_base64, validate=True)
    except ValueError as exc:
        raise HTTPException(422, detail="asset_base64_invalid") from exc
    row = guarded(lambda: runtime(request).assets.upload(db, owner_id=user.id, scope_kind=data.scope_kind,
        scope_id=data.scope_id, content_type=data.content_type, content=content), db)
    db.commit()
    return {"id": row.id, "revision": row.revision, "content_type": row.content_type,
        "width": row.width, "height": row.height, "byte_size": row.byte_size, "state": row.state,
        "url": f"/api/v1/media/assets/{row.id}/content"}


@router.get("/media/assets/{asset_id}/content")
def content(asset_id: str, request: Request, db: Session = Depends(get_db), user=Depends(get_current_user)):
    row, pixels = guarded(lambda: runtime(request).assets.read(db, owner_id=user.id, asset_id=asset_id), db)
    return Response(pixels, media_type=row.content_type, headers={"Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff"})


@router.get("/media/assets/{asset_id}/preflight")
def preflight(asset_id: str, request: Request, db: Session = Depends(get_db), user=Depends(get_current_user)):
    return guarded(lambda: runtime(request).interpretation.preflight(db, user.id, asset_id), db)


@router.delete("/media/assets/{asset_id}", dependencies=[Depends(require_local_frontend_request)], status_code=204)
def delete_draft(asset_id: str, request: Request, db: Session = Depends(get_db), user=Depends(get_current_user)):
    ensure_demo_user_mutable(user)
    assets = runtime(request).assets
    row = guarded(lambda: assets.owned(db, owner_id=user.id, asset_id=asset_id), db)
    if row.state != "draft":
        raise HTTPException(409, detail="attached_asset_cannot_be_deleted_as_draft")
    row.state = "deleted"
    db.commit()
    assets.path(row).unlink(missing_ok=True)


@router.get("/media/comfy-samples/{kind}")
def comfy_sample(kind: str, user=Depends(get_current_user)):
    if kind not in {"text", "reference"}:
        raise HTTPException(404)
    return json.loads((Path(__file__).parent / "samples" / f"comfy-{kind}.json").read_text("utf-8"))


@router.get("/media/worlds/{world_id}/posts/{post_id}/image-generation")
def read_job(world_id: str, post_id: str, request: Request, db: Session = Depends(get_db), user=Depends(get_current_user)):
    media = runtime(request)
    guarded(lambda: media.authorize_post_world(db, user.id, world_id, post_id), db)
    return guarded(lambda: media.worker.view_for_post(db, user.id, post_id), db)


@router.post("/media/worlds/{world_id}/posts/{post_id}/image-generation/{action}", dependencies=[Depends(require_local_frontend_request)])
def change_job(world_id: str, post_id: str, action: str, request: Request, db: Session = Depends(get_db), user=Depends(get_current_user)):
    ensure_demo_user_mutable(user)
    media = runtime(request)
    guarded(lambda: media.authorize_post_world(db, user.id, world_id, post_id), db)
    if action == "cancel":
        value = guarded(lambda: media.worker.cancel(db, user.id, post_id), db)
    elif action == "retry":
        value = guarded(lambda: media.worker.retry(db, user.id, post_id, media.quota_day()), db)
    else:
        raise HTTPException(404)
    db.commit()
    return value
