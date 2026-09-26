import base64
import io
import json
import struct
import zlib

import pytest
from PIL import Image

from app.integrations.character_cards.parser import CardParseError, parse_card
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


def test_duplicate_metadata_and_json_keys_rejected():
    value = base64.b64encode(encoded(card()))
    with pytest.raises(CardParseError, match="duplicate_metadata"):
        parse_card(png((b"chara", value), (b"CHARA", value)))
    with pytest.raises(CardParseError, match="duplicate_json_key"):
        parse_card(b'{"name":"one","name":"two"}')


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
    assert "personality_required_review_description" in mapped.review
    assert "worldview_dynamic_text_review" in mapped.review
    assert "system_prompt" in mapped.raw_only
    assert "NEVER EXECUTE" not in str(mapped.fields)
    assert parsed.document == value
