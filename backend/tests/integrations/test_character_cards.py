import base64
import hashlib
import io
import json
import struct
import zlib

import pytest
from PIL import Image

from app.integrations.character_cards import parser
from app.integrations.character_cards.parser import MAX_FILE_BYTES, CardParseError, parse_card
from app.domains.characters.service.card_mapping import map_card


def card(version=2):
    data = dict(name="하루 🌷", description="{{char}}는 기자", personality="",
                scenario="학교", first_mes="안녕", mes_example="{{char}}: 안녕 {{user}}")
    if version == 1:
        return data
    return dict(spec=f"chara_card_v{version}", spec_version=f"{version}.0", data=data)


def encoded(value):
    return json.dumps(value, ensure_ascii=False).encode()


def chunk(kind, payload):
    return struct.pack(">I", len(payload)) + kind + payload + struct.pack(">I", zlib.crc32(kind + payload))


def png(*metadata):
    output = io.BytesIO()
    Image.new("RGB", (2, 2)).save(output, format="PNG")
    raw = output.getvalue()
    return raw[:-12] + b"".join(chunk(b"tEXt", key + b"\0" + value) for key, value in metadata) + raw[-12:]


@pytest.mark.parametrize("version", [1, 2, 3])
@pytest.mark.parametrize("image", [False, True])
def test_versions_and_unicode(version, image):
    raw = encoded(card(version))
    if image:
        raw = png((b"ccv3" if version == 3 else b"chara", base64.b64encode(raw)))
    parsed = parse_card(raw)
    assert parsed.version == version
    assert parsed.data["name"] == "하루 🌷"
    assert parsed.source_format == ("png" if image else "json")


def test_v3_preferred_and_corrupt_v3_does_not_fall_back():
    raw = png((b"chara", base64.b64encode(encoded(card(2)))),
              (b"ccv3", base64.b64encode(encoded(card(3)))))
    assert parse_card(raw).version == 3
    with pytest.raises(CardParseError, match="base64"):
        parse_card(png((b"chara", base64.b64encode(encoded(card(2)))), (b"ccv3", b"!")))


def test_duplicate_json_keys_rejected():
    with pytest.raises(CardParseError, match="duplicate_json_key"):
        parse_card(b'{"name":"one","name":"two"}')


@pytest.mark.parametrize("keyword,version", [(b"chara", 2), (b"ccv3", 3)])
@pytest.mark.parametrize("identical", [False, True])
def test_duplicate_metadata_selects_first_and_preserves_source(keyword, version, identical):
    first = card(version)
    second = card(version)
    if not identical:
        second["data"]["name"] = "Different character"
    first_json = encoded(first)
    raw = png((keyword, base64.b64encode(first_json)),
              (keyword.upper(), base64.b64encode(encoded(second))))
    result = parse_card(raw)
    assert result.document == first
    assert result.source_sha256 == hashlib.sha256(raw).hexdigest()
    assert result.parser_version == "angmoo-card-import-v2"
    selection = result.metadata_selection
    assert selection.keyword == keyword.decode()
    assert selection.selected_occurrence == 0
    assert selection.same_keyword_count == 2
    assert selection.multiple_definitions is True
    assert selection.selected_json_sha256 == hashlib.sha256(first_json).hexdigest()


def test_duplicate_order_is_physical_not_recency_or_validity():
    first, second = card(), card()
    first["data"]["name"] = "First"
    first["data"]["modification_date"] = 1
    second["data"]["name"] = "Second"
    second["data"]["modification_date"] = 999
    entries = [(b"chara", base64.b64encode(encoded(item))) for item in (first, second)]
    assert parse_card(png(*entries)).data["name"] == "First"
    assert parse_card(png(*reversed(entries))).data["name"] == "Second"


@pytest.mark.parametrize("bad", [b"!", base64.b64encode(b"not json"),
    base64.b64encode(encoded({"spec": "chara_card_v9"})),
    base64.b64encode(encoded({**card(), "data": {**card()["data"], "name": " "}}))])
@pytest.mark.parametrize("keyword,version", [(b"chara", 2), (b"ccv3", 3)])
def test_invalid_preferred_definition_never_falls_back(keyword, version, bad):
    good = base64.b64encode(encoded(card(version)))
    fallback = [(b"chara", base64.b64encode(encoded(card())))] if keyword == b"ccv3" else []
    with pytest.raises(CardParseError):
        parse_card(png(*fallback, (keyword, bad), (keyword, good)))


@pytest.mark.parametrize("unused", [b"!", base64.b64encode(b"not json")])
def test_unused_payload_is_not_decoded_but_its_crc_is_checked(unused):
    valid = base64.b64encode(encoded(card()))
    raw = png((b"chara", valid), (b"chara", unused))
    assert parse_card(raw).document == card()
    broken = bytearray(raw)
    broken[-13] ^= 1  # The unused tEXt CRC, before IEND.
    with pytest.raises(CardParseError, match="crc"):
        parse_card(bytes(broken))


def test_both_keywords_and_duplicates_prefer_first_v3():
    entries = []
    for keyword, version, name in [(b"chara", 2, "A"), (b"chara", 2, "B"),
                                   (b"ccv3", 3, "C"), (b"ccv3", 3, "D")]:
        value = card(version)
        value["data"]["name"] = name
        entries.append((keyword, base64.b64encode(encoded(value))))
    selected = parse_card(png(*entries))
    assert selected.data["name"] == "C"
    assert selected.metadata_selection.keyword == "ccv3"
    assert selected.metadata_selection.same_keyword_count == 2
    single_per_key = parse_card(png(entries[0], entries[2]))
    assert single_per_key.metadata_selection.multiple_definitions is False
    assert parse_card(encoded(card())).metadata_selection is None


@pytest.mark.parametrize("suffix", [b"trailing", b"", chunk(b"IEND", b"x")])
def test_complete_container_must_end_correctly(suffix):
    raw = png((b"chara", base64.b64encode(encoded(card()))))
    invalid = raw + suffix if suffix == b"trailing" else raw[:-12] + suffix
    with pytest.raises(CardParseError):
        parse_card(invalid)


@pytest.mark.parametrize("constant", [b"NaN", b"Infinity", b"-Infinity", b"1e9999"])
def test_nonfinite_json_numbers_rejected(constant):
    with pytest.raises(CardParseError, match="invalid_json_number"):
        parse_card(b'{"extra":' + constant + b'}')


@pytest.mark.parametrize("limit", ["MAX_TEXT_BYTES", "MAX_TOTAL_TEXT_BYTES", "MAX_CHUNKS"])
def test_png_limits_count_all_definitions(monkeypatch, limit):
    value = base64.b64encode(encoded(card()))
    raw = png((b"chara", value), (b"chara", value))
    bound = len(value) + 6 if limit == "MAX_TEXT_BYTES" else 2 * (len(value) + 6) if limit == "MAX_TOTAL_TEXT_BYTES" else 5
    monkeypatch.setattr(parser, limit, bound)
    assert parse_card(raw).metadata_selection.same_keyword_count == 2
    monkeypatch.setattr(parser, limit, bound - 1)
    with pytest.raises(CardParseError):
        parse_card(raw)


def test_selected_base64_is_bounded_before_decode(monkeypatch):
    raw_json = encoded(card())
    raw = png((b"chara", base64.b64encode(raw_json)))
    monkeypatch.setattr(parser, "MAX_JSON_BYTES", len(raw_json))
    assert parse_card(raw).document == card()
    monkeypatch.setattr(parser, "MAX_JSON_BYTES", len(raw_json) - 3)
    monkeypatch.setattr(parser.base64, "b64decode", lambda *args, **kwargs: pytest.fail("oversized value reached decode"))
    with pytest.raises(CardParseError, match="json_too_large"):
        parse_card(raw)


@pytest.mark.parametrize("as_png", [False, True])
def test_json_byte_limit_inclusive_and_decoded_limit_checked(monkeypatch, as_png):
    value = encoded(card())
    raw = png((b"chara", base64.b64encode(value))) if as_png else value
    monkeypatch.setattr(parser, "MAX_JSON_BYTES", len(value))
    assert parse_card(raw).document == card()
    monkeypatch.setattr(parser, "MAX_JSON_BYTES", len(value) - 1)
    with pytest.raises(CardParseError, match="json_too_large"):
        parse_card(raw)


@pytest.mark.parametrize("limit,bound", [("MAX_DEPTH", 3), ("MAX_NODES", 10)])
def test_json_complexity_limit_inclusive(monkeypatch, limit, bound):
    value = encoded(card())  # root, spec, spec_version, data and six common values.
    monkeypatch.setattr(parser, limit, bound)
    assert parse_card(value).version == 2
    monkeypatch.setattr(parser, limit, bound - 1)
    with pytest.raises(CardParseError, match="complexity"):
        parse_card(value)


@pytest.mark.parametrize("limit,bound", [("MAX_DIMENSION", 5), ("MAX_PIXELS", 15)])
def test_image_limits_are_inclusive(monkeypatch, limit, bound):
    output = io.BytesIO()
    Image.new("RGB", (5, 3)).save(output, "PNG")
    raw = output.getvalue()
    raw = raw[:-12] + chunk(b"tEXt", b"chara\0" + base64.b64encode(encoded(card()))) + raw[-12:]
    monkeypatch.setattr(parser, limit, bound)
    assert parse_card(raw).source_format == "png"
    monkeypatch.setattr(parser, limit, bound - 1)
    with pytest.raises(CardParseError, match="image_too_large"):
        parse_card(raw)


@pytest.mark.parametrize("document,error", [
    ({"spec": []}, "unsupported_version"),
    ({**card(), "spec_version": "2.1"}, "unsupported_version"),
    ({**card(), "data": []}, "data_object_required"),
    ({**card(), "data": {**card()["data"], "name": " "}}, "name_required"),
    ({**card(), "data": {**card()["data"], "personality": None}}, "common_field_type"),
])
def test_invalid_common_definition_has_safe_error(document, error):
    with pytest.raises(CardParseError, match=error):
        parse_card(encoded(document))


def test_v2_in_ccv3_rejected_without_fallback():
    value = base64.b64encode(encoded(card()))
    with pytest.raises(CardParseError, match="metadata_version_mismatch"):
        parse_card(png((b"chara", value), (b"ccv3", value)))


def test_plain_truncated_and_corrupt_png_rejected():
    with pytest.raises(CardParseError, match="metadata_missing"):
        parse_card(png())
    valid = png((b"chara", base64.b64encode(encoded(card()))))
    with pytest.raises(CardParseError):
        parse_card(valid[:-8])
    broken = bytearray(valid)
    broken[30] ^= 1
    with pytest.raises(CardParseError, match="crc"):
        parse_card(bytes(broken))


def test_file_cap_remains_distinct_from_upload_request_cap():
    valid = png((b"chara", base64.b64encode(encoded(card()))))
    exact_padding = MAX_FILE_BYTES - len(valid) - 12
    exact = valid[:-12] + chunk(b"pADd", b"x" * exact_padding) + valid[-12:]
    assert len(exact) == MAX_FILE_BYTES
    assert parse_card(exact).document == card()
    padding = MAX_FILE_BYTES + 1 - len(valid) - 12
    oversized = valid[:-12] + chunk(b"pADd", b"x" * padding) + valid[-12:]

    assert len(oversized) == MAX_FILE_BYTES + 1
    assert 4 * ((len(oversized) + 2) // 3) <= 28_000_000
    with pytest.raises(CardParseError, match="card_file_size_limit"):
        parse_card(oversized)


def test_complexity_unknown_version_and_bad_field_rejected():
    value = {}
    for _ in range(34):
        value = {"child": value}
    with pytest.raises(CardParseError, match="complexity"):
        parse_card(encoded(value))
    value = card()
    value["spec"] = "chara_card_v4"
    with pytest.raises(CardParseError, match="unsupported_version"):
        parse_card(encoded(value))
    value = card()
    value["data"]["name"] = ["bad"]
    with pytest.raises(CardParseError, match="field_type"):
        parse_card(encoded(value))


def test_mapper_preserves_source_and_requires_user_review():
    value = card(3)
    value["data"].update(nickname="하루", system_prompt="NEVER EXECUTE",
                          character_book={"entries": []}, tags=["not interests"],
                          description="<char> {{user}} {{random}}")
    parsed = parse_card(encoded(value))
    mapped = map_card(parsed)
    assert mapped.fields["worldview"] == "하루 {{user}} {{random}}"
    assert mapped.fields["speech_style"] == "하루: 안녕 대화 상대"
    assert mapped.fields["topic_preferences"] == ""
    assert "personality_required_review_description" not in mapped.review
    assert "worldview_dynamic_text_review" in mapped.review
    assert "system_prompt" in mapped.raw_only
    assert "NEVER EXECUTE" not in str(mapped.fields)
    assert parsed.document == value
