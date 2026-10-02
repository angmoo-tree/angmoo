import asyncio
import json
import pytest
from sqlalchemy import select
from app.runtime.media import binding, social_context
from app.domains.media.interpretation_contracts import parse_analysis
from app.domains.media.setting_schemas import InterpretationSettingsWrite
from app.domains.media.service.interpretation import write_interpretation_settings
from app.domains.social.models.posts import PostMedia
from app.domains.memory.policies.grouped_fts import build_groups, build_image_groups
from app.runtime.memory.grouped_fts_search import render_match
from image_integration.test_generation_lifecycle import configured, admit, OWNER, POST
from image_integration.test_providers import png


class Analyst:
    def __init__(self): self.calls = 0
    async def analyze(self, **kwargs):
        self.calls += 1
        await asyncio.sleep(.02)
        return parse_analysis({"description": "책상 위의 파란 물체", "recall_hint": "파란 물체 책상"}), {"tokens": 1}


@pytest.fixture
def scene(tmp_path):
    sessions, media, _ = configured(tmp_path)
    analyst = Analyst()
    media.interpretation.interpreter = analyst
    with sessions() as db:
        write_interpretation_settings(db, OWNER, InterpretationSettingsWrite(expected_revision=0, enabled=True, api_key="fake", daily_limit=3))
        db.commit()
    binding.register(media)
    yield sessions, media, analyst
    binding.unregister(media)


def uploaded(scene):
    sessions, media, _ = scene
    with sessions() as db:
        asset = media.assets.upload(db, owner_id=OWNER, scope_kind="world", scope_id="social-uow-world", content_type="image/png", content=png(), draft=False)
        db.add(PostMedia(post_id=POST, asset_id=asset.id, source_kind="uploaded", url=f"/api/v1/media/assets/{asset.id}/content", alt_text="upload", key_source="none", byte_size=asset.byte_size, width=asset.width, height=asset.height))
        db.commit()
        return asset.id


def test_generated_intent_in_candidate_does_not_analyze_or_rewrite_valid_selector_query(scene):
    sessions, media, analyst = scene
    identity = admit(sessions, media)
    asyncio.run(media.worker.process(identity))
    with sessions() as db:
        candidate = {"images": social_context.snapshots(db, OWNER, [POST])}
        social_context.allocate([candidate])
        assert candidate["images"][0]["source"] == "generation_intent"
        images = asyncio.run(social_context.prepare_selected(db, OWNER, candidate))
        frozen = social_context.freeze_query({"query": "reading", "origin": "selector"}, images)
        assert frozen["final_query"]["query"] == "reading" and analyst.calls == 0


def test_uploaded_candidate_is_lazy_b_and_c_share_one_analysis_then_freeze_once(scene):
    sessions, _, analyst = scene
    uploaded(scene)
    with sessions() as db:
        candidate = {"images": social_context.snapshots(db, OWNER, [POST])}
        assert candidate["images"][0]["source"] == "unrecognized" and analyst.calls == 0
    async def run():
        with sessions() as b, sessions() as c:
            return await asyncio.gather(social_context.prepare_selected(b, OWNER, candidate), social_context.prepare_selected(c, OWNER, candidate))
    b, c = asyncio.run(run())
    assert analyst.calls == 1 and b[0]["interpretation_id"] == c[0]["interpretation_id"]
    frozen = social_context.freeze_query({"query": "어제 읽었던", "origin": "selector"}, b)
    assert frozen["final_query"]["query"] == "어제 읽었던 파란 물체 책상"
    assert social_context.freeze_query({"query": "", "origin": "fallback"}, b)["final_query"]["query"] == ""
    with sessions() as db:
        shown = {"images": social_context.snapshots(db, OWNER, [POST])}
        social_context.allocate([shown])
        assert social_context.freeze_query({"query": "어제 읽었던", "origin": "selector"}, shown["images"])["image_hint"] == ""
        omitted = {"images": social_context.snapshots(db, OWNER, [POST])}
        social_context.allocate([omitted], budget=1)
        assert omitted["images"][0]["omission_reason"] == "selector_image_budget"
        images = asyncio.run(social_context.prepare_selected(db, OWNER, omitted))
        assert social_context.freeze_query({"query": "어제", "origin": "selector"}, images)["image_hint"]
        assert analyst.calls == 1


def test_mutated_pixels_fail_before_selected_use(scene):
    sessions, media, _ = scene
    identity = uploaded(scene)
    with sessions() as db:
        candidate = {"images": social_context.snapshots(db, OWNER, [POST])}
        asset = media.assets.owned(db, owner_id=OWNER, asset_id=identity)
        media.assets.path(asset).write_bytes(b"changed")
        with pytest.raises(Exception, match="content_changed"):
            asyncio.run(social_context.prepare_selected(db, OWNER, candidate))


@pytest.mark.parametrize("base_count,hint_count,expected", [(32,32,(24,8)),(5,32,(5,27)),(32,2,(30,2))])
def test_fts_group_reservations_share_unused_budget(base_count,hint_count,expected):
    base = " ".join(f"base{i}" for i in range(base_count))
    hint = " ".join(f"hint{i}" for i in range(hint_count))
    result = build_image_groups(base,hint)
    assert (sum(g.text.startswith("base") for g in result.groups), sum(g.text.startswith("hint") for g in result.groups)) == expected
    assert len(result.groups) <= 32
    assert len({t for g in result.groups for t in g.tokens}) <= 128
    assert len(render_match(result.groups).encode()) <= 8192
    assert build_image_groups(base, "").groups == build_groups(base).groups


def test_fts_deduplicates_whole_groups_and_rejects_incomplete_long_groups():
    result=build_image_groups("same same alpha", "same beta")
    assert [g.text for g in result.groups] == ["same", "alpha", "beta"]
    result=build_image_groups("x"*1001,"brief")
    assert [g.text for g in result.groups] == ["brief"] and result.truncated


def test_hint_never_overflows_or_destroys_valid_base_query():
    base={"query":"x"*1000,"origin":"selector"}
    frozen=social_context.freeze_query(base,[{"recall_hint":"visible","source":"actual_image_analysis","selector_delivered":False}])
    assert frozen["final_query"]==base and frozen["image_hint"]==""
    assert frozen["hint_omitted_reason"]=="final_query_char_budget"
