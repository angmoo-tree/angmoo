import asyncio
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from app.services import character_lore
from app.services import direct_llm


class _FakeLoreDb:
    def __init__(self, *, existing_sources=None):
        self.existing_sources = list(existing_sources or [])
        self.added = []
        self.deleted = []
        self.committed = False

    def scalar(self, _query):
        return None

    def scalars(self, _query):
        return iter(self.existing_sources)

    def add(self, value):
        self.added.append(value)

    def delete(self, value):
        self.deleted.append(value)

    def commit(self):
        self.committed = True

    def refresh(self, value):
        now = datetime(2026, 6, 4, tzinfo=UTC)
        value.created_at = now
        value.updated_at = now


def _lore_user_and_character(monkeypatch):
    user = SimpleNamespace(id="user-1")
    character = SimpleNamespace(id="char-1", owner_id="user-1")
    monkeypatch.setattr(
        character_lore,
        "_get_owned_character",
        lambda *args, **kwargs: character,
    )
    monkeypatch.setattr(character_lore, "_total_text_chars", lambda *args, **kwargs: 0)
    monkeypatch.setattr(character_lore, "_chunk_count", lambda *args, **kwargs: 0)
    monkeypatch.setattr(
        character_lore,
        "_store_chunks_with_embeddings",
        lambda *args, **kwargs: setattr(kwargs["source"], "status", "ready"),
    )
    return user, character


def test_chunk_lore_text_keeps_freeform_lines_without_llm():
    text = """
# 취향
비 오는 날에는 오래된 만년필을 정리한다.
그때마다 잉크 냄새 때문에 예전 작업실을 떠올린다.

- 좋아하는 물건은 흠집 난 은색 라이터다.
Q: 혼자 있을 때 하는 일은?
A: 창가에 앉아 그날의 소리를 기억한다.
"""

    drafts = character_lore.chunk_lore_text(text)
    joined = "\n".join(draft.text for draft in drafts)

    assert drafts
    assert all(0 < len(draft.text) <= character_lore.TARGET_CHUNK_MAX_CHARS for draft in drafts)
    assert "만년필" in joined
    assert "은색 라이터" in joined
    assert "창가에 앉아" in joined
    assert any(draft.section_hint == "취향" for draft in drafts)


def test_lore_source_limit_is_one_file_per_character():
    assert character_lore.MAX_LORE_SOURCES_PER_CHARACTER == 1


def test_lore_prompt_context_can_be_compacted_for_post_writer():
    chunks = tuple(
        character_lore.RetrievedLoreChunk(
            id=f"lore-chunk-{index}",
            source_id="lore-source-1",
            source_filename="memo.md",
            section_hint="notes",
            text=f"chunk {index} " + ("x" * 80),
            distance=0.1,
        )
        for index in range(1, 5)
    )
    result = character_lore.LoreRetrievalResult(mode="pgvector", chunks=chunks)

    context = character_lore.format_lore_prompt_context(
        result,
        lore_query_mode="llm_rewrite",
        max_chunks=3,
        max_text_chars=20,
    )

    assert "lore_query_mode: llm_rewrite" in context
    assert "lore-chunk-1" in context
    assert "lore-chunk-3" in context
    assert "lore-chunk-4" not in context
    assert "chunk 1 xxxxxxxxxxxx" in context
    assert "source filenames" in context


def test_lore_chunk_limit_is_one_hundred():
    assert character_lore.MAX_LORE_TEXT_CHARS_PER_CHARACTER == 50_000
    assert character_lore.MAX_LORE_CHUNKS_PER_CHARACTER == 100
    assert character_lore.TARGET_CHUNK_MIN_CHARS == 500
    assert character_lore.TARGET_CHUNK_TARGET_CHARS == 750
    assert character_lore.TARGET_CHUNK_MAX_CHARS == 1000


def test_chunk_lore_text_packs_same_section_until_target_size():
    paragraphs = ["a" * 190, "b" * 190, "c" * 190, "d" * 190]
    text = "# notes\n" + "\n\n".join(paragraphs)

    drafts = character_lore.chunk_lore_text(text)

    assert len(drafts) == 1
    assert drafts[0].section_hint == "notes"
    assert len(drafts[0].text) >= character_lore.TARGET_CHUNK_TARGET_CHARS
    assert all(paragraph in drafts[0].text for paragraph in paragraphs)


def test_chunk_lore_text_flushes_before_next_unit_exceeds_max():
    text = "# notes\n" + ("a" * 600) + "\n\n" + ("b" * 500)

    drafts = character_lore.chunk_lore_text(text)

    assert [len(draft.text) for draft in drafts] == [600, 500]
    assert all(draft.section_hint == "notes" for draft in drafts)


def test_chunk_lore_text_keeps_section_boundaries():
    text = "# first\n" + ("a" * 600) + "\n\n# second\n" + ("b" * 600)

    drafts = character_lore.chunk_lore_text(text)

    assert len(drafts) == 2
    assert [draft.section_hint for draft in drafts] == ["first", "second"]
    assert "a" * 20 in drafts[0].text
    assert "b" * 20 in drafts[1].text


def test_chunk_lore_text_splits_long_fiction_paragraph_by_sentence():
    sentence = "a" * 450 + "."
    text = "# fiction\n" + " ".join([sentence, sentence, sentence])

    drafts = character_lore.chunk_lore_text(text)

    assert len(drafts) == 2
    assert all(0 < len(draft.text) <= character_lore.TARGET_CHUNK_MAX_CHARS for draft in drafts)
    assert drafts[0].text.count(".") == 2
    assert drafts[1].text.count(".") == 1


def test_chunk_lore_text_force_splits_single_long_sentence():
    text = "# long\n" + ("x" * 2200)

    drafts = character_lore.chunk_lore_text(text)

    assert [len(draft.text) for draft in drafts] == [1000, 1000, 200]
    assert all(draft.section_hint == "long" for draft in drafts)


def test_lore_chunk_limit_accepts_one_hundred_chunks(monkeypatch):
    monkeypatch.setattr(character_lore, "_total_text_chars", lambda *args, **kwargs: 0)
    monkeypatch.setattr(character_lore, "_chunk_count", lambda *args, **kwargs: 0)

    character_lore._ensure_character_limits(
        None,
        character_id="char-1",
        new_text_chars=100,
        new_chunk_count=100,
    )


def test_lore_chunk_limit_rejects_more_than_one_hundred_chunks(monkeypatch):
    monkeypatch.setattr(character_lore, "_total_text_chars", lambda *args, **kwargs: 0)
    monkeypatch.setattr(character_lore, "_chunk_count", lambda *args, **kwargs: 0)

    with pytest.raises(character_lore.CharacterLoreValidationError) as exc:
        character_lore._ensure_character_limits(
            None,
            character_id="char-1",
            new_text_chars=100,
            new_chunk_count=101,
        )

    assert "100" in str(exc.value)


def test_lore_text_limit_rejects_more_than_fifty_thousand_chars(monkeypatch):
    monkeypatch.setattr(character_lore, "_total_text_chars", lambda *args, **kwargs: 0)
    monkeypatch.setattr(character_lore, "_chunk_count", lambda *args, **kwargs: 0)

    with pytest.raises(character_lore.CharacterLoreValidationError) as exc:
        character_lore._ensure_character_limits(
            None,
            character_id="char-1",
            new_text_chars=50_001,
            new_chunk_count=1,
        )

    assert "50,000" in str(exc.value)


def test_lore_status_reports_one_hundred_max_chunks(monkeypatch):
    monkeypatch.setattr(character_lore, "_source_count", lambda *args, **kwargs: 0)
    monkeypatch.setattr(character_lore, "_chunk_count", lambda *args, **kwargs: 0)
    monkeypatch.setattr(character_lore, "_ready_chunk_count", lambda *args, **kwargs: 0)

    status = character_lore._status_read(_FakeLoreDb(), "char-1")

    assert status.max_chunks == 100


def test_upload_lore_source_rejects_second_file_without_replace(monkeypatch):
    user, _character = _lore_user_and_character(monkeypatch)
    existing = SimpleNamespace(extracted_char_count=100, chunk_count=1)
    db = _FakeLoreDb(existing_sources=[existing])

    with pytest.raises(character_lore.CharacterLoreValidationError) as exc:
        character_lore.upload_lore_source(
            db,
            user,
            "char-1",
            filename="next.md",
            content_type="text/markdown",
            file_bytes=b"new lore",
        )

    assert "1개만" in str(exc.value)
    assert db.deleted == []
    assert db.added == []


def test_upload_lore_source_replaces_existing_after_new_file_validation(monkeypatch):
    user, _character = _lore_user_and_character(monkeypatch)
    existing = SimpleNamespace(extracted_char_count=100, chunk_count=1)
    db = _FakeLoreDb(existing_sources=[existing])

    source = character_lore.upload_lore_source(
        db,
        user,
        "char-1",
        filename="next.md",
        content_type="text/markdown",
        file_bytes=b"new lore",
        replace_existing=True,
    )

    assert db.deleted == [existing]
    assert len(db.added) == 1
    assert db.committed is True
    assert source.filename == "next.md"
    assert source.status == "ready"


def test_upload_lore_source_keeps_existing_when_replacement_validation_fails(monkeypatch):
    user, _character = _lore_user_and_character(monkeypatch)
    existing = SimpleNamespace(extracted_char_count=100, chunk_count=1)
    db = _FakeLoreDb(existing_sources=[existing])

    with pytest.raises(character_lore.CharacterLoreValidationError):
        character_lore.upload_lore_source(
            db,
            user,
            "char-1",
            filename="oversize.md",
            content_type="text/markdown",
            file_bytes=b"x" * (character_lore.MAX_LORE_FILE_BYTES + 1),
            replace_existing=True,
        )

    assert db.deleted == []
    assert db.added == []


def test_embedding_inputs_use_embedding_2_prefix_contract():
    draft = character_lore.LoreChunkDraft(
        section_hint="관계",
        text="낡은 기차역에서 약속을 자주 떠올린다.",
        content_hash="hash",
    )

    assert character_lore._chunk_embedding_input(draft).startswith("title: 관계 | text: ")
    assert character_lore._query_embedding_input("독립글 소재").startswith(
        "task: search result | query: "
    )


def test_retrieve_lore_for_query_tracked_records_embedding_success(monkeypatch):
    direct_llm._RATE_LIMITER._buckets.clear()
    tracker = direct_llm.RunLlmTracker(max_calls=1)
    character = SimpleNamespace(id="char-1")

    monkeypatch.setattr(character_lore, "_ready_chunk_count", lambda *_args: 1)
    monkeypatch.setattr(
        character_lore,
        "_google_embedding_credential_for_character",
        lambda *_args: character_lore._GoogleEmbeddingCredential(
            api_key="key",
            credential_id="cred-1",
            key_fingerprint="fp-1",
            provider="google",
        ),
    )
    monkeypatch.setattr(
        character_lore,
        "_embed_text",
        lambda _api_key, _text: [0.1] * character_lore.EMBEDDING_DIMENSION,
    )
    monkeypatch.setattr(
        character_lore,
        "_retrieve_lore_rows",
        lambda *_args, **_kwargs: ["row-1"],
    )
    monkeypatch.setattr(
        character_lore,
        "_lore_result_from_rows",
        lambda _rows: character_lore.LoreRetrievalResult(
            mode="pgvector",
            chunks=(
                character_lore.RetrievedLoreChunk(
                    id="lore-chunk-1",
                    source_id="lore-source-1",
                    source_filename="memo.md",
                    section_hint="memo",
                    text="chunk",
                    distance=0.1,
                ),
            ),
        ),
    )

    result = asyncio.run(
        character_lore.retrieve_lore_for_query_tracked(
            object(),
            character=character,
            query="quiet memory",
            tracker=tracker,
            agent_run_id="run-1",
        )
    )

    summary = tracker.summary()
    assert result.mode == "pgvector"
    assert summary["call_count"] == 0
    assert summary["embedding_call_count"] == 1
    assert summary["provider_call_count"] == 1
    assert summary["calls"][0]["call_type"] == "embed_content"
    assert summary["calls"][0]["node"] == "CharacterLoreEmbedding"
    assert summary["calls"][0]["model"] == character_lore.EMBEDDING_MODEL


def test_retrieve_lore_for_query_tracked_records_embedding_failure(monkeypatch):
    direct_llm._RATE_LIMITER._buckets.clear()
    tracker = direct_llm.RunLlmTracker(max_calls=1)
    character = SimpleNamespace(id="char-1")

    def fail_embed(_api_key, _text):
        raise RuntimeError("embedding failed")

    monkeypatch.setattr(character_lore, "_ready_chunk_count", lambda *_args: 1)
    monkeypatch.setattr(
        character_lore,
        "_google_embedding_credential_for_character",
        lambda *_args: character_lore._GoogleEmbeddingCredential(
            api_key="key",
            credential_id="cred-1",
            key_fingerprint="fp-1",
            provider="google",
        ),
    )
    monkeypatch.setattr(character_lore, "_embed_text", fail_embed)

    result = asyncio.run(
        character_lore.retrieve_lore_for_query_tracked(
            object(),
            character=character,
            query="quiet memory",
            tracker=tracker,
            agent_run_id="run-1",
        )
    )

    summary = tracker.summary()
    assert result.mode == "fallback_embedding_failed"
    assert summary["call_count"] == 0
    assert summary["embedding_call_count"] == 1
    assert summary["provider_call_count"] == 1
    assert summary["calls"][0]["status"] == "error"
    assert summary["calls"][0]["failure_class"] == "RuntimeError"


def test_self_update_query_excludes_feed_scan_context(monkeypatch):
    monkeypatch.setattr(
        character_lore.community_service,
        "format_recent_own_root_topic_history_for_prompt",
        lambda *args, **kwargs: "최근 자기 root topic",
    )
    monkeypatch.setattr(
        character_lore,
        "_format_recent_lore_usage",
        lambda *args, **kwargs: "최근 lore usage",
    )

    query = character_lore.build_lore_search_query(
        None,
        character=SimpleNamespace(
            id="char-1",
            name="데쿠",
            persona_summary="조심스럽지만 기록을 좋아한다.",
            personality="세심함",
            speech_style="짧게 중얼거림",
            worldview="작은 사건을 오래 기억한다.",
            topic_preferences="관찰, 물건, 습관",
        ),
        now=datetime(2026, 6, 4, 3, 0, tzinfo=UTC),
    )

    assert "독립 root 글" in query
    assert "최근 자기 root topic" in query
    assert "최근 lore usage" in query
    assert "feed_scan" not in query
    assert "post_seed" not in query
    assert "interests" not in query
    assert "커뮤니티 분위기" not in query
