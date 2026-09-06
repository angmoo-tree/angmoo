from app.domains.local_bot.repository.keys import get_active_local_key

from app.domains.local_bot.repository.keys import get_active_local_key_by_hash

from app.domains.local_bot.repository.keys import get_latest_local_key

from app.domains.local_bot.service.key_records import create_local_key

from app.domains.local_bot.service.key_records import mark_local_key_used

from app.domains.local_bot.service.key_records import revoke_active_local_key

from app.domains.identity.repository.credentials import get_character_credential

from app.domains.identity.service.character_credentials import default_auth_profile_id

from app.domains.identity.service.character_credentials import default_credential_model

from app.domains.identity.service.character_credentials import upsert_credential

from datetime import UTC

from datetime import datetime

from datetime import timedelta

from uuid import uuid4

from sqlalchemy import select

from sqlalchemy.orm import Session



from app.domains.routines.models.resident import AgentActivitySetting as _model_AgentActivitySetting

from app.domains.routines.models.resident import AgentFeedCue as _model_AgentFeedCue

from app.domains.routines.models.resident import AgentSlot as _model_AgentSlot

from app.domains.characters.models import Character as _model_Character

from app.domains.identity.models import User as _model_User

from app.runtime.persistence.model_registration import register_models

from app.core.image_generation import DEFAULT_USER_IMAGE_MODEL

from app.core.image_generation import DEFAULT_MAX_IMAGES_PER_DAY

from app.core import security

from app.core import active_hours

from app.core import unit_of_work

from app.domains.routines.constants import HIDDEN_ACTIVITY_ACTION_TYPES

from app.domains.routines.constants import STATE_SAVE_DEDUPE_WINDOW

from app.domains.routines.service.activity_logs import filter_visible_activity_logs

from app.domains.routines.service.activity_logs import list_recent_activity

from app.domains.routines.service.activity_logs import log_activity

from app.domains.routines.service.activity_settings import get_setting

from app.domains.routines.service.activity_settings import ensure_setting

from app.domains.routines.service.activity_settings import update_setting

from app.domains.routines.repository.slots import get_assigned_slot

register_models()
