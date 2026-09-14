"""Wire canonical-validating Relationships reads to one chat request."""
from app.domains.relationships.service.social_context import SocialContextService


class ChatSocialContextProvider:
    def __init__(self, recall, labels):
        self._service = SocialContextService(recall.execute)
        self._labels = labels

    def prepare(self, scope, *, counterpart_id=None):
        return self._service.prepare(scope, labels=self._labels, counterpart_id=counterpart_id)

    def assert_current(self, snapshot):
        self._service.assert_current(snapshot)
