"""Closed Router time meanings resolve to independently specified UTC ranges."""
from dataclasses import replace
from datetime import UTC, datetime

import pytest

from app.domains.chat.contracts import parse_retrieval_intent_payload
from app.domains.chat.service.retrieval_routing import RetrievalRoutingService
from chat.test_p8_l_k_retrieval_router import _FakePolicy, _command, _payload

pytestmark = pytest.mark.usefixtures("deny_external_network")
NOW = datetime(2026, 3, 9, 5, tzinfo=UTC)


@pytest.mark.parametrize("expression,start,end", [
    *((value, "2026-03-09T04:00:00Z", "2026-03-10T04:00:00Z") for value in ("today", "오늘", "今日", "اليوم")),
    *((value, "2026-03-08T05:00:00Z", "2026-03-09T04:00:00Z") for value in ("yesterday", "어제", "昨日", "أمس")),
    *((value, "2026-03-02T05:00:00Z", "2026-03-09T04:00:00Z") for value in ("last week", "지난주", "先週", "الأسبوع الماضي")),
    *((value, "2026-02-01T05:00:00Z", "2026-03-01T05:00:00Z") for value in ("last month", "지난달", "先月", "الشهر الماضي")),
])
def test_bounded_legacy_languages_use_the_same_civil_meaning(expression, start, end):
    payload = _payload("CANONICAL", time_expression=expression)
    saved = repr(payload)
    intent = parse_retrieval_intent_payload(payload)
    scope = replace(_FakePolicy().load_scope(_command()), world_timezone="America/New_York")
    assert RetrievalRoutingService._resolve_time(intent=intent, scope=scope, now=NOW) == (start, end, "resolved")
    assert repr(payload) == saved
    assert scope.world_timezone == "America/New_York"


def test_explicit_query_region_overrides_only_this_typed_request():
    payload = _payload("CANONICAL")
    payload["time_scope"] = {"kind": "relative", "expression": None, "unit": "day", "offset": -1,
                             "period": None, "timezone": "Asia/Tokyo"}
    scope = replace(_FakePolicy().load_scope(_command()), world_timezone="America/New_York")
    intent = parse_retrieval_intent_payload(payload)
    assert RetrievalRoutingService._resolve_time(intent=intent, scope=scope, now=NOW) == (
        "2026-03-07T15:00:00Z", "2026-03-08T15:00:00Z", "resolved")
    assert scope.world_timezone == "America/New_York"
    assert intent.time_scope.payload()["timezone"] == "Asia/Tokyo"


@pytest.mark.parametrize("expression", ["sometime recently", "いつか", "언젠가", "في وقت ما", "three weeks and two days ago"])
def test_unrecognized_legacy_meaning_is_ambiguous_instead_of_all_history(expression):
    intent = parse_retrieval_intent_payload(_payload("CANONICAL", time_expression=expression))
    assert RetrievalRoutingService._resolve_time(intent=intent, scope=_FakePolicy().load_scope(_command()), now=NOW) == (
        None, None, "ambiguous")
