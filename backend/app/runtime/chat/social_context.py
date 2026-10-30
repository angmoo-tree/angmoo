"""Wire canonical-validating Relationships reads to one chat request."""
from app.domains.relationships.service.social_context import SocialContextService
from app.domains.chat.contracts.chat_identity_context import presentation_name


class ChatSocialContextProvider:
    def __init__(self, recall, labels, *, label_reader=None):
        self._service = SocialContextService(recall.execute, label_reader=label_reader, name_policy=presentation_name)
        self._labels = labels
        from app.domains.relationships.service.social_context_validation import SocialContextValidationService
        self._access = SocialContextValidationService(recall._gateway)

    def prepare(self, scope, *, counterpart_id=None):
        return self._service.prepare(scope, labels=self._labels, counterpart_id=counterpart_id)

    def bind_labels(self, labels):
        self._labels.update(labels)

    def assert_usable(self, snapshot):
        self._access.assert_snapshot_usable(snapshot)
