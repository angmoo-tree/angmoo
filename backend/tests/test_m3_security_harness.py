from __future__ import annotations

import asyncio
import json
import socket
from pathlib import Path

import httpx
import pytest
from fastapi.routing import APIRoute, _iter_routes_with_context

from app.main import app
from app.services import agent_runs as agent_run_service
from conftest import ExternalNetworkBlocked


BACKEND_ROOT = Path(__file__).resolve().parents[1]
INVENTORY_PATH = BACKEND_ROOT / "security" / "route_security_inventory.json"
VALID_ACCESS = {
    "public",
    "authenticated-shared",
    "owner-only",
    "admin-only",
    "local-bot-token",
    "private-excluded",
}
UNSAFE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}
PREAUTH_MUTATION_ROUTES = {
    "POST /api/v1/auth/local/bootstrap/challenge",
    "POST /api/v1/auth/local/bootstrap/claim",
    "POST /api/v1/auth/local/session",
    "POST /api/v1/posts/{post_id}/comments",
}
SESSION_LIFECYCLE_MUTATIONS = {
    "POST /api/v1/auth/logout",
}


def _route_key(route, method: str) -> str:
    return f"{method} {route.path}"


def _canonical_inventory_module(module: str) -> str:
    if module == "app.main":
        return "app.public_main"
    return module


def _dependency_names(route) -> set[str]:
    names: set[str] = set()

    def walk(dependant) -> None:
        for dependency in dependant.dependencies:
            call = dependency.call
            if call is not None:
                names.add(getattr(call, "__name__", type(call).__name__))
            walk(dependency)

    walk(route.dependant)
    return names


def _actual_routes() -> dict[str, object]:
    result: dict[str, object] = {}
    for route, context in _iter_routes_with_context(app.routes):
        if not isinstance(route, APIRoute):
            continue
        effective_route = context or route
        for method in sorted(effective_route.methods or ()):
            result[_route_key(effective_route, method)] = effective_route
    return result


def _inventory() -> dict[str, dict[str, str]]:
    payload = json.loads(INVENTORY_PATH.read_text(encoding="utf-8"))
    assert payload["schema_version"] == 1
    return payload["routes"]


def test_security_inventory_explicitly_covers_every_openapi_operation() -> None:
    actual = _actual_routes()
    inventory = _inventory()

    covered = {
        key for key, metadata in inventory.items()
        if metadata["access"] != "private-excluded"
    }
    excluded = {
        key for key, metadata in inventory.items()
        if metadata["access"] == "private-excluded"
    }
    assert covered == set(actual)
    assert excluded.isdisjoint(actual)
    for key, metadata in inventory.items():
        assert metadata["access"] in VALID_ACCESS
        if metadata["access"] == "private-excluded":
            continue
        route = actual[key]
        assert metadata["module"] == _canonical_inventory_module(
            route.endpoint.__module__
        )
        assert metadata["endpoint"] == route.name


def test_security_inventory_access_classes_match_authentication_dependencies() -> None:
    actual = _actual_routes()
    for key, metadata in _inventory().items():
        if metadata["access"] == "private-excluded":
            assert key not in actual
            continue
        dependencies = _dependency_names(actual[key])
        access = metadata["access"]
        if access == "admin-only":
            pytest.fail(f"Public runtime must not expose an admin route: {key}")
        elif access == "local-bot-token":
            assert "get_current_local_bot" in dependencies, key
        elif access in {"authenticated-shared", "owner-only"}:
            if key in SESSION_LIFECYCLE_MUTATIONS:
                assert "get_current_session_for_logout" in dependencies, key
                continue
            assert dependencies & {
                "get_current_user",
                "get_current_user_allow_incomplete",
            }, key


def test_every_client_object_id_route_has_an_explicit_inventory_entry() -> None:
    object_routes = {key for key in _actual_routes() if "{" in key}
    assert object_routes
    assert object_routes <= set(_inventory())


def test_demo_read_only_guard_covers_every_mutation_auth_surface() -> None:
    actual = _actual_routes()
    inventory = _inventory()

    session_mutations = {
        key
        for key, metadata in inventory.items()
        if key.split(" ", 1)[0] in UNSAFE_METHODS
        and metadata["access"] in {"authenticated-shared", "owner-only"}
        and key not in SESSION_LIFECYCLE_MUTATIONS
    }
    local_bot_mutations = {
        key
        for key, metadata in inventory.items()
        if key.split(" ", 1)[0] in UNSAFE_METHODS
        and metadata["access"] == "local-bot-token"
    }
    admin_mutations = {
        key
        for key, metadata in inventory.items()
        if key.split(" ", 1)[0] in UNSAFE_METHODS
        and metadata["access"] == "admin-only"
    }
    preauth_mutations = {
        key
        for key, metadata in inventory.items()
        if key.split(" ", 1)[0] in UNSAFE_METHODS
        and metadata["access"] == "public"
    }
    assert len(session_mutations) == 86
    assert len(local_bot_mutations) == 10
    assert not admin_mutations
    assert preauth_mutations == PREAUTH_MUTATION_ROUTES
    assert SESSION_LIFECYCLE_MUTATIONS <= set(inventory)

    for key in session_mutations:
        assert _dependency_names(actual[key]) & {
            "get_current_user",
            "get_current_user_allow_incomplete",
        }, key
    for key in local_bot_mutations:
        assert "get_current_local_bot" in _dependency_names(actual[key]), key
    for key in SESSION_LIFECYCLE_MUTATIONS:
        assert "get_current_session_for_logout" in _dependency_names(actual[key]), key


def test_private_runtime_does_not_expose_global_resident_tick(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    called = False

    async def _unexpected_tick(*args, **kwargs):
        nonlocal called
        called = True
        raise AssertionError("global resident tick must not be reachable over HTTP")

    monkeypatch.setattr(agent_run_service, "tick_resident_slots", _unexpected_tick)

    async def _post_tick() -> httpx.Response:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            return await client.post(
                "/api/v1/agent-runs/resident-slots/tick",
                json={
                    "post_id": "post-attacker",
                    "message": "attacker context",
                    "max_runs": 10,
                },
            )

    response = asyncio.run(_post_tick())

    assert response.status_code in {404, 405}
    assert called is False


def test_private_runtime_does_not_expose_community_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    called = False

    async def _unexpected_run(*args, **kwargs):
        nonlocal called
        called = True
        raise AssertionError("community-once must not be reachable over HTTP")

    monkeypatch.setattr(agent_run_service, "run_community_once", _unexpected_run)

    async def _post_community_once() -> httpx.Response:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            return await client.post(
                "/api/v1/agent-runs/community-once",
                json={"character_id": "char-attacker"},
            )

    response = asyncio.run(_post_community_once())

    assert response.status_code in {404, 405}
    assert called is False


def test_network_deny_fixture_blocks_non_loopback_resolution(
    deny_external_network,
) -> None:
    with pytest.raises(ExternalNetworkBlocked, match="network access blocked"):
        socket.getaddrinfo("provider.invalid", 443)


def test_network_deny_fixture_allows_loopback_resolution(
    deny_external_network,
) -> None:
    results = socket.getaddrinfo("127.0.0.1", 8080)
    assert results
