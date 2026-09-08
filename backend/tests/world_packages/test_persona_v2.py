from dataclasses import replace
from io import BytesIO
from zipfile import ZipFile

import pytest
from pydantic import ValidationError
from app.domains.characters.contracts import PERSONA_LIMITS
from app.domains.characters.schemas import AgentCreationDraftUpdate, AgentProfileUpdate, AgentPersonaUpdate
from app.domains.world_packages.schemas.content_v2 import AutonomousCharacterTemplateV2
from app.domains.world_packages.schemas.manifest import WorldPackageManifest, WorldPackageLicense
from app.domains.world_packages.archive.validation import ZipWorldPackageImportValidator
from app.domains.world_packages.exceptions import WorldPackageContractError, WorldPackageReasonCode
from world_packages.test_export import _portable_snapshot, _FakeSource, _FakeRegistry, _exporter
from world_packages.test_preview import _stage, OPERATION_ID


@pytest.mark.parametrize("field,limit", list(PERSONA_LIMITS.items()))
def test_write_limits_count_normalized_codepoints(field, limit):
    payload = {field: "😀" * limit}
    assert getattr(AgentCreationDraftUpdate.model_validate(payload), field) == payload[field]
    with pytest.raises(ValidationError):
        AgentCreationDraftUpdate.model_validate({field: "😀" * (limit + 1)})
    # CRLF and decomposed Hangul are normalized before counting.
    normalized = AgentCreationDraftUpdate.model_validate({field: "가\r\n" * (limit // 2)})
    assert getattr(normalized, field) == "가\n" * (limit // 2)


def test_profile_and_persona_apis_share_limits():
    assert len(AgentProfileUpdate(one_liner="x" * 500).one_liner) == 500
    assert len(AgentPersonaUpdate(personality="x" * 6000).personality) == 6000
    with pytest.raises(ValidationError): AgentProfileUpdate(one_liner="x" * 501)
    with pytest.raises(ValidationError): AgentPersonaUpdate(personality="x" * 6001)


def test_fifty_maximum_personas_export_import_without_loss(tmp_path):
    snapshot = _portable_snapshot()
    values = {key: "😀" * maximum for key, maximum in PERSONA_LIMITS.items()}
    characters = tuple(AutonomousCharacterTemplateV2(
        ref=f"characters/bird-{index}", display_name=f"Bird {index}", handle_hint=f"bird_{index}",
        **values, persona_summary="😀" * 32000,
    ) for index in range(50))
    seeds = tuple(snapshot.world_characters[0].model_copy(update={"character_ref": item.ref}) for item in characters)
    snapshot = replace(snapshot, characters=characters, world_characters=seeds, media_candidates=())
    exporter = _exporter(_FakeSource(snapshot), _FakeRegistry())
    _, archive = exporter.build(source_world_id=snapshot.source_world_id, local_owner_id="private-owner-id",
        license=WorldPackageLicense(expression="CC-BY-4.0", attribution="Fixture creator"), license_text=None)
    assert archive.manifest.format_version == 2
    with ZipFile(BytesIO(archive.content)) as zip_file:
        assert 2 * 1024 * 1024 < zip_file.getinfo("content/characters.json").file_size < 32 * 1024 * 1024
        with pytest.raises(ValidationError):
            WorldPackageManifest.model_validate_json(zip_file.read("manifest.json"))
    store, _, _ = _stage(tmp_path, archive.content)
    imported = ZipWorldPackageImportValidator(store).validate(operation_id=OPERATION_ID)
    assert len(imported.characters.characters) == 50
    assert imported.characters.characters[0].model_dump() == characters[0].model_dump()


def test_invalid_legacy_persona_produces_safe_field_error():
    snapshot = _portable_snapshot()
    invalid = snapshot.characters[0].model_copy(update={"persona_summary": "private-text-" * 4000})
    exporter = _exporter(_FakeSource(replace(snapshot, characters=(invalid,))), _FakeRegistry())
    with pytest.raises(WorldPackageContractError) as error:
        exporter.preview(source_world_id=snapshot.source_world_id, local_owner_id="private-owner-id",
            license=WorldPackageLicense(expression="CC-BY-4.0", attribution="Fixture creator"), license_text=None)
    assert error.value.reason_code == WorldPackageReasonCode.PERSONA_INVALID
    assert error.value.fields == ({"field": "persona_summary", "limit": 32000, "actual": 52000},)
    assert "private-text" not in str(error.value)


@pytest.mark.parametrize("field,limit", [("topic_preferences", 3000), ("safety_rules", 4000)])
@pytest.mark.parametrize("extra", [0, 1], ids=["within-budget", "over-budget"])
def test_v1_list_text_is_admitted_before_preview_or_rejected_with_safe_details(tmp_path, field, limit, extra):
    import json
    from app.domains.world_packages.schemas.content import CharactersDocument
    from app.domains.world_packages.utils.canonical import canonical_json_bytes
    from world_packages.test_preview import _archive, _payloads, _replace_indexed_payload

    payloads = _payloads(_archive())
    document = json.loads(payloads["content/characters.json"])
    document["characters"][0][field] = ["😀" * (limit + extra)]
    # This is structurally valid v1, including its historically unbounded items.
    CharactersDocument.model_validate(document)
    content = _replace_indexed_payload(payloads, path="content/characters.json", content=canonical_json_bytes(document))
    if extra:
        with pytest.raises(WorldPackageContractError) as failure:
            _stage(tmp_path, content)
        assert failure.value.reason_code == WorldPackageReasonCode.PERSONA_INVALID
        assert failure.value.fields == ({"field": field, "limit": limit, "actual": limit + extra},)
        assert "😀" not in str(failure.value)
    else:
        store, _, _ = _stage(tmp_path, content)
        package = ZipWorldPackageImportValidator(store).validate(operation_id=OPERATION_ID)
        assert package.manifest.format_version == 1
        assert getattr(package.characters.characters[0], field) == document["characters"][0][field]
