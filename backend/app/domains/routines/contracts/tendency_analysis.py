"""Same-session owner and profile collaboration for tendency analysis."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Callable, Generic, TypeVar
from sqlalchemy.orm import Session
from app.domains.routines.contracts.activity_management import ActivityOwner, TendencyPersona
from app.domains.routines.contracts.autonomy_management import AutonomyCredential, ProfileBind, ProfileRelease
from app.domains.routines.contracts.manual_activity import ImportedWorldGuard

DetailT = TypeVar("DetailT")

@dataclass(frozen=True)
class TendencyAnalysisWorkflows(Generic[DetailT]):
    get_owned_character: Callable[[Session, ActivityOwner, str], TendencyPersona]
    ensure_mutable: Callable[[ActivityOwner], None]
    ensure_llm_mode: Callable[[TendencyPersona], None]
    ensure_imported_world_runtime_enabled: ImportedWorldGuard
    get_credential: Callable[[Session, str], AutonomyCredential | None]
    bind_profile: ProfileBind
    release_profile: ProfileRelease
    build_detail: Callable[[Session, TendencyPersona], DetailT]
    credential_required_error: type[Exception]
