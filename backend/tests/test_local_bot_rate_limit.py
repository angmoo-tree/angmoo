from types import SimpleNamespace

import pytest

from app.services import local_bot


def _context():
    return SimpleNamespace(
        user=SimpleNamespace(id="user-1"),
        character=SimpleNamespace(id="char-1"),
        local_key=SimpleNamespace(id="key-1", token_prefix="angmoo_local_test"),
    )


@pytest.mark.parametrize(
    ("label", "expected_action_types"),
    [
        ("like", ("liked",)),
        ("repost", ("reposted",)),
        ("follow", ("followed",)),
        ("unfollow", ("unfollowed",)),
    ],
)
def test_reaction_cooldown_is_action_specific(
    monkeypatch, label, expected_action_types
):
    calls = []

    def fake_daily_limit(db, context):
        calls.append(("daily",))

    def fake_activity_limit(
        db, *, context, action_types, cooldown, max_per_day, label
    ):
        calls.append((action_types, cooldown, max_per_day, label))

    monkeypatch.setattr(local_bot, "_ensure_reaction_daily_limit", fake_daily_limit)
    monkeypatch.setattr(local_bot, "_ensure_activity_rate_limit", fake_activity_limit)

    local_bot._ensure_reaction_rate_limit(object(), _context(), label=label)

    assert calls == [
        ("daily",),
        (expected_action_types, local_bot.REACTION_COOLDOWN, None, label),
    ]


def test_reaction_daily_limit_still_uses_shared_reaction_bucket(monkeypatch):
    class FakeDb:
        def scalar(self, _statement):
            return local_bot.MAX_REACTIONS_PER_DAY

    class RaisedRateLimit(Exception):
        def __init__(self, label):
            self.label = label

    def fake_raise_rate_limit(
        db, context, *, label, message, retry_after_seconds
    ):
        raise RaisedRateLimit(label)

    monkeypatch.setattr(local_bot, "_raise_rate_limit", fake_raise_rate_limit)

    with pytest.raises(RaisedRateLimit) as exc:
        local_bot._ensure_reaction_daily_limit(FakeDb(), _context())

    assert exc.value.label == "reaction"

