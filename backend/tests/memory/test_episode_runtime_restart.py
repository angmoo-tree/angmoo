from fastapi.testclient import TestClient
from sqlalchemy import text

from app.config import settings
from app.runtime.contributor_backend import create_contributor_runtime_app


def test_default_episode_runtime_start_shutdown_restart_and_legacy_rollback(tmp_path, monkeypatch):
    for selected_policy in (None, "legacy", "episode_v1"):
        policy = selected_policy or "episode_v1"
        if selected_policy is not None:
            monkeypatch.setattr(settings, "MEMORY_GENERATION_POLICY", policy)
            monkeypatch.setattr(settings, "MEMORY_RECALL_REPRESENTATION", policy)
            monkeypatch.setattr(settings, "ACTIVITY_THOUGHT_POLICY", "thought_v1" if policy == "episode_v1" else "legacy")
        app = create_contributor_runtime_app(data_root=tmp_path / "episode-runtime")
        with TestClient(app) as client:
            assert client.get("/health").status_code == 200
            composition = app.state.runtime_composition
            assert composition.settings.MEMORY_RECALL_REPRESENTATION == policy
            assert composition.settings.MEMORY_GENERATION_POLICY == policy
            assert composition.settings.ACTIVITY_THOUGHT_POLICY == ("thought_v1" if policy == "episode_v1" else "legacy")
            assert composition.memory_hybrid_runtime._episode_only == (policy == "episode_v1")
            with composition.engine.connect() as db:
                assert db.execute(text("PRAGMA integrity_check")).scalar() == "ok"
                assert not db.execute(text("PRAGMA foreign_key_check")).all()
                assert db.execute(text("SELECT count(*) FROM memory_episode_info")).scalar() == 0
