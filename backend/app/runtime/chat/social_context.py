"""Wire canonical-validating Relationships reads to one chat request."""
from app.domains.relationships.service.social_context import SocialContextService
from app.domains.chat.contracts.chat_identity_context import presentation_name


class ChatSocialContextProvider:
    def __init__(self, recall, labels, *, label_reader=None):
        self._service = SocialContextService(recall.execute, label_reader=label_reader, name_policy=presentation_name)
        self._labels = labels

    def prepare(self, scope, *, counterpart_id=None):
        return self._service.prepare(scope, labels=self._labels, counterpart_id=counterpart_id)

    def bind_labels(self, labels):
        self._labels.update(labels)

    def assert_current(self, snapshot):
        self._service.assert_current(snapshot)
