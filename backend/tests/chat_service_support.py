"""Keep historical Chat tests aimed at the actual split service instances.

The former module exposed thread, settings and message helpers together. Tests
retain their existing assertions and monkeypatch names while patches now reach
the owning service method. Product code does not use this compatibility view.
"""

from app.domains.chat import exceptions, policies
from app.domains.chat.service import profiles
from app.runtime.chat import sqlalchemy_service as legacy
from app.runtime.chat.message_composition import (
    message_service,
    settings_service,
    thread_service,
)


class HistoricalChatTestView:
    def _owner(self, name):
        for owner in (
            message_service,
            settings_service,
            thread_service,
            profiles,
            policies,
            exceptions,
            legacy,
        ):
            if hasattr(owner, name):
                return owner
        raise AttributeError(name)

    def __getattr__(self, name):
        return getattr(self._owner(name), name)

    def __setattr__(self, name, value):
        setattr(self._owner(name), name, value)


messages = HistoricalChatTestView()
