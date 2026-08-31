"""Framework-independent Chat errors used by application and HTTP adapters."""


class MessageServiceError(Exception):
    """Base error for the legacy-compatible Chat v1 use cases."""


class MessageNotFoundError(MessageServiceError):
    pass


class MessageForbiddenError(MessageServiceError):
    pass


class MessageThreadLimitError(MessageServiceError):
    pass


class MessageCredentialRequiredError(MessageServiceError):
    pass


class MessageCredentialInvalidError(MessageServiceError):
    pass


class MessageModelBusyError(MessageServiceError):
    pass


class MessageInFlightError(MessageServiceError):
    pass


class MessageValidationError(MessageServiceError):
    pass
