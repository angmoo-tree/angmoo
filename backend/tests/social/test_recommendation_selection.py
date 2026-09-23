from datetime import UTC, datetime, timedelta
from app.domains.social.policies.recommendation import Candidate, compose


def test_latest_quota_personalized_lanes_no_duplicates():
    now = datetime.now(UTC)
    rows = [Candidate(str(i), str(i), now-timedelta(minutes=i),
                      float(i % 2 == 0), float(i % 3 == 0),
                      frozenset({"latest", "interest" if i % 2 == 0 else "explore", "relation"} if i % 3 == 0 else {"latest", "interest" if i % 2 == 0 else "explore"})) for i in range(80)]
    selected = compose(rows, now=now, seed="actor")
    assert len(selected) == len({c.id for c, _ in selected}) == 20
    assert [c.id for c, _ in selected[:10]] == [str(i) for i in range(10)]
    assert [lane for _, lane in selected[10:]] == ["interest"]*5 + ["relation"]*3 + ["explore"]*2


def test_shortage_latest_can_exceed_ten_but_keeps_real_source():
    now = datetime.now(UTC)
    selected = compose([Candidate(str(i), str(i), now, 0, 0, frozenset({"latest"})) for i in range(30)], now=now, seed="actor")
    assert len(selected) == 20
    assert all(lane == "latest" for _, lane in selected)


def test_author_limit_does_not_remove_latest_ten():
    now = datetime.now(UTC)
    selected = compose([Candidate(str(i), "same", now, 1, 0, frozenset({"latest", "interest"})) for i in range(80)], now=now, seed="actor")
    assert len(selected) == 10
