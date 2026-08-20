from __future__ import annotations

import ast
from pathlib import Path
import sqlite3

import pytest

from app.domains.runtime.ports.search_index import (
    RebuildableSearchIndexPort,
    SearchIndexDocument,
    SearchIndexQuery,
)
from app.domains.runtime.ports.vector_recall import VectorRecallPort
from app.runtime.persistence.runtime_data_path import StaticRuntimeDataPath
from app.runtime.search.sqlite_fts5 import (
    SqliteFts5SchemaError,
    SqliteFts5SearchIndex,
    SqliteFts5Settings,
)


def _index(tmp_path: Path, *, generation: str = "test-v1") -> SqliteFts5SearchIndex:
    index = SqliteFts5SearchIndex(
        StaticRuntimeDataPath(tmp_path / "Angmoo"),
        settings=SqliteFts5Settings(generation=generation),
    )
    doctor = index.open()
    assert doctor.healthy is True
    assert doctor.fts5_available is True
    return index


def _documents() -> tuple[SearchIndexDocument, ...]:
    return (
        SearchIndexDocument(
            document_id="post-1",
            world_id="world-arcana",
            kind="post",
            text="아르카나 아카데미에서 첫 마법 수업을 열었어요.",
            character_id="char-mango",
            source_id="post-1",
            occurred_at="2026-08-20T01:00:00Z",
            metadata={"visibility": "public", "source": "canonical"},
        ),
        SearchIndexDocument(
            document_id="comment-1",
            world_id="world-arcana",
            kind="comment",
            text="세이지와 도서관에서 별자리 책을 함께 읽었어요.",
            character_id="char-sage",
            counterparty_id="char-mango",
            source_id="comment-1",
            source_event_id="event-comment-1",
            occurred_at="2026-08-20T02:00:00Z",
            metadata={"post_id": "post-1"},
        ),
        SearchIndexDocument(
            document_id="event-1",
            world_id="world-arcana",
            kind="event",
            text="망고와 세이지가 공동 일과를 수락했다.",
            character_id="char-mango",
            counterparty_id="char-sage",
            source_id="social-event-1",
            source_event_id="social-event-1",
            occurred_at="2026-08-20T03:00:00Z",
            metadata={"event_type": "routine_accepted"},
        ),
        SearchIndexDocument(
            document_id="memory-1",
            world_id="world-arcana",
            kind="memory",
            text="세이지는 망고가 도서관에서 건넨 도움을 기억한다.",
            character_id="char-sage",
            counterparty_id="char-mango",
            source_id="memory-1",
            source_event_id="social-event-1",
            occurred_at="2026-08-20T04:00:00Z",
            metadata={"memory_type": "relationship"},
        ),
        SearchIndexDocument(
            document_id="post-other-world",
            world_id="world-other",
            kind="post",
            text="아르카나 아카데미에서 세이지를 만났어요.",
            character_id="char-mango",
            source_id="post-other-world",
            occurred_at="2026-08-20T05:00:00Z",
            metadata={"visibility": "public"},
        ),
        SearchIndexDocument(
            document_id="post-hidden",
            world_id="world-arcana",
            kind="post",
            text="검색되면 안 되는 숨김 마법 기록",
            character_id="char-mango",
            source_id="post-hidden",
            searchable=False,
            metadata={"visibility": "hidden"},
        ),
    )


def test_fts5_projection_is_separate_rebuildable_and_has_stable_digest(
    tmp_path: Path,
) -> None:
    index = _index(tmp_path)
    assert isinstance(index, RebuildableSearchIndexPort)
    assert index.database_path == (
        tmp_path
        / "Angmoo"
        / "search"
        / "generations"
        / "test-v1"
        / "angmoo-search.sqlite3"
    )
    assert "canonical" not in index.database_path.parts

    first = index.rebuild(_documents())
    assert first.healthy is True
    assert first.document_count == first.indexed_document_count == 5
    assert "CJK bigram" in first.tokenizer_strategy

    second = index.rebuild(reversed(_documents()))
    assert second.healthy is True
    assert second.digest == first.digest

    index.checkpoint(truncate=True)
    index.close()
    reopened = _index(tmp_path)
    assert reopened.doctor().digest == first.digest


def test_cjk_fallback_provenance_and_all_scope_filters(tmp_path: Path) -> None:
    index = _index(tmp_path)
    index.rebuild(_documents())

    academy = index.search(
        world_id="world-arcana", query="아카데미", limit=10
    )
    assert [hit.document_id for hit in academy] == ["post-1"]
    assert academy[0].world_id == "world-arcana"
    assert academy[0].kind == "post"
    assert academy[0].source_id == "post-1"
    assert academy[0].metadata == {
        "source": "canonical",
        "visibility": "public",
    }

    other_world = index.search(
        world_id="world-other", query="아카데미", limit=10
    )
    assert [hit.document_id for hit in other_world] == ["post-other-world"]

    scoped = index.search_scoped(
        SearchIndexQuery(
            world_id="world-arcana",
            text="세이지",
            character_id="char-sage",
            counterparty_id="char-mango",
            kinds=("comment", "memory"),
            limit=10,
        )
    )
    assert {hit.document_id for hit in scoped} == {"comment-1", "memory-1"}
    assert all(hit.source_event_id for hit in scoped)

    # FTS token matching cannot satisfy a Latin prefix.  The deterministic
    # normalized substring fallback still keeps the query inside the World.
    index.upsert(
        SearchIndexDocument(
            document_id="post-latin",
            world_id="world-arcana",
            kind="post",
            text="Academy observatory notes",
            metadata={"source": "canonical"},
        )
    )
    fallback = index.search(
        world_id="world-arcana", query="acad", limit=10
    )
    assert [hit.document_id for hit in fallback] == ["post-latin"]


def test_hidden_deleted_and_tombstoned_documents_are_excluded_immediately(
    tmp_path: Path,
) -> None:
    index = _index(tmp_path)
    index.rebuild(_documents())
    assert index.search(
        world_id="world-arcana", query="숨김", limit=10
    ) == ()

    assert index.search(
        world_id="world-arcana", query="별자리", limit=10
    )
    index.remove(document_id="comment-1")
    assert index.search(
        world_id="world-arcana", query="별자리", limit=10
    ) == ()

    index.upsert(
        SearchIndexDocument(
            document_id="event-1",
            world_id="world-arcana",
            kind="event",
            text="망고와 세이지가 공동 일과를 수락했다.",
            searchable=False,
            metadata={"tombstone": "true"},
        )
    )
    assert index.search(
        world_id="world-arcana", query="공동 일과", limit=10
    ) == ()
    assert index.doctor().healthy is True


def test_doctor_detects_projection_drift_and_rebuild_repairs_it(tmp_path: Path) -> None:
    index = _index(tmp_path)
    index.rebuild(_documents())
    with sqlite3.connect(index.database_path) as connection:
        connection.execute(
            "UPDATE search_documents SET text = ? WHERE document_id = ?",
            ("tampered", "post-1"),
        )
    drifted = index.doctor()
    assert drifted.healthy is False
    assert drifted.digest_matches is False

    repaired = index.rebuild(_documents())
    assert repaired.healthy is True
    assert repaired.digest_matches is True

    with sqlite3.connect(index.database_path) as connection:
        connection.execute(
            "UPDATE search_documents_fts SET text = ? WHERE document_id = ?",
            ("index drift", "post-1"),
        )
    fts_drifted = index.doctor()
    assert fts_drifted.healthy is False
    assert fts_drifted.digest_matches is True
    assert index.rebuild(_documents()).healthy is True


def test_duplicate_rebuild_and_unversioned_projection_fail_closed(
    tmp_path: Path,
) -> None:
    index = _index(tmp_path)
    document = _documents()[0]
    with pytest.raises(ValueError, match="duplicate search document"):
        index.rebuild((document, document))

    unversioned = SqliteFts5SearchIndex(
        StaticRuntimeDataPath(tmp_path / "Unversioned"),
        settings=SqliteFts5Settings(generation="bad-v1"),
    )
    unversioned.database_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(unversioned.database_path) as connection:
        connection.execute("CREATE TABLE unexpected (id INTEGER PRIMARY KEY)")
    with pytest.raises(SqliteFts5SchemaError, match="unversioned"):
        unversioned.open()


def test_vector_recall_is_a_domain_port_only_and_has_no_runtime_adapter() -> None:
    assert isinstance(VectorRecallPort, type)
    app_root = Path(__file__).parents[1] / "app"
    port_path = app_root / "domains" / "runtime" / "ports" / "vector_recall.py"
    tree = ast.parse(port_path.read_text(encoding="utf-8"), filename=str(port_path))
    imports = [
        node.module
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module
    ]
    assert not any(
        imported.startswith(("app.runtime", "app.integrations", "app.models"))
        for imported in imports
    )
    assert not (app_root / "runtime" / "search" / "vector_recall.py").exists()


def test_fts_query_syntax_is_quoted_instead_of_executed(tmp_path: Path) -> None:
    index = _index(tmp_path)
    before = index.rebuild(_documents())
    assert index.search(
        world_id="world-arcana",
        query='" OR * NOT (',
        limit=10,
    ) == ()
    after = index.doctor()
    assert after.healthy is True
    assert after.digest == before.digest
