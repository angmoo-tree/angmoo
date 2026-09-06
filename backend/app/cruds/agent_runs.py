from app.domains.identity.repository.credentials import get_credential

from app.domains.identity.repository.credentials import get_default_credential

import hashlib

from datetime import UTC

from datetime import datetime

from datetime import timedelta

from typing import Any

from sqlalchemy import func

from sqlalchemy import or_

from sqlalchemy import select

from sqlalchemy.exc import IntegrityError

from sqlalchemy.orm import Session

from app.domains.routines.models.resident import AgentActivitySetting as _model_AgentActivitySetting

from app.domains.routines.models.resident import AgentPublicActionExecution as _model_AgentPublicActionExecution

from app.domains.routines.models.resident import AgentRun as _model_AgentRun

from app.domains.routines.models.resident import AgentSlot as _model_AgentSlot

from app.domains.characters.models import Character as _model_Character

from app.domains.world_characters.models import WorldCharacter as _model_WorldCharacter

from app.runtime.persistence.model_registration import register_models

from app.core import unit_of_work

from app.domains.relationships.constants import RELATIONSHIP_POINT_KINDS

from app.domains.relationships.constants import RELATIONSHIP_POINT_PENDING

from app.domains.relationships.constants import RELATIONSHIP_POINT_SELECTED

from app.domains.relationships.constants import RELATIONSHIP_POINT_CONSUMED

from app.domains.relationships.constants import RELATIONSHIP_POINT_EXPIRED

from app.domains.relationships.constants import RELATIONSHIP_POINT_FAILED

from app.domains.relationships.constants import RELATIONSHIP_POINT_ACTIVE_STATUSES

from app.domains.relationships.utils.points import relationship_point_pair_key

from app.domains.relationships.utils.points import relationship_point_source_signature

from app.domains.relationships.utils.points import relationship_point_chain_id

from app.domains.relationships.utils.points import _relationship_point_payload

from app.domains.relationships.repository.points import count_relationship_points_for_pair_since

from app.domains.relationships.service.points import create_relationship_point

from app.domains.relationships.service.points import expire_relationship_points

from app.domains.relationships.service.points import list_pending_relationship_points

from app.domains.relationships.service.points import mark_relationship_point_selected

from app.domains.relationships.service.points import release_relationship_point_selection

from app.domains.relationships.service.points import mark_relationship_point_consumed

from app.domains.relationships.service.points import mark_relationship_point_replied

from app.domains.relationships.service.points import mark_relationship_point_failed

register_models()
