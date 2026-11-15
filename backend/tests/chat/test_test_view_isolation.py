"""Temporary historical facade patches must not escape their test scope."""
import pytest

from chat_service_support import messages


@pytest.mark.parametrize("name", ["generate_text", "_world_thread_read"])
def test_forwarded_patch_restores_the_actual_owner(name):
    owner = messages._owner(name)
    original = getattr(owner, name)
    first = lambda *args, **kwargs: "first"
    second = lambda *args, **kwargs: "second"

    with pytest.MonkeyPatch.context() as outer:
        outer.setattr(messages, name, first)
        assert getattr(owner, name) is first
        with pytest.MonkeyPatch.context() as inner:
            inner.setattr(messages, name, second)
            assert getattr(owner, name) is second
        assert getattr(owner, name) is first
    assert getattr(owner, name) == original
    assert getattr(messages, name) == original
