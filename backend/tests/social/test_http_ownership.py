from types import SimpleNamespace

from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from fastapi.routing import _iter_routes_with_context
import pytest

from app.api import identity_dependencies
from app.api.v1.routes import community as community_assembly
from app.domains.social import dependencies
from app.domains.social.exceptions import NotificationNotFoundError
from app.runtime.social import composition, discovery, inbox, profile_activity, timeline


def test_both_factories_bind_social_services_and_preserve_character_state_order():
    from app.main import create_app as hosted
    from app.main import create_public_app as local
    for factory in (hosted, local):
        app = factory()
        request = Request({"type": "http", "app": app})
        assert dependencies.get_timeline_service(request) is timeline.timeline_service
        assert dependencies.get_inbox_service(request) is inbox.inbox_service
        assert dependencies.get_discovery_service(request) is discovery.discovery_service
        assert dependencies.get_profile_activity_service(request) is profile_activity.profile_activity_service
        routes = [route for route, _ in _iter_routes_with_context(app.routes)]
        social_routes = [route for route in routes if getattr(getattr(route, "endpoint", None), "__module__", "") == "app.domains.social.router" and "manual-social" not in getattr(route, "tags", [])]
        assert len(social_routes) == 31
        names = [getattr(route, "name", "") for route in routes]
        assert names.count("save_character_state") == 1
        assert names.count("get_character_activity") == 1
        assert names.index("save_character_state") + 1 == names.index("get_character_activity")
    assert dependencies.get_current_user is identity_dependencies.get_current_user
    assert dependencies.get_optional_current_user is identity_dependencies.get_optional_current_user


def test_social_dependencies_fail_closed_before_runtime_configuration():
    request = Request({"type": "http", "app": FastAPI()})
    for getter in (dependencies.get_timeline_service, dependencies.get_inbox_service, dependencies.get_discovery_service, dependencies.get_profile_activity_service):
        with pytest.raises(RuntimeError, match="is not configured"):
            getter(request)


def test_inbox_http_preserves_request_values_validation_and_error_mapping():
    app = FastAPI()
    composition.configure_social_runtime(app)
    app.include_router(community_assembly.router, prefix="/api/v1")
    db, owner = object(), SimpleNamespace(id="owner", display_name="Owner")
    calls = []
    class MissingInbox:
        def mark_notification_read(self, session, user, notification_id):
            calls.append((session, user, notification_id))
            raise NotificationNotFoundError(notification_id)
    app.state.social_inbox_service = MissingInbox()
    app.dependency_overrides[dependencies.get_db] = lambda: db
    app.dependency_overrides[dependencies.get_current_user] = lambda: owner
    client = TestClient(app)
    response = client.patch("/api/v1/notifications/7/read")
    assert response.status_code == 404
    assert response.json() == {"detail": "Notification not found"}
    assert calls == [(db, owner, 7)]
    invalid = client.patch("/api/v1/notifications/not-an-integer/read")
    assert invalid.status_code == 422
    assert calls == [(db, owner, 7)]
