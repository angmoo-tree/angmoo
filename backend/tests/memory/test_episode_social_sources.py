from app.contracts.activity_thought import parse_activity_thought
from app.domains.memory.contracts.scope import MemoryScope
from app.domains.social.models.activity_thought import SocialActivityThought
from app.runtime.memory.episode_social_sources import build_episode_social_sources
from app.runtime.memory.episode_revalidation import revalidate_episode_bundle
from app.domains.memory.policies.episode_bundles import partition_episode_units
from app.runtime.social.subjective_composition import record_activity_thought
from test_p8_l_r_today_sns_activity import _seed_today_activity, today_session, NOW


def test_social_source_group_keeps_only_observed_branch_and_own_view(today_session):
    db, fixture = today_session
    execution, event = _seed_today_activity(db, fixture)
    SocialActivityThought.__table__.create(db.get_bind(), checkfirst=True)
    row = record_activity_thought(db, execution=execution, event=event, source_post_id="subject-root",
        thought=parse_activity_thought("친구들과 준비 과정을 나누고 싶다."), captured_at=NOW)
    db.flush()
    scope = MemoryScope(fixture["owner"].id, fixture["world"].id, fixture["subject"].id)
    result = build_episode_social_sources(db, scope=scope,
        identities=(("POST", "subject-root"), ("REPLY", "subject-reply"), ("REPLY", "peer-unrelated-sibling")))
    assert len(result.inputs) == 2
    assert result.rejected == ((("REPLY", "peer-unrelated-sibling"), "memory_unobserved"),)
    root = next(value.unit for value in result.inputs if value.identity == ("POST", "subject-root"))
    assert root.thought_reference == f"social:{row.id}"
    assert root.legacy_subjective_context is None
    assert root.members[0].actor_label == fixture["subject_character"].name
    assert root.members[0].occurred_at is not None
    reply = next(value.unit for value in result.inputs if value.identity == ("REPLY", "subject-reply"))
    assert reply.thought_reference is None
    assert reply.legacy_subjective_context is not None
    assert "peer-unrelated-sibling" not in {m.source_id for value in result.inputs for m in value.unit.members}
    bundle = partition_episode_units((root,), activation_epoch="test", cutoff_sequence=1)[0]
    evidence = revalidate_episode_bundle(db, bundle)
    assert ("POST", "subject-root") in evidence
