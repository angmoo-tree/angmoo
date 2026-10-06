"""Narrow existing admission collaborators shared by saved World scheduling."""
from dataclasses import dataclass
from typing import Callable
from sqlalchemy.orm import Session
from app.domains.routines.contracts.activity_management import ActivityCharacter
from app.domains.routines.contracts.autonomy_management import (
    AutonomyCredential, EffectiveAutonomyCount, ReadinessEvaluator, ResidentAssignment, ProfileBind, ProfileRelease,
)


@dataclass(frozen=True)
class AutonomyAdmissionReferences:
    ensure_not_suspended: Callable[[ActivityCharacter], None]
    ensure_llm_mode: Callable[[ActivityCharacter], None]
    ensure_auto_ticks_available: Callable[[Session], None]
    evaluate_readiness: ReadinessEvaluator
    get_credential: Callable[[Session, str], AutonomyCredential | None]
    count_effective_agents: EffectiveAutonomyCount
    assign_slot: ResidentAssignment
    sync_enabled: Callable[[], bool]
    bind_profile: ProfileBind
    release_profile: ProfileRelease
    reload_secrets: Callable[[], None]
