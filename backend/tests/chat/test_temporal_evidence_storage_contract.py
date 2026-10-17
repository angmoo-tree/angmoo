"""Temporal inspector fields are additive, bounded and validated before insertion."""

from copy import deepcopy
from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select

from chat.test_p8_l_j_response_generation_lifecycle import (
    response_session, _ready_to_commit, _commit_payload, _fence, models,
)
from app.domains.chat.contracts.evidence_bundle import (
    EvidenceBundle, EvidenceBundleContractError, EvidenceItem, EvidenceKind, compute_evidence_hash,
)
from app.domains.chat.contracts.generation_lifecycle import GenerationContractError
from app.domains.chat.contracts.response_request import RetrievalAxis, RetrievalOutcome
from app.domains.chat.repository.response_lifecycle import SqlAlchemyResponseLifecycleRepository
from app.domains.chat.service.evidence import _time_provenance

pytestmark = pytest.mark.usefixtures("deny_external_network")

START = "2026-10-16T03:17:19.107018+00:00"
END = "2026-10-17T03:17:19Z"
RECORDED = "2026-10-17T13:00:00+09:00"


def _payload(record, times=None):
    items = tuple(EvidenceItem(
        opaque_reference=f"evidence-{index}",
        kind=EvidenceKind.EPISODE_MEMORY if index == 0 else EvidenceKind.TODAY_SNS_ACTIVITY,
        text="Isolated source evidence", occurred_at=datetime.now(UTC), axes=(RetrievalAxis.CANONICAL,),
    ) for index in range(5))
    values = dict(request_id=record.request_id, request_scope_hash=record.request_scope_hash,
        route=record.route, retrieval_outcome=RetrievalOutcome.CURRENT_CONTEXT, items=items,
        partial_axes=(), degraded_reason=None, clarification_slot=None)
    bundle = EvidenceBundle(**values, evidence_hash=compute_evidence_hash(**values))
    if times is not None:
        bundle = replace(bundle, items=(replace(items[0], prepared_times=times), *items[1:])).with_temporal_evidence()
    payload = _commit_payload(record)
    return replace(payload, evidence_inspector_snapshot=bundle.inspector_snapshot(),
        metadata=replace(payload.metadata, public_evidence_count=5, evidence_bundle_version=bundle.version,
            evidence_hash=bundle.evidence_hash, evidence_capability=bundle.evidence_capability))


@pytest.mark.parametrize("times", [
    None,
    ("event", START, None, None),
    ("event", START, START, RECORDED),
    ("interval", START, END, RECORDED),
    ("recorded", None, None, RECORDED),
    ("unknown", None, None, None),
    ("unknown", None, None, RECORDED),
], ids=["legacy", "event", "point-range", "interval", "recorded", "unknown", "unknown-event-recorded"])
def test_mixed_evidence_commit_preserves_legacy_or_verified_time_payload(response_session, times):
    db, now = response_session, datetime.now(UTC)
    repository = SqlAlchemyResponseLifecycleRepository(db)
    record = _ready_to_commit(repository, now)
    db.commit()
    payload = _payload(record, times)
    repository.finalize(_fence(record), payload, now=now + timedelta(seconds=1))
    db.commit()
    db.expire_all()
    saved = repository.get_request(record.request_id)
    assert saved.state.value == "committed"
    assert saved.response_metadata["_evidence_inspector_v1"] == payload.evidence_inspector_snapshot
    assert saved.response_metadata["evidence_hash"] == payload.metadata.evidence_hash
    assert db.scalar(select(func.count()).select_from(models.MessageMessage).where(
        models.MessageMessage.role == "assistant")) == 1


VALID_TIME = {"kind": "event", "event_from": START, "event_to": None, "recorded_at": None}
BAD_TIMES = [
    None, [], {},
    {**VALID_TIME, "extra": "untrusted"},
    {key: value for key, value in VALID_TIME.items() if key != "event_to"},
    {**VALID_TIME, "kind": []},
    {**VALID_TIME, "kind": "made_up"},
    *({**VALID_TIME, "event_from": value} for value in [
        "2026-02-30T12:00:00Z", "2026-10-17", "2026-10-17T12:00:00",
        "2026-10-17T24:00:00Z", "2026-10-17T12:00:00+25:00",
        1792200000, True, "x" * 41,
    ]),
    {**VALID_TIME, "event_from": None},
    {**VALID_TIME, "event_to": END},
    {**VALID_TIME, "recorded_at": "not-a-date"},
    {**VALID_TIME, "kind": "interval"},
    {**VALID_TIME, "kind": "interval", "event_from": END, "event_to": START},
    {**VALID_TIME, "kind": "recorded", "recorded_at": RECORDED},
    {**VALID_TIME, "kind": "recorded", "event_from": None},
    {**VALID_TIME, "kind": "unknown"},
]


@pytest.mark.parametrize("time_value", BAD_TIMES)
@pytest.mark.parametrize("section", ["evidence", "social-context"])
def test_malformed_time_cannot_insert_an_assistant(response_session, time_value, section):
    db, now = response_session, datetime.now(UTC)
    repository = SqlAlchemyResponseLifecycleRepository(db)
    record = _ready_to_commit(repository, now)
    db.commit()
    payload = _payload(record)
    snapshot = deepcopy(payload.evidence_inspector_snapshot)
    snapshot["items"][0]["time_provenance"] = time_value
    if section == "evidence":
        payload = replace(payload, evidence_inspector_snapshot=snapshot)
    else:
        payload = replace(payload, social_context_inspector_snapshot=snapshot)
    with pytest.raises(GenerationContractError, match="response_evidence_inspector_invalid"):
        repository.finalize(_fence(record), payload, now=now + timedelta(seconds=1))
    db.rollback()
    assert repository.get_request(record.request_id).state.value == "committing"
    assert db.scalar(select(func.count()).select_from(models.MessageMessage).where(
        models.MessageMessage.role == "assistant")) == 0


@pytest.mark.parametrize("times", [
    ("event", "2026-02-30T12:00:00Z", None, None),
    ("event", START, END, None),
    ("interval", END, START, None),
])
def test_invalid_code_owned_times_cannot_enter_a_bound_evidence_item(times):
    with pytest.raises(EvidenceBundleContractError, match="evidence_time_provenance_invalid"):
        EvidenceItem("ref", EvidenceKind.EPISODE_MEMORY, "Source", None,
            (RetrievalAxis.CANONICAL,), time_provenance=times)


def test_inspector_read_preserves_verified_time_and_historical_absence():
    assert _time_provenance({}) is None
    event = _time_provenance({"time_provenance": VALID_TIME})
    assert event.kind == "event" and event.event_from == datetime.fromisoformat(START)
    unknown = _time_provenance({"time_provenance": {
        "kind": "unknown", "event_from": None, "event_to": None, "recorded_at": RECORDED,
    }})
    assert unknown.kind == "unknown" and unknown.event_from is None
    assert unknown.recorded_at == datetime.fromisoformat(RECORDED)


@pytest.mark.parametrize("value", [
    {**VALID_TIME, "event_from": 1792200000},
    {**VALID_TIME, "kind": "unknown"},
    {**VALID_TIME, "extra": "untrusted"},
])
def test_inspector_read_does_not_coerce_malformed_time_into_verified_evidence(value):
    result = _time_provenance({"time_provenance": value})
    assert result.kind == "unknown"
    assert result.event_from is result.event_to is result.recorded_at is None


@pytest.mark.parametrize("change", ["extra-item-field", "missing-axes", "extra-locator-field"])
def test_time_support_does_not_open_the_existing_inspector_allowlists(response_session, change):
    db, now = response_session, datetime.now(UTC)
    repository = SqlAlchemyResponseLifecycleRepository(db)
    record = _ready_to_commit(repository, now)
    db.commit()
    payload = _payload(record, ("event", START, None, None))
    item = payload.evidence_inspector_snapshot["items"][0]
    if change == "extra-item-field":
        item["untrusted"] = "extra"
    elif change == "missing-axes":
        item.pop("axes")
    else:
        item["locator"] = {"kind": "memory_item", "source_id": "memory", "source_type": None,
            "source_revision": None, "actor_world_character_id": None, "target_world_character_id": None,
            "untrusted": "extra"}
    with pytest.raises(GenerationContractError, match="response_evidence_inspector_invalid"):
        repository.finalize(_fence(record), payload, now=now + timedelta(seconds=1))
    db.rollback()
