"""Retrieval denials and entity eligibility belong to the actual Chat policy."""

from types import SimpleNamespace

import pytest

from app.domains.chat.contracts import CanonicalRetrievalScope, RetrievalContractError
from app.domains.chat.service.retrieval_policy import RetrievalPolicyResolver
from test_p8_l_k_retrieval_router import _command


@pytest.mark.parametrize(
    "installation",
    [None, SimpleNamespace(bootstrap_state="claimed", owner_user_id="other")],
)
def test_preflight_owner_denial_precedes_other_queries(installation):
    session = object()
    command = _command()
    calls = []

    def installation_read(db, received):
        calls.append((db, received))
        return installation

    resolver = RetrievalPolicyResolver(
        session, SimpleNamespace(installation=installation_read), object()
    )
    with pytest.raises(
        RetrievalContractError, match="retrieval_preflight_local_owner_forbidden"
    ):
        resolver.load_scope(command)
    assert calls == [(session, command)]


def test_entity_policy_rechecks_unicode_identity_and_blocks_clarification():
    session = object()
    scope = CanonicalRetrievalScope(
        request_id="request",
        owner_id="owner",
        world_id="world",
        thread_id="thread",
        requester_world_character_id="requester",
        responding_world_character_id="responding",
        world_timezone="Asia/Seoul",
        world_language="ko",
        responding_character_name="Responder",
        memory_enabled=True,
    )
    observed = []
    membership = SimpleNamespace(status="active")
    rows = [
        (
            SimpleNamespace(id="eligible", status="active"),
            SimpleNamespace(
                name="Alice",
                handle="alice",
                deleted_at=None,
                moderation_status="active",
            ),
            membership,
        ),
        (
            SimpleNamespace(id="sql-only-match", status="active"),
            SimpleNamespace(
                name="Unrelated",
                handle="unrelated",
                deleted_at=None,
                moderation_status="active",
            ),
            membership,
        ),
    ]

    def entity_mentions(db, *, world_id, normalized):
        observed.append((db, world_id, normalized))
        return rows

    def blocked(db, **kwargs):
        observed.append((db, kwargs))
        return True

    resolver = RetrievalPolicyResolver(
        session, SimpleNamespace(entity_mentions=entity_mentions), blocked
    )
    result = resolver.resolve_entity_mentions(scope, (("ref", " @ALICE "),))
    assert observed == [
        (session, "world", "alice"),
        (
            session,
            {
                "world_id": "world",
                "first_world_character_id": "responding",
                "second_world_character_id": "eligible",
            },
        ),
    ]
    assert len(result) == 1
    assert result[0].ref == "ref"
    assert len(result[0].candidates) == 1
    candidate = result[0].candidates[0]
    assert candidate.world_character_id == "eligible"
    assert candidate.blocked is True
    assert candidate.observable is False
    assert candidate.safe_for_clarification is False
