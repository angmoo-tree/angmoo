from app.domains.memory.service.daypart import purge_expired_events as _purge_expired_daypart_memory_events

from app.domains.memory.service.daypart import event_exists as _daypart_memory_event_exists

from app.domains.memory.service.daypart import record_memory_event as _record_daypart_memory_event

from app.runtime.social import feed_history as resident_feed_history

from app.domains.routines.service import feed_history_values

from app.domains.social.service import resident_affordances

from app.domains.memory.service.daypart_observations import filter_daypart_duplicate_feed_interest as _filter_daypart_duplicate_feed_interest

from app.domains.memory.service.daypart_observations import filter_daypart_duplicate_inbox_candidates as _filter_daypart_duplicate_inbox_candidates

from app.domains.memory.service import daypart_observations

from app.domains.memory.contracts.daypart import DaypartObservationReferences

import logging

from datetime import UTC

from datetime import date

from datetime import datetime

from datetime import timedelta

from typing import Any

from sqlalchemy import delete

from sqlalchemy import select

from sqlalchemy.orm import Session



from app.domains.routines.models.resident import AgentActivityLog as _model_AgentActivityLog

from app.domains.routines.models.resident import AgentActivitySetting as _model_AgentActivitySetting

from app.domains.routines.models.resident import AgentFeedCue as _model_AgentFeedCue

from app.domains.routines.models.resident import AgentRun as _model_AgentRun

from app.domains.routines.models.resident import AgentSlot as _model_AgentSlot

from app.domains.characters.models import Character as _model_Character

from app.domains.characters.models import CharacterState as _model_CharacterState

from app.domains.identity.models import LlmCredential as _model_LlmCredential

from app.domains.social.models.posts import Notification as _model_Notification

from app.domains.social.models.posts import Post as _model_Post

from app.domains.social.models.posts import PostLike as _model_PostLike

from app.domains.social.models.posts import PostRepost as _model_PostRepost

from app.domains.social.models.posts import ProfileFollow as _model_ProfileFollow

from app.runtime.persistence.model_registration import register_models

from app.config import settings



from app.runtime.routines import activity_policy as agent_activity_policy

from app.domains.routines.service.action_briefs import is_feed_scan_community_theme_brief



from app.core.context_text import neutralize_context_text

from app.runtime.resident.context_references import SqlAlchemyResidentActionReferences

from app.domains.routines.service.action_candidates import _profile_display_name_for_action_menu

from app.domains.routines.service.action_admission import _profile_following_status

from app.domains.social.repository.resident_context import _has_character_like

from app.domains.social.repository.resident_context import _has_character_repost

from app.domains.social.repository.resident_context import _has_character_replied_to_thread

from app.domains.social.repository.resident_context import _is_direct_reply_to_character_post_for_action_gate

from app.domains.routines.constants import GEMINI_FREE_FEED_ACTION_MAX

from app.domains.routines.constants import GEMINI_FREE_FEED_CANDIDATE_MAX

from app.domains.routines.constants import GEMINI_FREE_INBOX_ACTION_MAX

from app.domains.routines.constants import GEMINI_FREE_INBOX_CANDIDATE_MAX

from app.domains.routines.service.action_candidates import _profile_target_parts

from app.domains.routines.constants import GEMINI_FREE_POLICY_ID

from app.domains.routines.utils.context_text import _clip_text

register_models()

logger = logging.getLogger(__name__)

GEMINI_FREE_CREATE_POST_MAX = 1

COMPLETE_TICK_ACTION_TYPES = (
    "create_post",
    "reply",
    "like",
    "repost",
    "follow",
    "unfollow",
    "observe",
)







