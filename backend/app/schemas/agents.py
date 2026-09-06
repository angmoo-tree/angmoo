from app.domains.local_bot.schemas import AgentLocalConnectionRead

from app.domains.local_bot.schemas import AgentLocalKeyCreateRead

from app.domains.local_bot.schemas import BotCharacterRead

from app.domains.local_bot.schemas import BotMeRead

from app.domains.characters.schemas import AgentImageGenerationSettingUpdate

from app.domains.characters.schemas import AgentImageSeedUpload

from app.domains.characters.schemas import PollinationsImageModel

from app.domains.characters.schemas import AgentImageGenerationSettingRead

from app.domains.characters.schemas import AgentDetailRead

from app.domains.routines.schemas import AgentActionRangeRead

from app.domains.routines.schemas import AgentActivitySettingRead

from app.domains.routines.schemas import AgentActivitySummaryRead

from app.domains.identity.schemas import CredentialRead

from datetime import datetime

from typing import Literal

from app.domains.characters.schemas import AgentDraftImageStyle

from app.domains.characters.schemas import AgentDraftMediaKind

from app.domains.characters.schemas import AgentDraftMediaDelivery

from app.domains.characters.schemas import AgentProfileImageBucket

from app.domains.characters.schemas import AgentCreationDraftCreate

from app.domains.characters.schemas import AgentCreationDraftUpdate

from app.domains.characters.schemas import AgentCreationDraftMediaUpload

from app.domains.characters.schemas import AgentCreationDraftGenerateMediaCreate

from app.domains.characters.schemas import AgentCreationDraftComplete

from app.domains.characters.schemas import AgentProfileMediaGenerateCreate

from app.domains.characters.schemas import AgentProfileImageUsageStatusRead

from app.domains.characters.schemas import AgentProfileImageUsageRead

from app.domains.characters.schemas import AgentCreationDraftMediaResult

from app.domains.characters.schemas import AgentCreationDraftMediaGenerationRead

from app.domains.characters.schemas import AgentProfileMediaGenerationRead

from app.domains.characters.schemas import AgentCreationDraftRead

from app.domains.characters.schemas import AgentPromotionUsageRead

from app.domains.characters.schemas import AgentActivityProfileReadinessRead

from pydantic import BaseModel

from pydantic import ConfigDict

from pydantic import Field

from pydantic import field_validator

from pydantic import model_validator

from app.core.image_generation import IMAGE_MODEL_OPTIONS

from app.core.image_generation import MAX_IMAGES_PER_DAY

from app.providers.registry import AGENT_GOOGLE_MODELS

from app.domains.routines.schemas.runs import AgentActivityLogRead

from app.domains.routines.schemas.runs import AgentSlotRead

from app.domains.routines.schemas.runs import UtcInstantResponseModel

from app.domains.characters.schemas import CharacterRead

from app.domains.characters.schemas import CharacterStateRead

from app.domains.characters.schemas import AgentCreate

from app.domains.characters.schemas import AgentDeleteCreate

from app.domains.characters.schemas import AgentProfileUpdate

from app.domains.characters.schemas import AgentPersonaUpdate

from app.domains.characters.schemas import AgentProfileMediaUpload

from app.domains.characters.schemas import AgentPromotionUsageUpdate

from app.domains.social.schemas.community import PostDetail

from app.domains.media.schemas import validate_profile_media_reference

from app.domains.routines.schemas import AgentActivitySettingUpdate

from app.domains.routines.schemas import AgentFeedCueCreate

from app.domains.routines.schemas import AgentFeedCueRead

from app.domains.routines.schemas.first_greeting import AgentFirstGreetingCreate

from app.api.schemas.first_greeting import AgentFirstGreetingRead

from app.domains.identity.schemas import CredentialUpsert

AgentGoogleModel = Literal[*AGENT_GOOGLE_MODELS]

GoogleGeminiModel = AgentGoogleModel

ImageKeyMode = Literal["service", "user", "disabled"]

WritingRepetitionLevel = Literal["off", "light", "normal", "strong"]

AgentExecutionMode = Literal["llm", "local"]
