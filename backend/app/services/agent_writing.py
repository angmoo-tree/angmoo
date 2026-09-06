"""Temporary existing Memory action persistence until the signed B7 merge."""

from app.domains.memory.service.daypart import record_action_memory as _record_daypart_action_memory

from app.runtime.social.agent_tools import agent_tool_actions

from app.runtime.social import agent_tool_authorization as social_tool_authorization

from app.domains.social.service.agent_tool_authorization import _agent_tool_lookup_session_key

from app.domains.social.service import resident_affordances

from datetime import datetime

from typing import Any

from sqlalchemy.orm import Session

from app.domains.routines.models.resident import AgentActivitySetting as _model_AgentActivitySetting

from app.domains.routines.models.resident import AgentRun as _model_AgentRun

from app.domains.characters.models import Character as _model_Character

from app.domains.characters.models import CharacterState as _model_CharacterState

from app.domains.identity.models import LlmCredential as _model_LlmCredential

from app.runtime.persistence.model_registration import register_models

from app.domains.character_lore.service import presentation as lore_presentation

from app.domains.character_lore.contracts import LoreRetrievalResult

from app.runtime.character_lore import build_lore_workflows

from app.domains.memory.models.daypart import AgentDaypartMemoryEvent

register_models()
