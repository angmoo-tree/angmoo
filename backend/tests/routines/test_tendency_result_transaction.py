"""The original tendency commit occurs before usage/result evaluation and log write."""
from pathlib import Path

import pytest
from sqlalchemy import create_engine, select, event
from sqlalchemy.orm import Session

from app import models as _registered_models
from app.domains.identity.models import User
from app.domains.characters.models import Character
from app.domains.routines.models import AgentActivitySetting, AgentActivityLog
from app.domains.routines.service.tendency_analysis import store_tendency_analysis


@pytest.mark.parametrize("lane", ["direct", "openclaw"])
def test_tendency_result_is_evaluated_after_setting_commit_before_activity_log(tmp_path: Path, lane: str) -> None:
    engine = create_engine(f"sqlite:///{tmp_path / 'tendency.sqlite3'}")
    for table in (User.__table__, Character.__table__, AgentActivitySetting.__table__, AgentActivityLog.__table__):
        table.create(engine)
    try:
        with Session(engine) as db:
            user = User(id="owner", display_name="owner")
            character = Character(id="character", owner_id=user.id, name="character", handle="character", persona_summary="fixture", execution_mode="llm")
            setting = AgentActivitySetting(character_id=character.id, tendency_summary="before", tendency_action_ranges={}, planner_tendency_profile={}, tendency_error="previous error")
            db.add_all([user, character, setting])
            db.commit()
            observed = []
            ordering = []

            def on_statement(_connection, _cursor, statement, _parameters, _context, _many):
                if "FROM users" in statement:
                    ordering.append("user-read")
                if "FROM characters" in statement:
                    ordering.append("character-read")

            event.listen(engine, "before_cursor_execute", on_statement)
            event.listen(db, "after_commit", lambda _session: ordering.append("commit"))
            reason = "user_requested_tendency_analysis_direct" if lane == "direct" else "user_requested_tendency_analysis"
            result_text = f"{lane} evaluated after commit"

            def result_factory() -> str:
                ordering.append("result")
                with Session(engine) as observer:
                    durable_setting = observer.get(AgentActivitySetting, character.id)
                    assert durable_setting is not None
                    observed.append((durable_setting.tendency_summary, durable_setting.tendency_error, list(observer.scalars(select(AgentActivityLog)))))
                return result_text

            store_tendency_analysis(
                db, setting, user=user, character=character,
                summary="after", action_ranges={"post": {"min": 1, "max": 2}},
                planner_profile={"feed_seed_interest_criteria": "fixture"},
                reason=reason, result_factory=result_factory,
            )
            assert observed == [("after", None, [])]
            assert ordering.index("commit") < ordering.index("user-read") < ordering.index("result")
            assert ordering.index("commit") < ordering.index("character-read") < ordering.index("result")
            assert db.get(AgentActivitySetting, character.id) is setting
            assert setting.tendency_updated_at is not None
            with Session(engine) as observer:
                durable_setting = observer.get(AgentActivitySetting, character.id)
                assert durable_setting is not None
                assert durable_setting.tendency_action_ranges == {"post": {"min": 1, "max": 2}}
                assert durable_setting.planner_tendency_profile == {"feed_seed_interest_criteria": "fixture"}
                log = observer.scalar(select(AgentActivityLog))
                assert log is not None
                assert (log.user_id, log.character_id, log.action_type, log.target_post_id, log.reason, log.result) == (
                    user.id, character.id, "tendency_analyzed", None, reason, result_text,
                )
    finally:
        engine.dispose()
