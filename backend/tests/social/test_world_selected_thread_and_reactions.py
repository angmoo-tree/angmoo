from datetime import UTC,datetime,timedelta

import pytest
from sqlalchemy import func,select
from sqlalchemy.orm import Session

from model_fixture_support import models
from social.test_l3_owner_manual_social_inbox import _fixture,_seed,_owner_payload,_world_post,FRONTEND_HEADERS
from app.domains.social.contracts.writes import OwnerLikeCommand
from app.runtime.social.sqlalchemy_unit_of_work import SqlAlchemySocialWriteUnitOfWork

BASE="/api/v1/worlds/world-manual/manual-social/posts/"


def setup():
    client,engine,principal=_fixture()
    _seed(engine,principal)
    assert client.post("/api/v1/worlds/world-manual/owner-character",headers=FRONTEND_HEADERS,json=_owner_payload()).status_code==201
    with Session(engine) as db:
        root=db.get(models.Post,"post-autonomous-target")
        for key,parent in [("reply-B",root.id),("reply-C","reply-B"),("sibling",root.id)]:
            db.add(_world_post(post_id=key,author_character_id=root.author_character_id,author_world_character_id=root.author_world_character_id,
                world_id=root.world_id,reply_to_post_id=parent,created_at=datetime.now(UTC)))
            db.flush()
        db.commit()
    return client,engine,principal


def test_selected_reply_is_anchor_and_nested_write_targets_immediate_author():
    client,engine,_=setup()
    reply=client.post(BASE+"reply-C/replies",headers={**FRONTEND_HEADERS,"Idempotency-Key":"nested-immediate-v2"},json={"body":"Nested reply"})
    assert reply.status_code==201,reply.text
    assert reply.json()["post"]["reply_to_post_id"]=="reply-C"
    for offset in (0,1):
        page=client.get(BASE+"reply-B",headers=FRONTEND_HEADERS,params={"offset":offset}).json()
        assert page["schema_version"]=="owner-manual-social-thread-v2"
        assert page["selected_post"]["id"]=="reply-B" and page["root_post_id"]=="post-autonomous-target"
        assert "sibling" not in [p["id"] for p in page["replies"]]
    with Session(engine) as db:
        candidate=db.scalar(select(models.OwnerManualInboxCandidate))
        evidence=db.scalar(select(models.SocialEventEvidence).where(models.SocialEventEvidence.source_post_id==reply.json()["post"]["id"]))
        assert candidate.target_post_id==evidence.target_post_id=="reply-C"
        assert evidence.root_post_id=="post-autonomous-target"
        assert candidate.target_world_character_id=="world-character-autonomous-target"


def test_like_set_unset_converges_and_each_real_transition_has_audit_only_event():
    client,engine,_=setup()
    url=BASE+"reply-C/like"
    for method,state,count in [("put","liked",1),("put","liked",1),("delete","not_liked",0),("delete","not_liked",0),("put","liked",1)]:
        response=getattr(client,method)(url,headers=FRONTEND_HEADERS)
        assert response.status_code==200,response.text
        assert response.json()["viewer_like_state"]==state and response.json()["like_count"]==count
    with Session(engine) as db:
        row=db.scalar(select(models.PostLike))
        assert (row.world_id,row.actor_world_character_id,row.target_world_character_id)==("world-manual",client.get(BASE+"reply-C",headers=FRONTEND_HEADERS).json()["owner_world_character_id"],"world-character-autonomous-target")
        events=list(db.scalars(select(models.SocialEvent)))
        assert [e.event_type for e in events]==["like_added","like_removed","like_added"]
        assert all(e.retrieval_status=="audit_only" for e in events)
        assert len({e.idempotency_key for e in events})==3
        assert db.scalar(select(func.count(models.RelationshipState.id)))==0
        assert db.scalar(select(func.count(models.GraphProjectionOutbox.id)))==0
    selected=client.get(BASE+"reply-C",headers=FRONTEND_HEADERS).json()["selected_post"]
    assert selected["viewer_like_state"]=="liked" and selected["can_owner_like"]


@pytest.mark.parametrize("stage",["after_reaction_source","after_reaction_event"])
def test_reaction_rollback_keeps_source_event_and_state_atomic(stage):
    _,engine,_=setup()
    def fail(value):
        if value==stage: raise RuntimeError("injected")
    with Session(engine) as db:
        with pytest.raises(RuntimeError):
            SqlAlchemySocialWriteUnitOfWork(db,failure_injector=fail).set_owner_like(OwnerLikeCommand("world-manual","owner-manual","reply-C",True))
        assert db.scalar(select(func.count(models.PostLike.id)))==0
        assert db.scalar(select(func.count(models.SocialEvent.id)))==0


@pytest.mark.parametrize("field,value",[("visibility","private"),("deleted_at",datetime.now(UTC)),("report_hidden_at",datetime.now(UTC)),("world_id","other")])
def test_selected_hidden_or_wrong_world_not_read_or_written(field,value):
    client,engine,_=setup()
    if field=="world_id":
        assert client.get(BASE.replace("world-manual","other")+"reply-C",headers=FRONTEND_HEADERS).status_code in {403,404}
        return
    with Session(engine) as db:
        setattr(db.get(models.Post,"reply-C"),field,value)
        db.commit()
    assert client.get(BASE+"reply-C",headers=FRONTEND_HEADERS).status_code==404
    assert client.put(BASE+"reply-C/like",headers=FRONTEND_HEADERS).status_code==404


def test_hidden_parent_is_unavailable_without_flattening_selected_subtree():
    client,engine,_=setup()
    with Session(engine) as db:
        db.get(models.Post,"reply-B").visibility="private"
        db.commit()
    response=client.get(BASE+"reply-C",headers=FRONTEND_HEADERS)
    assert response.status_code==200
    assert response.json()["parent"]=={"post_id":"reply-B","state":"unavailable"}
    assert response.json()["selected_post"]["reply_to_post_id"]=="reply-B"


def test_unambiguous_legacy_like_is_normalized_in_write_not_get():
    client,engine,_=setup()
    owner_actor=client.get(BASE+"reply-C",headers=FRONTEND_HEADERS).json()["owner_world_character_id"]
    with Session(engine) as db:
        actor=db.get(models.WorldCharacter,owner_actor)
        db.add(models.PostLike(post_id="reply-C",user_id="owner-manual",character_id=actor.character_id))
        db.commit()
    assert client.get(BASE+"reply-C",headers=FRONTEND_HEADERS).json()["selected_post"]["viewer_like_state"]=="not_liked"
    assert client.put(BASE+"reply-C/like",headers=FRONTEND_HEADERS).status_code==200
    with Session(engine) as db:
        assert db.scalar(select(models.PostLike)).actor_world_character_id==owner_actor
        assert db.scalar(select(func.count(models.SocialEvent.id)))==0


def test_subtree_pagination_counts_all_fifty_three_descendants_in_stable_order():
    client,engine,_=setup()
    at=datetime(2026,10,5,tzinfo=UTC)
    with Session(engine) as db:
        root=db.get(models.Post,"reply-B")
        for index in range(53):
            db.add(_world_post(post_id=f"page-{index:03}", author_character_id=root.author_character_id,
                author_world_character_id=root.author_world_character_id, world_id=root.world_id,
                reply_to_post_id=root.id,created_at=at))
        db.commit()
    first=client.get(BASE+"reply-B",headers=FRONTEND_HEADERS).json()
    second=client.get(BASE+"reply-B",headers=FRONTEND_HEADERS,params={"offset":first["next_offset"]}).json()
    assert first["selected_post"]["reply_count"]==54
    assert first["next_offset"]==50 and second["next_offset"] is None
    all_ids=[item["id"] for page in (first,second) for item in page["replies"]]
    assert len(all_ids)==len(set(all_ids))==54 and "sibling" not in all_ids
    assert [value for value in all_ids if value.startswith("page-")]==sorted(value for value in all_ids if value.startswith("page-"))


def test_cycle_has_no_canonical_root_and_never_authorizes_reaction_or_reply():
    client,engine,_=setup()
    with Session(engine) as db:
        db.get(models.Post,"reply-B").reply_to_post_id="reply-C"; db.commit()
    assert client.get(BASE+"reply-B",headers=FRONTEND_HEADERS).status_code==404
    assert client.put(BASE+"reply-B/like",headers=FRONTEND_HEADERS).status_code==404


def test_public_context_is_server_scoped_and_get_never_mutates_sources():
    from app.domains.social.service.owner_reaction_reads import enrich_public_reactions
    from app.domains.social.service.posts import get_post
    from app.runtime.social.manual_feed_references import RuntimeManualFeedReferences
    client,engine,_=setup()
    assert client.put(BASE+"reply-C/like",headers=FRONTEND_HEADERS).status_code==200
    with Session(engine) as db:
        for viewer,expected in [("owner-manual","liked"),(None,"unavailable"),("other-owner","unavailable")]:
            read=enrich_public_reactions(db,references=RuntimeManualFeedReferences(db),read=get_post(db,"reply-C"),current_user_id=viewer)
            assert read.viewer_like_state==expected and read.like_count==1
            assert read.can_owner_like is (expected=="liked")
        assert not db.new and not db.dirty and not db.deleted
        assert db.scalar(select(func.count(models.PostLike.id)))==1
        assert db.scalar(select(func.count(models.SocialEvent.id)))==1


def test_concurrent_like_puts_on_independent_sqlite_connections_are_one_transition(tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    from sqlalchemy import create_engine,event
    from app.database import get_db
    from app.models import Base
    client,original,principal=_fixture()
    engine=create_engine(f"sqlite:///{tmp_path / 'reactions.sqlite'}",connect_args={"check_same_thread":False,"timeout":5})
    @event.listens_for(engine,"connect")
    def pragmas(connection,_): connection.execute("PRAGMA foreign_keys=ON")
    Base.metadata.create_all(engine);_seed(engine,principal)
    def session():
        with Session(engine) as db:yield db
    client.app.dependency_overrides[get_db]=session
    assert client.post("/api/v1/worlds/world-manual/owner-character",headers=FRONTEND_HEADERS,json=_owner_payload()).status_code==201
    barrier=Barrier(2)
    def put(_):barrier.wait(timeout=10);return client.put(BASE+"post-autonomous-target/like",headers=FRONTEND_HEADERS)
    with ThreadPoolExecutor(max_workers=2) as executor:responses=list(executor.map(put,range(2)))
    assert [r.status_code for r in responses]==[200,200]
    assert all(r.json()["viewer_like_state"]=="liked" and r.json()["like_count"]==1 for r in responses)
    with Session(engine) as db:
        assert db.scalar(select(func.count(models.PostLike.id)))==1
        assert db.scalar(select(func.count(models.SocialEvent.id)))==1
        assert db.scalar(select(models.SocialEvent)).retrieval_status=="audit_only"
    engine.dispose();original.dispose()
