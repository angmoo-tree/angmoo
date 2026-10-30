"""Record observed input after a known pre-publication target rejection.

Never translate a database/network failure or unknown commit into a failed
public action. Successful effect receipts remain authoritative and immutable.
"""
from datetime import UTC, datetime
from sqlalchemy import select
from app.domains.memory.contracts.activity_situation import (
    CommittedActivityResult, DeliveredInputManifest, stable_digest,
)
from app.domains.memory.models.activity_situation import MemorySituationReceipt
from app.domains.memory.policies.situation_output import parse_description
from app.domains.memory.repository.situation_admission import admit

KNOWN_REJECTIONS = frozenset({
    "feed_target_stale", "activity_source_changed", "activity_target_unavailable", "feed_affordance_changed", "feed_claim_changed",
})


def record_failure(session, lane, state, reason, *, now=None):
    if reason not in KNOWN_REJECTIONS:
        return 0
    decision = state.get("decision") or {}
    if not decision.get("_situation_manifest"):
        return 0
    now = now or datetime.now(UTC)
    saved = 0
    for planned in decision.get("decisions", []):
        target, action = planned["target_id"], planned["action"]
        if action not in {"comment", "reply", "like", "post"}:
            continue
        override = decision.get("_situation_overrides", {}).get(target)
        manifest = DeliveredInputManifest.from_dict(
            override["manifest"] if override else decision["_situation_manifest"])
        if manifest.version < 3:
            continue  # Legacy hash-only input cannot prove the original text.
        activity = state["identity"]["activity_id"]
        previous = session.scalar(select(MemorySituationReceipt).where(
            MemorySituationReceipt.scope_setting_id == manifest.snapshot.setting_id,
            MemorySituationReceipt.logical_activity_id == activity,
            MemorySituationReceipt.lane == lane, MemorySituationReceipt.target_key == target))
        if previous is not None:
            continue  # Includes both completed effects and an earlier failure.
        observed = [s for s in manifest.sources if s.role == "core" and s.target_key == target]
        if not observed:
            continue
        excerpt = " / ".join(s.delivered_text for s in observed)[:400]
        description = (f'다음 내용을 읽었다: “{excerpt}”. 예정한 반응은 게시 대상의 상태가 바뀌어 실행되지 않았다.'
            if manifest.snapshot.memory_search_locale.startswith("ko") else
            f'I read this content: “{excerpt}”. The planned response was not executed because the publication target changed.')
        normalized = "reply" if action == "comment" else action
        result = CommittedActivityResult(activity, lane, target, (normalized,), (),
            stable_digest({"planned_action": normalized, "target": target}),
            stable_digest({"failed_before_publication": reason, "target": target}), now,
            counterpart_id=next((s.actor_id for s in observed if s.actor_id), None),
            experience_state="observed_action_failed", failure_reason=reason)
        admit(session, manifest=manifest,
            draft=parse_description(description, target_key=target), result=result, now=now)
        saved += 1
    return saved
