from app.domains.routines.schemas.first_greeting import AgentFirstGreetingCreate
from app.api.schemas.first_greeting import AgentFirstGreetingRead
from app.domains.local_bot.schemas import AgentLocalConnectionRead, AgentLocalKeyCreateRead, BotCharacterRead, BotMeRead
from app.domains.characters.schemas import AgentImageGenerationSettingUpdate, AgentImageSeedUpload, PollinationsImageModel
from app.domains.characters.schemas import (
    AgentImageGenerationSettingRead,
    AgentDetailRead,
)

from app.domains.routines.schemas import (
    AgentActionRangeRead,
    AgentActivitySettingRead,
    AgentActivitySummaryRead,
)

from app.domains.identity.schemas import (
    CredentialRead,
    CredentialUpsert,
)

from datetime import datetime
from typing import Literal

from app.domains.characters.schemas import (
    AgentDraftImageStyle,
    AgentDraftMediaKind,
    AgentDraftMediaDelivery,
    AgentProfileImageBucket,
    AgentCreationDraftCreate,
    AgentCreationDraftUpdate,
    AgentCreationDraftMediaUpload,
    AgentCreationDraftGenerateMediaCreate,
    AgentCreationDraftComplete,
    AgentProfileMediaGenerateCreate,
    AgentProfileImageUsageStatusRead,
    AgentProfileImageUsageRead,
    AgentCreationDraftMediaResult,
    AgentCreationDraftMediaGenerationRead,
    AgentProfileMediaGenerationRead,
    AgentCreationDraftRead,
    AgentPromotionUsageRead,
)

from app.domains.characters.schemas import AgentActivityProfileReadinessRead

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.core.image_generation import IMAGE_MODEL_OPTIONS, MAX_IMAGES_PER_DAY
from app.providers.registry import AGENT_GOOGLE_MODELS
from app.domains.routines.schemas.runs import (
    AgentActivityLogRead,
    AgentSlotRead,
    UtcInstantResponseModel,
)
from app.schemas.characters import CharacterRead, CharacterStateRead
from app.domains.characters.schemas import (
    AgentCreate,
    AgentDeleteCreate,
    AgentProfileUpdate,
    AgentPersonaUpdate,
    AgentProfileMediaUpload,
    AgentPromotionUsageUpdate,
)
from app.domains.social.schemas.community import PostDetail
from app.schemas.media_security import validate_profile_media_reference


AgentGoogleModel = Literal[*AGENT_GOOGLE_MODELS]
GoogleGeminiModel = AgentGoogleModel
ImageKeyMode = Literal["service", "user", "disabled"]
WritingRepetitionLevel = Literal["off", "light", "normal", "strong"]
AgentExecutionMode = Literal["llm", "local"]





































from app.domains.routines.schemas import AgentActivitySettingUpdate, AgentFeedCueCreate, AgentFeedCueRead
