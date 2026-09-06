import asyncio
from types import SimpleNamespace
import pytest
from app.runtime.resident import credential_profiles as profiles


class ProfileError(Exception):
    pass


class RecordedProfiles:
    OpenClawAuthProfileSyncError = ProfileError
    def __init__(self, events, *, matched=False, fail=None):
        self.events, self.matched, self.fail = events, matched, fail
    def inspect_credential_slot(self, **kwargs):
        self.events.append('inspect')
        if self.fail == 'inspect':
            raise ProfileError('{"api_key":"synthetic-secret"}')
        return {'matches': self.matched}
    def bind_credential_to_slot(self, **kwargs):
        self.events.append('bind')
        assert kwargs['api_key'] == 'synthetic-secret'
        if self.fail == 'bind':
            raise ProfileError('{"api_key":"synthetic-secret"}')
        self.matched = self.fail != 'preflight'
    def release_credential_from_slot(self, **kwargs):
        self.events.append('release')


class RecordedClient:
    def __init__(self, events, *, fail=False):
        self.events, self.fail = events, fail
    async def reload_secrets(self):
        self.events.append('reload')
        if self.fail:
            raise profiles.OpenClawGatewayError('{"api_key":"synthetic-secret"}')


def _resolver(monkeypatch, events):
    def resolve(credential, **kwargs):
        events.append('resolve')
        assert kwargs == dict(purpose=profiles.CredentialPurpose.PRIVATE_OPENCLAW, owner_id='owner', character_id='character')
        def reveal():
            events.append('reveal')
            return 'synthetic-secret'
        return SimpleNamespace(reveal=reveal)
    monkeypatch.setattr(profiles.CredentialResolver, 'resolve_llm_credential', resolve)


def test_slot_auth_avoids_reveal_for_match_and_preserves_bind_reload_release_order(monkeypatch):
    events = []
    _resolver(monkeypatch, events)
    adapter, client = RecordedProfiles(events, matched=True), RecordedClient(events)
    credential = object()
    kwargs = dict(client=client, openclaw_auth_profiles=adapter, agent_id='slot', user_id='owner', character=SimpleNamespace(id='character'), credential=credential)
    assert asyncio.run(profiles._ensure_slot_auth_profile(**kwargs)) is True
    assert events == ['inspect']
    events.clear()
    adapter.matched = False
    assert asyncio.run(profiles._ensure_slot_auth_profile(**kwargs)) is True
    assert events == ['inspect', 'resolve', 'reveal', 'bind', 'reload', 'inspect']
    events.clear()
    asyncio.run(profiles._release_slot_auth_profile(client=client, openclaw_auth_profiles=adapter, agent_id='slot', user_id='owner', character_id='character', credential=credential))
    assert events == ['release', 'reload']


@pytest.mark.parametrize('fail,expected', [
    ('inspect', ['inspect']),
    ('bind', ['inspect', 'resolve', 'reveal', 'bind']),
    ('reload', ['inspect', 'resolve', 'reveal', 'bind', 'reload']),
    ('preflight', ['inspect', 'resolve', 'reveal', 'bind', 'reload', 'inspect']),
])
def test_slot_auth_failure_stops_at_original_stage_and_redacts_secret(monkeypatch, fail, expected):
    events = []
    _resolver(monkeypatch, events)
    with pytest.raises(profiles.CredentialSyncError) as caught:
        asyncio.run(profiles._ensure_slot_auth_profile(
            client=RecordedClient(events, fail=fail == 'reload'), openclaw_auth_profiles=RecordedProfiles(events, fail=fail),
            agent_id='slot', user_id='owner', character=SimpleNamespace(id='character'), credential=object(),
        ))
    assert events == expected
    assert 'synthetic-secret' not in str(caught.value)
    if fail == 'preflight':
        assert str(caught.value) == 'OpenClaw auth profile preflight failed'
    else:
        assert '[REDACTED]' in str(caught.value)
