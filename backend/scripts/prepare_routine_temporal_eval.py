"""Prepare synthetic time-quality cases and a human rubric without AI requests."""
from __future__ import annotations

import argparse
import csv
import json
from datetime import UTC, date, datetime
from hashlib import sha256
from pathlib import Path
from types import SimpleNamespace
from zoneinfo import ZoneInfo

from app.domains.routine_posts.service.evidence import build_routine_prompt_context
from app.domains.routine_posts.service.temporal_context import ROUTINE_TEMPORAL_INSTRUCTIONS
from app.domains.routines.policies.planning import daypart_windows


CASES_PATH = Path(__file__).resolve().parents[1] / "tests/routine_posts/fixtures/temporal_quality_cases.json"


def _local_instant(value: str, timezone_name: str) -> datetime:
    candidate = datetime.fromisoformat(value)
    if candidate.tzinfo is None or candidate.utcoffset() is None:
        raise ValueError("evaluation_local_time_requires_offset")
    zone = ZoneInfo(timezone_name)
    local = candidate.astimezone(zone)
    if local.replace(tzinfo=None) != candidate.replace(tzinfo=None) or local.utcoffset() != candidate.utcoffset():
        raise ValueError("evaluation_local_time_zone_mismatch")
    return candidate.astimezone(UTC)


def _prompt(case: dict[str, object]) -> dict[str, object]:
    timezone_name = str(case["timezone"])
    reference = _local_instant(str(case["reference_local"]), timezone_name)
    plan_date = date.fromisoformat(str(case["plan_date"]))
    start, end = daypart_windows(plan_date, timezone_name)[str(case["daypart"])]
    previous_at = _local_instant(str(case["previous_post_local"]), timezone_name)
    world = SimpleNamespace(id="synthetic-world", name="연습 월드", tagline="시간 정합성 평가",
        setting_description="SNS 활동을 기록하는 가상의 공간", daily_life_description="매일 다양한 일과가 있다.",
        tone_tags=["일상"], timezone=timezone_name)
    character = SimpleNamespace(id="synthetic-character", name="하린", persona_summary="차분한 학생",
        speech_style="상대에게 예의를 지키며 또렷하게 쓴다.")
    context = SimpleNamespace(world=world, character=character,
        world_character=SimpleNamespace(local_profile={}),
        profile=SimpleNamespace(visible_summary="평범한 학생", core_interests=["연습"], action_profile={}),
        plan=SimpleNamespace(local_date=plan_date, timezone_name=timezone_name),
        item=SimpleNamespace(daypart=case["daypart"], activity_kind="practice",
            title=case["activity_title"], activity_seed=case["activity_seed"],
            social_mode="routine", place_key=None, scheduled_start_at=start, scheduled_end_at=end),
        episode=SimpleNamespace(effective_activity_snapshot={}),
        due_tick=SimpleNamespace(scheduled_for=start),
        state_before={"action_note": case["state_note"]},
        previous_beat=SimpleNamespace(id="synthetic-prior-beat", sequence_no=1,
            result_snapshot={"scene_kind": case["previous_scene_kind"],
                "scene_brief": case["previous_scene_brief"]} if "previous_scene_kind" in case else {}),
        previous_post=SimpleNamespace(id="synthetic-prior-post", title="앞선 장면",
            body=case["previous_post_body"], topic_signature="이전 기록", created_at=previous_at),
        source_events=())
    return build_routine_prompt_context(context, as_of_utc=reference)


def prepare(output: Path) -> dict[str, object]:
    if output.exists():
        raise ValueError("evaluation_output_exists")
    fixture_bytes = CASES_PATH.read_bytes()
    source = json.loads(fixture_bytes)
    if source["contract"] != "routine-temporal-evaluation-v1":
        raise ValueError("evaluation_contract_invalid")
    cases = source["cases"]
    identifiers = [case["id"] for case in cases]
    if len(identifiers) != 8 or len(set(identifiers)) != 8:
        raise ValueError("evaluation_case_ids_invalid")
    prepared = []
    for case in cases:
        prompt = _prompt(case)
        without_time = dict(prompt)
        without_time.pop("temporal_context")
        old_post = without_time["previous_success"]["post"]
        without_time["previous_success"] = {**without_time["previous_success"],
            "post": {k: v for k, v in old_post.items() if k not in {"created_at", "created_at_local"}}}
        prepared.append({"id": case["id"], "focus": case["focus"],
            "follow_up_of": case.get("follow_up_of"),
            "baseline_context": without_time, "candidate_context": prompt,
            "context_chars_before": len(json.dumps(without_time, ensure_ascii=False)),
            "context_chars_after": len(json.dumps(prompt, ensure_ascii=False))})
    output.mkdir(parents=True)
    manifest = {"contract": source["contract"], "baseline_commit": source["baseline_commit"],
        "fixture_sha256": sha256(fixture_bytes).hexdigest(), "case_count": len(prepared),
        "physical_request_cap": None, "model": None, "ai_requests_performed": 0,
        "scope": "synthetic_input_and_human_rubric_only",
        "limitations": ["The baseline removes the added input fields; its actual prompt must come from the baseline commit.",
            "Q-8 placeholders must be replaced with actual Q-1 output before an AI comparison.",
            "Runtime retrieval, persistence and cross-lane effects are outside this preparation."]}
    (output / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    (output / "cases.json").write_text(json.dumps(prepared, ensure_ascii=False, indent=2), encoding="utf-8")
    (output / "temporal_instructions.txt").write_text(ROUTINE_TEMPORAL_INSTRUCTIONS, encoding="utf-8")
    with (output / "rubric.csv").open("w", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(["case_id", "baseline_plan_time_valid", "baseline_draft_time_valid",
            "candidate_plan_time_valid", "candidate_draft_time_valid", "continuity_regression",
            "character_regression", "memory_regression", "physical_requests_before",
            "physical_requests_after", "input_tokens_before", "input_tokens_after", "notes"])
        for case in prepared:
            writer.writerow([case["id"], *([""] * 12)])
    return {"case_count": len(prepared), "ai_requests_performed": 0,
        "min_added_context_chars": min(c["context_chars_after"] - c["context_chars_before"] for c in prepared),
        "max_added_context_chars": max(c["context_chars_after"] - c["context_chars_before"] for c in prepared)}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    print(json.dumps(prepare(parser.parse_args().output), ensure_ascii=False))
