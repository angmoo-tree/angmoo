from datetime import datetime


class AuthError(Exception):
    pass


class EmailAlreadyExistsError(AuthError):
    pass


class InvalidCredentialsError(AuthError):
    pass


class LoginRateLimitedError(AuthError):
    def __init__(self, retry_after_seconds: int) -> None:
        self.retry_after_seconds = retry_after_seconds
        super().__init__("Login temporarily rate limited")


class GoogleLoginRateLimitedError(AuthError):
    def __init__(self, retry_after_seconds: int) -> None:
        self.retry_after_seconds = retry_after_seconds
        super().__init__("Google login temporarily rate limited")


class GoogleAuthConfigError(AuthError):
    pass


class InvalidGoogleCredentialError(AuthError):
    pass


class GoogleEmailAlreadyExistsError(AuthError):
    pass


class GoogleLinkEmailMismatchError(AuthError):
    pass


class GoogleSubAlreadyLinkedError(AuthError):
    pass


class InvalidGoogleSignupTokenError(AuthError):
    pass


class PolicyAgreementRequiredError(AuthError):
    pass


class DisplayNameAlreadyExistsError(AuthError):
    pass


class DisplayNameInvalidError(AuthError):
    pass


class ReservedDisplayNameError(AuthError):
    pass


class DisplayNameBlockedError(AuthError):
    pass


class DisplayNameCooldownError(AuthError):
    def __init__(self, available_at: datetime) -> None:
        self.available_at = available_at
        super().__init__("Display name change is on cooldown")


class AccountDeletionConfirmationError(AuthError):
    pass


class AccountDeletionBusyError(AuthError):
    pass


class AccountDeletionCredentialSyncError(AuthError):
    pass


class AccountDeletionMediaCleanupError(AuthError):
    pass


class LocalIdentityError(Exception):
    code = "local_identity_error"


class LocalOwnerUnclaimedError(LocalIdentityError):
    code = "local_owner_unclaimed"


class BootstrapClosedError(LocalIdentityError):
    code = "bootstrap_closed"


class BootstrapChallengeInvalidError(LocalIdentityError):
    code = "bootstrap_challenge_invalid"


class BootstrapRaceLostError(LocalIdentityError):
    code = "bootstrap_race_lost"


class LocalOwnerCandidateInvalidError(LocalIdentityError):
    code = "local_owner_candidate_invalid"


class LocalOwnerProfileInvalidError(LocalIdentityError):
    code = "local_owner_profile_invalid"


class LocalOwnerPrivacyAcknowledgementRequiredError(LocalIdentityError):
    code = "local_owner_privacy_acknowledgement_required"


class LocalSessionRateLimitedError(LocalIdentityError):
    code = "local_session_rate_limited"


class LocalSessionUnavailableError(LocalIdentityError):
    code = "app_secret_missing"


class CredentialResolutionError(ValueError):
    pass


class CredentialMigrationError(RuntimeError):
    def __init__(self, code: str, *, record_type: str, record_id: str) -> None:
        self.code = code
        self.record_type = record_type
        self.record_id = record_id
        super().__init__(code)


class DemoAccountLockedError(Exception):
    pass


class ExternalVerificationRateLimitedError(Exception):
    def __init__(self, retry_after_seconds: int) -> None:
        self.retry_after_seconds = max(1, retry_after_seconds)
        super().__init__("External verification temporarily rate limited")


class TurnstileError(Exception):
    pass


class TurnstileVerificationError(TurnstileError):
    pass


class TurnstileConfigError(TurnstileError):
    pass


class TurnstileUnavailableError(TurnstileError):
    pass


class BrowserSessionConfigurationError(ValueError):
    pass
