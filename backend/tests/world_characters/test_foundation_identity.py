"""Compatibility identities used by frozen migration and provider substitution."""
from app import models as registered_models
from app.core.db import Base
from app.domains.world_characters import client, models
from app.domains.world_characters.contracts import provider
from app.domains.world_characters.infrastructure import sqlalchemy_models as old_identity
from app.domains.world_characters.infrastructure import sqlalchemy_setup_models as old_setup


def test_frozen_migration_and_registry_use_the_same_six_model_classes() -> None:
    for name in ("WorldCharacter", "CharacterActiveWorld"):
        canonical = getattr(models, name)
        assert getattr(old_identity, name) is canonical
        assert getattr(registered_models, name) is canonical
        assert canonical.metadata is Base.metadata
        assert Base.metadata.tables[canonical.__tablename__] is canonical.__table__
    for name in ("WorldCommunityProfile", "WorldActivityRepertoire",
                 "WorldActivityCandidate", "WorldCharacterSetupAttempt"):
        canonical = getattr(models, name)
        assert getattr(old_setup, name) is canonical
        assert getattr(registered_models, name) is canonical
        assert canonical.metadata is Base.metadata
        assert Base.metadata.tables[canonical.__tablename__] is canonical.__table__


def test_provider_compatibility_keeps_monkeypatch_target_and_accounting_types(monkeypatch) -> None:
    from app.services import world_character_provider as old_provider

    assert old_provider is client
    assert client.WorldCharacterProviderResult is provider.WorldCharacterProviderResult
    assert client.WorldCharacterSetupProvider is provider.WorldCharacterSetupProvider
    original = client.DirectLlmWorldCharacterSetupProvider
    sentinel = object()
    monkeypatch.setattr(old_provider, "DirectLlmWorldCharacterSetupProvider", sentinel)
    assert client.DirectLlmWorldCharacterSetupProvider is sentinel
    assert original is not sentinel
