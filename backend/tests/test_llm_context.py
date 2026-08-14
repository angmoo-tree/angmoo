from app.services.llm_context import neutralize_context_text


def test_neutralize_context_text_trims_spaces_around_newlines() -> None:
    assert neutralize_context_text("first   \n   second") == "first\nsecond"


def test_neutralize_context_text_handles_long_space_runs_linearly() -> None:
    padding = " " * 100_000
    assert neutralize_context_text(f"first{padding}\n{padding}second") == "first\nsecond"
