"""Real file SQLite and filesystem failures; no provider or running data."""
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from threading import Event
from types import SimpleNamespace
import time

import pytest
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from test_card_metadata_compatibility import context, db, isolated_media, duplicate_png
from app.config import settings
from app.domains.characters import models
from app.domains.characters.service import card_import
from app.domains.characters.exceptions import AgentCreationDraftHandleConflictError, AgentCreationDraftExpiredError, AgentCreationDraftValidationError
from app.domains.identity.models import User
from app.integrations.media import card_staging


def test_encoding_once_and_other_writer_progresses_during_prepare(context, monkeypatch):
    session, owner, draft, workflows = context
    owner_id, draft_id, engine = owner.id, draft.id, session.get_bind()
    session.rollback()
    entered, release = Event(), Event()
    original = card_import.encode_profile_media_webp
    calls, sessions, durations = [], [], {}
    def encode(**kwargs):
        calls.append(1)
        assert not sessions[0].in_transaction()
        entered.set()
        assert release.wait(8)
        return original(**kwargs)
    monkeypatch.setattr(card_import, "encode_profile_media_webp", encode)
    def importer():
        with Session(engine) as separate:
            sessions.append(separate)
            return card_import.import_card(separate, SimpleNamespace(id=owner_id), draft_id,
                revision=1, content=duplicate_png(), workflows=workflows)
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(importer)
        try:
            assert entered.wait(8)
            start = time.perf_counter()
            with engine.begin() as writer:
                writer.execute(update(User).where(User.id == owner_id).values(display_name="Other writer finished"))
            durations["independent_writer_ms"] = round((time.perf_counter()-start)*1000, 3)
            assert not future.done()
        finally:
            release.set()
        result = future.result(8)
    assert calls == [1]
    assert result["draft"].revision == 2
    assert session.scalar(select(models.CharacterCardSource.source_bytes)) == duplicate_png()
    assert list(card_staging.staging_root().iterdir()) == []
    print("card_prepare_measurement", durations, "encoding_count=1; writer completed while encoder blocked")


@pytest.mark.parametrize("change,error", [("edit", AgentCreationDraftHandleConflictError),
    ("cancel", AgentCreationDraftHandleConflictError), ("expire", AgentCreationDraftExpiredError),
    ("contract", AgentCreationDraftValidationError)])
def test_prepare_revalidates_fresh_draft_without_committing_claim(context, monkeypatch, change, error):
    session, owner, draft, workflows = context
    engine = session.get_bind()
    original = card_import.prepare_display
    def prepare(**kwargs):
        value = original(**kwargs)
        changes = {"edit": {"revision": 2}, "cancel": {"status": "cancelled"},
            "expire": {"expires_at": datetime.now(UTC)-timedelta(seconds=1)}, "contract": {"contract_version": 1}}[change]
        with engine.begin() as writer:
            writer.execute(update(models.AgentCreationDraft).where(models.AgentCreationDraft.id == draft.id).values(**changes))
        return value
    monkeypatch.setattr(card_import, "prepare_display", prepare)
    with pytest.raises(error):
        card_import.import_card(session, owner, draft.id, revision=1, content=duplicate_png(), workflows=workflows)
    assert session.scalar(select(models.CharacterCardSource)) is None
    assert list(settings.media_root_path.rglob("*.webp")) == []
    assert list(card_staging.staging_root().iterdir()) == []


def test_commit_response_loss_preserves_canonically_referenced_file(context, monkeypatch):
    session, owner, draft, workflows = context
    original = session.commit
    def commit_then_fail():
        original()
        raise RuntimeError("synthetic commit acknowledgement lost")
    monkeypatch.setattr(session, "commit", commit_then_fail)
    with pytest.raises(RuntimeError, match="acknowledgement"):
        card_import.import_card(session, owner, draft.id, revision=1, content=duplicate_png(), workflows=workflows)
    stored = session.get(models.AgentCreationDraft, draft.id)
    assert stored.revision == 2 and stored.avatar_temp_url
    assert len(list(settings.media_root_path.rglob("*.webp"))) == 1
    assert session.scalar(select(models.CharacterCardSource.source_bytes)) == duplicate_png()


@pytest.mark.parametrize("promoted,referenced", [(False, False), (True, False), (True, True)])
def test_crash_cleanup_requires_exclusive_lease_and_rechecks_reference(context, promoted, referenced):
    session, owner, draft, workflows = context
    prepared = card_staging.prepare_display(draft_id=draft.id, encoded=b"synthetic display only")
    if promoted:
        prepared.promote()
    # An arbitrarily old active request remains protected by its OS file lock.
    card_staging.cleanup_staging(lambda url: pytest.fail("active lease must not reach DB lookup"), now=time.time()+7200)
    assert prepared.directory.exists()
    prepared.finish(preserve=True)
    if referenced:
        session.get(models.AgentCreationDraft, draft.id).avatar_temp_url = prepared.url
        session.commit()
    card_staging.cleanup_staging(lambda url: card_import.display_is_referenced(session, url), now=time.time()+7200)
    assert prepared.destination.exists() == referenced
    assert not prepared.directory.exists()


def test_promotion_failure_preserves_draft_and_source(context, monkeypatch):
    session, owner, draft, workflows = context
    def fail(self):
        raise OSError("synthetic rename failure")
    monkeypatch.setattr(card_staging.PreparedDisplay, "promote", fail)
    with pytest.raises(OSError, match="rename"):
        card_import.import_card(session, owner, draft.id, revision=1, content=duplicate_png(), workflows=workflows)
    assert session.get(models.AgentCreationDraft, draft.id).revision == 1
    assert session.scalar(select(models.CharacterCardSource)) is None
    assert list(card_staging.staging_root().iterdir()) == []


def test_staging_cleanup_failure_does_not_turn_committed_import_into_failure(context, monkeypatch):
    from pathlib import Path
    session, owner, draft, workflows = context
    unlink = Path.unlink
    def unavailable(path, *args, **kwargs):
        if path.name == "manifest.json":
            raise OSError("synthetic cleanup unavailable")
        return unlink(path, *args, **kwargs)
    with monkeypatch.context() as patch:
        patch.setattr(Path, "unlink", unavailable)
        card_import.import_card(session, owner, draft.id, revision=1, content=duplicate_png(), workflows=workflows)
    assert session.get(models.AgentCreationDraft, draft.id).revision == 2
    assert session.scalar(select(models.CharacterCardSource.source_bytes)) == duplicate_png()
    assert len(list(settings.media_root_path.rglob("*.webp"))) == 1
    card_staging.cleanup_staging(lambda url: card_import.display_is_referenced(session, url), now=time.time()+7200)
    assert list(card_staging.staging_root().iterdir()) == []
    assert len(list(settings.media_root_path.rglob("*.webp"))) == 1


def test_crash_before_manifest_cleans_only_private_staging(context):
    from uuid import uuid4
    directory = card_staging.staging_root() / uuid4().hex
    directory.mkdir()
    (directory / "display.webp").write_bytes(b"incomplete preparation")
    card_staging.cleanup_staging(lambda url: pytest.fail("no manifest means no canonical file"), now=time.time()+7200)
    assert not directory.exists()


def test_flushed_caller_write_is_not_lost_by_prepare(context):
    session, owner, draft, workflows = context
    session.execute(update(User).where(User.id == owner.id).values(display_name="Caller pending"))
    session.flush()
    assert not session.dirty
    with pytest.raises(RuntimeError, match="card_import_requires_clean_unit_of_work"):
        card_import.import_card(session, owner, draft.id, revision=1, content=duplicate_png(), workflows=workflows)
    assert session.scalar(select(User.display_name).where(User.id == owner.id)) == "Caller pending"
    session.rollback()
    assert session.scalar(select(User.display_name).where(User.id == owner.id)) != "Caller pending"
