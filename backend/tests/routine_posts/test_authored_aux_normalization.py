"""OUT-T01..14: validate whole authored values before prefix normalization."""
from copy import deepcopy

import pytest

from app.contracts.name_binding import NameBindingError, NameBindingSnapshot
from app.domains.characters.policies.authored_names import authored_routine_draft
from app.runtime.autonomous_activity.generation_contracts import parse_routine_draft


def names():
    return NameBindingSnapshot("owner", "world", "actor", "Sakana", "user", "민식", 1)


def raw_draft(**changes):
    return {"title": "A scene", "body": "A complete visible post.",
            "thought": "A reason", "topic_signature": "A topic",
            "novelty_basis": "A new angle", **changes}


@pytest.mark.usefixtures("deny_external_network")
@pytest.mark.parametrize("field,limit", [("thought", 280), ("topic_signature", 300), ("novelty_basis", 500)])
@pytest.mark.parametrize("extra", [-1, 0, 1, 70])
def test_auxiliary_length_is_normalized_after_names(field, limit, extra):
    source = raw_draft(**{field: "한" * (limit + extra)})
    before = deepcopy(source)
    result = parse_routine_draft(authored_routine_draft(source, names()))
    if field == "thought":
        assert result["_thought"] == {"text": source[field][:limit], "status": "recorded", "truncated": extra > 0}
    else:
        assert result[field] == source[field][:limit]
    assert source == before


@pytest.mark.parametrize("field,limit", [("thought", 280), ("topic_signature", 300), ("novelty_basis", 500)])
def test_invalid_macro_in_discarded_tail_is_still_rejected(field, limit):
    with pytest.raises(NameBindingError, match="name_macro_unsupported"):
        authored_routine_draft(raw_draft(**{field: "x" * (limit + 20) + "{{getvar::secret}}"}), names())


@pytest.mark.parametrize("field,limit", [("title", 160), ("body", 4000)])
def test_visible_content_retains_strict_limits(field, limit):
    with pytest.raises(NameBindingError, match="name_macro_rendered_limit"):
        authored_routine_draft(raw_draft(**{field: "x" * (limit + 1)}), names())


@pytest.mark.parametrize("value", [None, "", "  ", 3, [], {}])
def test_novelty_is_required_even_after_normalization(value):
    with pytest.raises(ValueError):
        parse_routine_draft(authored_routine_draft(raw_draft(novelty_basis=value), names()))


def test_strip_before_limits_without_marking_whitespace_as_truncation():
    source = raw_draft(thought="  " + "x" * 280 + "  ", topic_signature="  " + "x" * 300 + "  ",
                       novelty_basis="  " + "x" * 500 + "  ")
    result = parse_routine_draft(authored_routine_draft(source, names()))
    assert result["_thought"]["truncated"] is False
    assert result["topic_signature"] == "x" * 300
    assert result["novelty_basis"] == "x" * 500


@pytest.mark.parametrize("unit", ["한", "日", "a", "e\u0301", "👩\u200d🚀", "🇰🇷", "🙂"])
def test_unicode_code_points_are_preserved_without_reencoding(unit):
    value = unit * 800
    result = parse_routine_draft(raw_draft(thought=value, topic_signature=value, novelty_basis=value))
    assert result["_thought"]["text"] == value[:280]
    assert result["topic_signature"] == value[:300]
    assert result["novelty_basis"] == value[:500]


def test_checkpoint_without_receipt_keeps_true_without_guessing_raw_length():
    from app.contracts.authored_output import restore_activity_thought
    thought, receipt = restore_activity_thought({"text": "x" * 280, "status": "recorded", "truncated": True})
    assert thought.truncated and receipt.truncated and receipt.inherited
    assert receipt.input_chars is receipt.rendered_chars is None


@pytest.mark.parametrize("value", [None, 8, [], {}, "x" * 350])
def test_planner_optional_thought_reaches_finalizer_and_strict_brief_stays_strict(value):
    from app.runtime.autonomous_activity.planner_contract import parse_action
    from app.runtime.autonomous_activity.name_binding import decision_names
    candidates = [{"target_id": "p", "allowed_actions": ["like"], "source_ids": ["p"], "counterpart_id": "user"}]
    raw = {"decisions": [{"target_id": "p", "action": "like", "brief": "support", "thought": value}], "state_update": None}
    result = decision_names(parse_action(raw, candidates), names(), candidates=candidates)
    assert result["decisions"][0]["_activity_thought"]["status"] == ("recorded" if isinstance(value,str) else "missing" if value is None else "invalid")
    assert result["decisions"][0]["_activity_thought"]["truncated"] is isinstance(value,str)
    raw["decisions"][0]["brief"] = "x" * 281
    with pytest.raises(ValueError): parse_action(raw,candidates)


def test_planner_tail_macro_is_checked_before_prefix_is_saved():
    from app.runtime.autonomous_activity.planner_contract import parse_action
    from app.runtime.autonomous_activity.name_binding import decision_names
    candidates=[{"target_id":"p","allowed_actions":["like"],"source_ids":["p"]}]
    parsed = parse_action({"decisions":[{"target_id":"p","action":"like","brief":"support", "thought":"x"*350+"{{getvar::secret}}"}], "state_update":None}, candidates)
    with pytest.raises(NameBindingError,match="name_macro_unsupported"):
        decision_names(parsed,names(),candidates=candidates)


@pytest.mark.parametrize("value", [None,"", "  ", 3, [], {}])
def test_optional_topic_and_thought_keep_valid_body_and_no_string_coercion(value):
    raw=raw_draft(thought=value,topic_signature=value)
    result=parse_routine_draft(authored_routine_draft(raw,names()))
    assert result["title"]==raw["title"] and result["body"]==raw["body"]
    assert result["topic_signature"]==""
    assert result["_thought"]["text"] is None
    assert result["_thought"]["status"]==("missing" if value is None or isinstance(value,str) else "invalid")


@pytest.mark.parametrize("key",["_thought","_normalization_receipt","_auxiliary_normalization","status"])
def test_untrusted_llm_cannot_supply_internal_normalization_metadata(key):
    with pytest.raises(ValueError):
        parse_routine_draft(raw_draft(**{key:{"truncated":False}}))
