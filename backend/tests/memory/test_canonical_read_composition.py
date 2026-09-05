"""Canonical reads preserve the current Session while using foreign evidence."""
from app.domains.characters.models import Character
from app.domains.memory.contracts.recall import CanonicalRecallOperation, CanonicalRecallQuery
from app.domains.memory.repository.recall import SqlAlchemyCanonicalRecallRepository, SqlAlchemyMemoryRecallDocumentSource
from app.runtime.memory.recall_queries import read_character_summary_rows
from app.runtime.memory.sqlalchemy_source_reader import SqlAlchemyMemorySourceEvidenceReader, models as source_models
from test_p8_l_h_canonical_recall import NOW, _accept_chat_memory, runtime_factory


def test_character_summary_reads_use_the_current_session_without_committing(runtime_factory):
    scope, counterpart, _, _, _ = _accept_chat_memory(runtime_factory)
    with runtime_factory() as observer:
        original = observer.get(Character, "recall-counterpart-character").one_liner
    calls = []

    def rows(session, query, requested):
        assert session.in_transaction()
        character = session.get(Character, "recall-counterpart-character")
        character.one_liner = "current uncommitted summary"
        session.flush()
        with runtime_factory() as observer:
            assert observer.get(Character, character.id).one_liner == original
        result = read_character_summary_rows(session, query, requested)
        calls.append(requested)
        return result

    repository = SqlAlchemyCanonicalRecallRepository(
        runtime_factory,
        source_reader_factory=SqlAlchemyMemorySourceEvidenceReader,
        character_rows=rows,
    )
    records = repository.execute_direct(
        query=CanonicalRecallQuery(
            operation=CanonicalRecallOperation.GET_CHARACTER_SUMMARIES,
            scope=scope,
            world_character_references=(counterpart,),
            limit=10,
        ),
        now=NOW,
    )
    assert calls == [(counterpart,)]
    assert len(records) == 1
    assert "current uncommitted summary" in records[0].text
    with runtime_factory() as observer:
        assert observer.get(Character, "recall-counterpart-character").one_liner == original


def test_document_hydration_revalidates_evidence_in_its_current_session(runtime_factory):
    _, _, _, message_id, item_id = _accept_chat_memory(runtime_factory)
    with runtime_factory() as observer:
        original = observer.get(source_models.MessageMessage, message_id).content
    calls = []

    def reader(session):
        assert session.in_transaction()
        message = session.get(source_models.MessageMessage, message_id)
        message.content = "uncommitted source change invalidates the saved digest"
        session.flush()
        with runtime_factory() as observer:
            assert observer.get(source_models.MessageMessage, message_id).content == original
        calls.append(message_id)
        return SqlAlchemyMemorySourceEvidenceReader(session)

    documents = SqlAlchemyMemoryRecallDocumentSource(
        runtime_factory, source_reader_factory=reader, now_factory=lambda: NOW
    ).documents_for_item_ids((item_id,))
    assert calls == [message_id]
    assert documents == {item_id: ()}
    with runtime_factory() as observer:
        assert observer.get(source_models.MessageMessage, message_id).content == original
