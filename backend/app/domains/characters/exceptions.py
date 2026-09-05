from datetime import datetime
from app.domains.characters import schemas

"""Stable Character handle validation and uniqueness errors."""
class CharacterHandleConflictError(Exception):
    pass


class InvalidCharacterHandleError(Exception):
    pass


class AgentServiceError(Exception):
    pass

class AgentNotFoundError(AgentServiceError):
    pass

class AgentHandleConflictError(AgentServiceError):
    pass

class AgentHandleInvalidError(AgentServiceError):
    pass

class AgentProfileNameInvalidError(AgentServiceError):
    pass

class InvalidProfileMediaError(AgentServiceError):
    pass

class PromptInjectionDetectedError(AgentServiceError):
    pass

class AgentExecutionModeError(AgentServiceError):
    pass

class AgentSuspendedError(AgentServiceError):
    pass


class AgentCreationDraftError(Exception):
    pass

class AgentCreationDraftNotFoundError(AgentCreationDraftError):
    pass

class AgentCreationDraftExpiredError(AgentCreationDraftNotFoundError):
    pass

class AgentCreationDraftCooldownError(AgentCreationDraftError):
    def __init__(self, available_at: datetime) -> None:
        super().__init__("Please wait before trying again")
        self.available_at = available_at

class AgentCreationDraftValidationError(AgentCreationDraftError):
    pass

class AgentCreationDraftHandleConflictError(AgentCreationDraftValidationError):
    pass

class AgentCreationDraftMediaError(AgentCreationDraftError):
    pass

class AgentProfileImageQuotaExceededError(AgentCreationDraftMediaError):
    def __init__(self, usage_status: schemas.AgentProfileImageUsageStatusRead) -> None:
        super().__init__("profile_image_daily_limit_exceeded")
        self.usage_status = usage_status

class AgentProfileImageCandidateNotFoundError(AgentCreationDraftError):
    pass

class AgentProfileImageCandidateExpiredError(AgentProfileImageCandidateNotFoundError):
    pass

class AgentPrivateMediaNotFoundError(AgentCreationDraftError):
    pass

class AgentCreationDraftParseError(AgentCreationDraftError):
    pass


class AgentActiveHoursInvalidError(AgentServiceError):
    pass


class CredentialRequiredError(AgentServiceError):
    pass


class CredentialSyncError(AgentServiceError):
    pass


class CharacterStateNotFoundError(AgentServiceError):
    pass
