from __future__ import annotations

from sqlalchemy.orm import Session

from app import models
from app.domains.memory.domain.errors import MemoryNotFoundError
from app.domains.memory.infrastructure import SqlAlchemyMemoryRepository
from test_p8_l_q_memory_read_inspector import (
    FRONTEND_HEADERS,
    _fixture,
    _seed,
)


def _scope_path(subject_id: str) -> str:
    return f"/api/v1/worlds/q-world/world-characters/{subject_id}"


def _setting_payload(*, expected_version: int, enabled: bool, key: str) -> dict:
    return {
        "schema_version": "memory-setting-update.v1",
        "expected_version": expected_version,
        "enabled": enabled,
        "idempotency_key": key,
    }


def test_owner_setting_is_saved_scope_exact_csrf_safe_and_replayable() -> None:
    client, engine, principal = _fixture()
    seeded = _seed(engine, principal)
    path = f"{_scope_path('q-requester')}/memory/settings"
    payload = _setting_payload(
        expected_version=0,
        enabled=True,
        key="setting-requester-enable-0001",
    )

    csrf_rejected = client.put(path, json=payload)
    first = client.put(path, headers=FRONTEND_HEADERS, json=payload)
    replay = client.put(path, headers=FRONTEND_HEADERS, json=payload)
    stale = client.put(
        path,
        headers=FRONTEND_HEADERS,
        json=_setting_payload(
            expected_version=0,
            enabled=False,
            key="setting-requester-disable-stale",
        ),
    )
    current = client.get(path, headers=FRONTEND_HEADERS)
    other_scope = client.get(
        f"{_scope_path('q-responding')}/memory/settings",
        headers=FRONTEND_HEADERS,
    )

    assert csrf_rejected.status_code == 403
    assert first.status_code == 200
    assert first.json()["outcome"] == "updated"
    assert first.json()["setting"]["enabled"] is True
    assert first.json()["setting"]["version"] == 2
    assert first.json()["projection_cleanup"] == "automatic_after_commit"
    assert replay.status_code == 200
    assert replay.json()["outcome"] == "reused"
    assert replay.json()["setting"]["version"] == 2
    assert stale.status_code == 409
    assert current.json()["enabled"] is True
    assert other_scope.json()["enabled"] is False
    assert seeded["memory_id"]


def test_owner_can_pin_and_unpin_existing_memory_while_scope_is_off() -> None:
    client, engine, principal = _fixture()
    seeded = _seed(engine, principal)
    memory_id = str(seeded["memory_id"])
    path = f"{_scope_path('q-responding')}/memories/{memory_id}/pin"
    pin_payload = {
        "schema_version": "memory-pin-update.v1",
        "expected_version": 1,
        "pinned": True,
        "idempotency_key": "pin-owner-memory-0001",
    }

    pinned = client.put(path, headers=FRONTEND_HEADERS, json=pin_payload)
    replay = client.put(path, headers=FRONTEND_HEADERS, json=pin_payload)
    stale_unpin = client.put(
        path,
        headers=FRONTEND_HEADERS,
        json={
            **pin_payload,
            "pinned": False,
            "idempotency_key": "unpin-owner-memory-stale",
        },
    )
    unpinned = client.put(
        path,
        headers=FRONTEND_HEADERS,
        json={
            **pin_payload,
            "expected_version": 2,
            "pinned": False,
            "idempotency_key": "unpin-owner-memory-0002",
        },
    )

    assert pinned.status_code == 200
    assert pinned.json()["operation"] == "pin"
    assert pinned.json()["item"]["pinned"] is True
    assert pinned.json()["item"]["version"] == 2
    assert replay.status_code == 200
    assert replay.json()["outcome"] == "reused"
    assert stale_unpin.status_code == 409
    assert unpinned.status_code == 200
    assert unpinned.json()["operation"] == "unpin"
    assert unpinned.json()["item"]["pinned"] is False
    assert unpinned.json()["item"]["version"] == 3


def test_owner_correction_revalidates_evidence_and_supersedes_old_item() -> None:
    client, engine, principal = _fixture()
    seeded = _seed(engine, principal)
    memory_id = str(seeded["memory_id"])
    scope_path = _scope_path("q-responding")
    setting = client.get(f"{scope_path}/memory/settings", headers=FRONTEND_HEADERS).json()
    enabled = client.put(
        f"{scope_path}/memory/settings",
        headers=FRONTEND_HEADERS,
        json=_setting_payload(
            expected_version=setting["version"],
            enabled=True,
            key="setting-correction-enable-0001",
        ),
    ).json()["setting"]
    payload = {
        "schema_version": "memory-correction-create.v1",
        "expected_item_version": 1,
        "expected_scope_version": enabled["version"],
        "summary": "오늘 훈련 뒤 함께한 약속을 지켰다.",
        "idempotency_key": "owner-correction-memory-0001",
    }

    corrected = client.post(
        f"{scope_path}/memories/{memory_id}/corrections",
        headers=FRONTEND_HEADERS,
        json=payload,
    )
    replay = client.post(
        f"{scope_path}/memories/{memory_id}/corrections",
        headers=FRONTEND_HEADERS,
        json=payload,
    )

    assert corrected.status_code == 200
    corrected_payload = corrected.json()
    replacement_id = corrected_payload["item"]["id"]
    assert corrected_payload["operation"] == "correct"
    assert corrected_payload["outcome"] == "updated"
    assert corrected_payload["replaced_memory_id"] == memory_id
    assert replacement_id != memory_id
    assert corrected_payload["item"]["summary"] == payload["summary"]
    assert replay.status_code == 200
    assert replay.json()["outcome"] == "reused"
    assert replay.json()["item"]["id"] == replacement_id

    old_detail = client.get(
        f"{scope_path}/memories/{memory_id}", headers=FRONTEND_HEADERS
    ).json()
    new_detail = client.get(
        f"{scope_path}/memories/{replacement_id}", headers=FRONTEND_HEADERS
    ).json()
    assert old_detail["lifecycle"] == "superseded"
    assert old_detail["superseded_by_memory_id"] == replacement_id
    assert new_detail["lifecycle"] == "active"
    assert new_detail["evidence"][0]["availability"] == "available"

    with Session(engine) as db:
        repository = SqlAlchemyMemoryRepository(db)
        try:
            repository.get_retrievable_item(
                scope=seeded["scope"], item_id=memory_id, now=new_detail_date()
            )
        except MemoryNotFoundError:
            pass
        else:
            raise AssertionError("superseded memory remained retrievable")
        assert repository.get_retrievable_item(
            scope=seeded["scope"], item_id=replacement_id, now=new_detail_date()
        ).summary == payload["summary"]


def test_correction_fails_closed_when_canonical_source_changed() -> None:
    client, engine, principal = _fixture()
    seeded = _seed(engine, principal)
    scope_path = _scope_path("q-responding")
    setting = client.get(f"{scope_path}/memory/settings", headers=FRONTEND_HEADERS).json()
    enabled = client.put(
        f"{scope_path}/memory/settings",
        headers=FRONTEND_HEADERS,
        json=_setting_payload(
            expected_version=setting["version"],
            enabled=True,
            key="setting-stale-source-enable",
        ),
    ).json()["setting"]
    with Session(engine) as db:
        source = db.get(models.MessageMessage, seeded["source_message_id"])
        assert source is not None
        source.content = "근거 원문이 나중에 변경됨"
        db.commit()

    response = client.post(
        f"{scope_path}/memories/{seeded['memory_id']}/corrections",
        headers=FRONTEND_HEADERS,
        json={
            "schema_version": "memory-correction-create.v1",
            "expected_item_version": 1,
            "expected_scope_version": enabled["version"],
            "summary": "근거와 달라진 정정",
            "idempotency_key": "owner-correction-stale-source",
        },
    )

    assert response.status_code == 409
    assert response.json()["detail"] == "memory_source_digest_conflict"


def test_delete_blocks_retrieval_immediately_is_replayable_and_scope_private() -> None:
    client, engine, principal = _fixture()
    seeded = _seed(engine, principal)
    memory_id = str(seeded["memory_id"])
    path = f"{_scope_path('q-responding')}/memories/{memory_id}"
    payload = {
        "schema_version": "memory-delete.v1",
        "expected_version": 1,
        "idempotency_key": "owner-delete-memory-0001",
    }

    principal["user"] = seeded["outsider"]
    outsider = client.request("DELETE", path, headers=FRONTEND_HEADERS, json=payload)
    principal["user"] = seeded["owner"]
    deleted = client.request("DELETE", path, headers=FRONTEND_HEADERS, json=payload)
    replay = client.request("DELETE", path, headers=FRONTEND_HEADERS, json=payload)
    listing = client.get(
        f"{_scope_path('q-responding')}/memories", headers=FRONTEND_HEADERS
    )

    assert outsider.status_code == 404
    assert deleted.status_code == 200
    assert deleted.json()["operation"] == "delete"
    assert deleted.json()["outcome"] == "deleted"
    assert deleted.json()["item"]["lifecycle"] == "deleted"
    assert replay.status_code == 200
    assert replay.json()["outcome"] == "reused"
    assert listing.json()["items"] == []
    with Session(engine) as db:
        try:
            SqlAlchemyMemoryRepository(db).get_retrievable_item(
                scope=seeded["scope"], item_id=memory_id, now=new_detail_date()
            )
        except MemoryNotFoundError:
            pass
        else:
            raise AssertionError("deleted memory remained retrievable")


def new_detail_date():
    from datetime import UTC, datetime

    return datetime.now(UTC)
