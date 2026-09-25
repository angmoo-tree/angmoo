"""Opt-in, capped real-provider comparison on synthetic inputs only.

Uses the canonical lane validators and isolated in-memory Routine fixtures.
Social source/memory snapshots are frozen: this is NOT a whole-runtime quality
gate or proof of production retrieval, scheduling, projection or latency.
Run from backend with tests on PYTHONPATH; no application server is started.
"""
import argparse
import asyncio
from dataclasses import replace
from datetime import UTC, datetime
import json
from pathlib import Path
import sqlite3
from time import monotonic
from types import SimpleNamespace

from sqlalchemy.orm import Session

from app.integrations.direct_llm import RunLlmTracker, DirectLlmMaxCallsExceeded
from app.runtime.autonomous_activity.combined_lanes import CombinedInboxLane, CombinedFeedLane, CombinedRoutineLane
from app.runtime.autonomous_activity.combined_selection import CombinedSelection
from app.runtime.autonomous_activity.contracts import Candidate
from app.runtime.autonomous_activity.generation_contracts import generation_mode
from app.runtime.autonomous_activity.inbox import InboxLane
from app.runtime.autonomous_activity.feed import FeedLane
from app.runtime.autonomous_activity.routine import RoutineLane
from app.runtime.autonomous_activity.inputs import shared_input
from app.runtime.character_activity_state import initialize_from_last_success
from scripts.evaluate_personalized_activity import credential, CASES, PERSONAS
from routine_posts.test_runtime import _engine, _seed, _resident_context, _utc


class Budget:
    def __init__(self, path, cap):
        self.path, self.cap, self.used = path, cap, 0
        if path.exists():
            previous = json.loads(path.read_text())
            if previous["cap"] != cap:
                raise ValueError("evaluation_cap_changed")
            self.used = previous["reserved_physical_requests"]

    def reserve(self):
        if self.used >= self.cap:
            raise DirectLlmMaxCallsExceeded("evaluation_request_cap_reached")
        self.used += 1
        self.path.write_text(json.dumps({"cap": self.cap, "reserved_physical_requests": self.used}), encoding="utf-8")


class EvaluationTracker(RunLlmTracker):
    def __init__(self, budget):
        super().__init__(max_calls=15)
        self.budget = budget

    def next_provider_call_order(self):
        self.budget.reserve()
        return super().next_provider_call_order()


class EvaluationRecovery:
    def __init__(self):
        self.used = set()

    def reserve(self, key):
        if key in self.used or len(self.used) >= 5:
            raise ValueError("activity_recovery_exhausted")
        self.used.add(key)


def resolve_credential(root):
    canonical = root.resolve() / "canonical"
    marker = json.loads((canonical / "current-generation.json").read_text())
    path = (canonical / marker["relative_path"] / "angmoo.sqlite3").resolve()
    if not path.is_relative_to(canonical):
        raise ValueError("evaluation_database_path_invalid")
    with sqlite3.connect(path.as_uri() + "?mode=ro", uri=True) as db:
        row = db.execute("SELECT character_id FROM llm_credentials WHERE enabled=1 AND purpose='agent' "
                         "AND model='gemini-3.1-flash-lite' ORDER BY id LIMIT 1").fetchone()
    if row is None:
        raise ValueError("evaluation_model_credential_unavailable")
    return credential(root, row[0])


async def evaluate(case, index, version, cred, budget):
    case_id, text, remembered = case
    started = monotonic()
    tracker = EvaluationTracker(budget)
    output = {"case": case_id, "version": version, "stages": {}}
    async def guard(_): return {}  # No live sources: only frozen synthetic component inputs.
    async def error(exc): raise exc
    with Session(_engine(), expire_on_commit=False) as db:
        fixture = _seed(db)
        ctx = _resident_context(db, fixture, run_id=f"evaluation-{case_id}-{version}",
            now=_utc(datetime(2026, 8, 10, 10, 5)))
        ctx = replace(ctx, credential=cred)
        initialize_from_last_success(db, actor=fixture.world_character)
        db.commit()
        shared = shared_input(ctx, fixture.world_character, fixture.world)
        shared["persona"] = PERSONAS[index % len(PERSONAS)]
        classes = (CombinedInboxLane, CombinedFeedLane, CombinedRoutineLane) if version == 2 else (InboxLane, FeedLane, RoutineLane)
        options = {"ledger": EvaluationRecovery()} if version == 2 else {}
        adapters = {lane: cls(ctx, actor=fixture.world_character, tracker=tracker, hybrid_service=None, guard=guard,
            **options, **({"lane": lane} if lane != "routine" else {})) for lane, cls in zip(("inbox", "feed", "routine"), classes)}
        for adapter in adapters.values():
            # This probe has no live source identity or publication. Production
            # guards are exercised by SQLite runtime tests, not synthetic IDs.
            adapter.guard = guard
        prepared = {}
        for lane in ("inbox", "feed"):
            candidates = [Candidate(target_id=f"{lane}-{i}", counterpart_id=f"partner-{i}", source_ids=[f"{lane}-{i}"],
                text=text if i == 0 else "게시판의 점검이 끝났습니다.", allowed_actions=["comment", "like"],
                relationship={"status": "known", "summary": "서로 아는 동료"}).model_dump() for i in range(2)]
            prepared[lane] = {"identity": {"activity_id": ctx.run_id, "contract_version": version},
                "shared_context": shared, "candidates": candidates,
                "lane_data": {c["target_id"]: {"post_id": c["target_id"]} for c in candidates}}
            adapters[lane].delivery = lambda _: None
        try:
            if version == 2:
                selection = CombinedSelection(adapters, {lane: SimpleNamespace(guard=guard, on_error=error) for lane in ("inbox", "feed")})
                state = {"identity": prepared["inbox"]["identity"], "shared_context": shared, "prepared_lanes": prepared}
                state.update(await selection.mode(state))
                prepared = (await selection.select(state))["prepared_lanes"]
            else:
                for lane in ("inbox", "feed"):
                    prepared[lane].update(await adapters[lane].select(prepared[lane]))
            output["selection"] = {lane: {"selections": item.get("selections"), "error": item.get("preparation_error")} for lane, item in prepared.items()}
            order = ("inbox", "feed", "routine") if version == 2 else ("inbox", "routine", "feed")
            for lane in order:
                adapter = adapters[lane]
                state = prepared.get(lane, {"identity": {"activity_id": ctx.run_id}, "shared_context": shared})
                try:
                    if lane == "routine":
                        state.update(await adapter.load(state))
                        if not state.get("candidates"):
                            output["stages"][lane] = {"status": "skipped"}
                            continue
                        state["memories"] = {}
                        state.update(await adapter.context(state))
                    else:
                        if state.get("preparation_error"):
                            raise ValueError("selection_invalid")
                        if not state.get("selections"):
                            output["stages"][lane] = {"status": "no_selection"}
                            continue
                        state["decision_context"] = {**shared, "memories": {s["target_id"]: {"status": "ready",
                            "packets": [{"ref": "synthetic-memory", "situation": remembered, "units": []}]}
                            for s in state["selections"]}, "source_manifest": [],
                            "metric_sources": [{"source_ref": c["target_id"], "target_ref": c["counterpart_id"], "text": c["text"]}
                                for c in adapter.selected(state)]}
                    if version == 2:
                        state.update(await generation_mode(state))
                    state.update(await adapter.plan(state))
                    state.update(await adapter.validate(state))
                    if state.get("assignments"):
                        state.update(await adapter.write(state))
                    output["stages"][lane] = {"status": "valid", "decision": state["decision"],
                        "drafts": state.get("drafts", []), "failure": state.get("failure")}
                except Exception as exc:
                    output["stages"][lane] = {"status": "failed", "error_type": type(exc).__name__,
                        "validation_code": getattr(exc, "validation_code", None),
                        "decision": state.get("decision"), "assignments": state.get("assignments")}
            output["status"] = "failed" if any(s["status"] == "failed" or s.get("failure") for s in output["stages"].values()) else "valid"
        except Exception as exc:
            output.update(status="failed", error_type=type(exc).__name__)
    allowed = {"node", "lane", "status", "duration_ms", "usage", "thinking_level", "max_output_tokens", "finish_reason", "failure_class"}
    output.update(duration_ms=round((monotonic() - started) * 1000),
        calls=[{k: v for k, v in call.items() if k in allowed} for call in tracker.calls],
        physical_requests=tracker.provider_call_order_in_run)
    return output


async def run(args):
    if args.output.exists() and not args.resume:
        raise ValueError("evaluation_output_exists")
    args.output.mkdir(parents=True, exist_ok=args.resume)
    manifest = {"model": "gemini-3.1-flash-lite", "scenarios": [c[0] for c in CASES[:8]],
        "repetitions_per_version": 1, "request_cap_including_retries": 120,
        "kind": "paired_frozen_component_comparison", "operational_writes": False,
        "quality_gate": {"core_contract_regressions_allowed": 0, "clear_quality_regressions_allowed": 0,
            "require_cost_or_latency_benefit_including_recovery": True,
            "whole_runtime_quality_measured": False, "default_switch_authorized_by_this_probe": False},
        "limitations": ["Frozen social sources and memory packets; no actual hybrid retrieval or social effects.",
            "Same initial context isolates generation quality; this does not measure cross-lane effect propagation.",
            "Local regression tests separately verify canonical persistence. Component latency excludes retrieval and publication."]}
    cred = resolve_credential(args.root)
    manifest["thinking_level"] = cred.thinking_level
    if not args.resume:
        (args.output / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    budget = Budget(args.output / "budget.json", 120)
    if args.probe_case:
        from hashlib import sha256
        package = Path(__file__).resolve().parents[1] / "app/runtime/autonomous_activity"
        probe = {"phase": "required_body_probe", "cases": args.probe_case, "version": 2,
            "remaining_physical_requests": 120 - budget.used, "started_at": datetime.now(UTC).isoformat(),
            "source_hashes": {p.name: sha256(p.read_bytes()).hexdigest() for p in package.glob("*.py")}}
        (args.output / "probe-manifest.json").write_text(json.dumps(probe, indent=2), encoding="utf-8")
    completed = set()
    if args.resume and (args.output / "results.jsonl").exists():
        for line in (args.output / "results.jsonl").read_text(encoding="utf-8").splitlines():
            row = json.loads(line)
            # Only the identified fixture-scope error is eligible for replacement.
            # All ordinary model/contract failures remain evaluation outcomes.
            if not any(s.get("error_type") == "RelationshipGraphRequestError" for s in row["stages"].values()):
                completed.add((row["case"], row["version"]))
    for index, case in enumerate(CASES[:8]):
        if args.probe_case and case[0] not in args.probe_case:
            continue
        for version in ((2,) if args.probe_case else (1, 2) if index % 2 == 0 else (2, 1)):
            if not args.probe_case and (case[0], version) in completed:
                continue
            if budget.used >= budget.cap:
                return
            row = await evaluate(case, index, version, cred, budget)
            row["phase"] = "required_body_probe" if args.probe_case else "initial_comparison"
            with (args.output / "results.jsonl").open("a", encoding="utf-8") as stream:
                stream.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")
            print(json.dumps({"case": row["case"], "version": version, "status": row["status"],
                "requests": row["physical_requests"], "total": budget.used}), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--resume", action="store_true", help="Continue the same lifetime request counter; never resets the cap")
    parser.add_argument("--probe-case", action="append", choices=[c[0] for c in CASES[:8]])
    try:
        asyncio.run(run(parser.parse_args()))
    except Exception as exc:
        import traceback
        frames = [{"file": Path(f.filename).name, "line": f.lineno, "function": f.name}
                  for f in traceback.extract_tb(exc.__traceback__)]
        print(json.dumps({"status": "failed", "error_type": type(exc).__name__, "frames": frames}), flush=True)
        raise SystemExit(1) from None
