from types import SimpleNamespace

from app.domains.routines.service import post_selection as post_selection_service
from app.runtime.resident import post_selection as post_selection_runtime


def _invoke_original_session_token(db, **kwargs):
    # Keep the original assertion's opaque Session token; only the test call wiring changes.
    return post_selection_service._select_resident_run_post_id(
        post_selection_runtime.SqlAlchemyPostSelectionReferences(db), **kwargs
    )


agent_run_service = SimpleNamespace(
    _select_resident_run_post_id=_invoke_original_session_token,
)


def test_routine_runtime_does_not_invent_global_selected_post(monkeypatch) -> None:
    monkeypatch.setattr(
        post_selection_runtime,
        "routine_world_character_for_character",
        lambda *_args, **_kwargs: object(),
    )

    def global_fallback_must_not_run(*_args, **_kwargs):
        raise AssertionError("routine runtime must not select a global fallback post")

    monkeypatch.setattr(
        post_selection_service,
        "_select_tick_post_id",
        global_fallback_must_not_run,
    )

    assert (
        agent_run_service._select_resident_run_post_id(
            object(),
            preferred_post_id=None,
            character_id="char-routine",
            scoped_runtime=True,
        )
        is None
    )


def test_non_scoped_runtime_keeps_legacy_post_fallback(monkeypatch) -> None:
    monkeypatch.setattr(
        post_selection_runtime,
        "routine_world_character_for_character",
        lambda *_args, **_kwargs: object(),
    )
    monkeypatch.setattr(
        post_selection_service,
        "_select_tick_post_id",
        lambda *_args, **_kwargs: "post-legacy-fallback",
    )

    assert (
        agent_run_service._select_resident_run_post_id(
            object(),
            preferred_post_id=None,
            character_id="char-legacy",
            scoped_runtime=False,
        )
        == "post-legacy-fallback"
    )
