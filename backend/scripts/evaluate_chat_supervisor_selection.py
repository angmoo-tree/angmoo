"""Opt-in R7 synthetic initial selection only. No chat, retrieval or memory writes.

Run inside the existing contributor environment. Credentials never leave it.
Output contains aggregate usage and safe codes, not provider text/arguments.
"""
import argparse
import asyncio
from dataclasses import replace
from datetime import UTC, datetime, timedelta
import hashlib
import importlib.util
import importlib.metadata
import json
from pathlib import Path
from types import SimpleNamespace
import sys
import os
import sqlite3
from time import monotonic

from contextvars import ContextVar
from app.integrations import direct_llm
from app.domains.identity.service.credential_resolution import CredentialResolver
from app.domains.identity.contracts import CredentialPurpose
from app.domains.chat.contracts.retrieval_policy import CanonicalRetrievalScope, RetrievalEntityCandidate, RetrievalEntityResolution, RetrievalPreflightCommand
from app.domains.chat.contracts.retrieval_router_provider import RetrievalRouterContextMessage
from app.domains.chat.service.retrieval_routing import RetrievalRoutingService
from app.domains.chat.contracts.supervisor_prompts import SUPERVISOR_SYSTEM_PROMPT, CANONICAL_DESCRIPTION, GRAPH_DESCRIPTION
from app.integrations.llm.supervisor_selection import DirectLlmSupervisorSelectionProvider, selection_system_prompt, selection_tools


class SyntheticPolicy:
    def __init__(self, case): self.case = case
    def load_scope(self, c):
        return CanonicalRetrievalScope(request_id=c.request_id, owner_id=c.owner_id, world_id=c.world_id,
            thread_id=c.thread_id, requester_world_character_id=c.requester_world_character_id,
            responding_world_character_id=c.responding_world_character_id, world_timezone="Asia/Seoul",
            world_language=self.case["language"], responding_character_name="응답 캐릭터", memory_enabled=True)
    def resolve_entity_mentions(self, scope, mentions):
        return tuple(RetrievalEntityResolution(ref, tuple(RetrievalEntityCandidate(
            f"synthetic-{ref}-{i}", mention, f"synthetic-{ref}-{i}", True, False, True, True)
            for i in range(2 if self.case["resolver"] == "duplicate_minjun" else 1))) for ref, mention in mentions)


def read_material():
    from app.config import settings
    root = Path(os.environ["ANGMOO_CONTRIBUTOR_DATA_ROOT"]).resolve()
    canonical = root / "canonical"
    marker = json.loads((canonical / "current-generation.json").read_text())
    database = (canonical / marker["relative_path"] / "angmoo.sqlite3").resolve()
    if not database.is_relative_to(canonical) or not database.is_file():
        raise ValueError("evaluation_database_path_invalid")
    settings.APP_SECRET_FILE = str(root / "secrets" / "app-secret")
    settings.CREDENTIAL_ENCRYPTION_PROVIDER = "local"
    with sqlite3.connect(f"file:{database}?mode=ro",uri=True) as db:
        db.row_factory = sqlite3.Row
        owner = db.execute("SELECT owner_user_id FROM installation_identities WHERE singleton_key='local-installation'").fetchone()[0]
        pref = db.execute("SELECT default_model, default_thinking_level, credential_source, source_character_id FROM user_message_preferences WHERE user_id=?", (owner,)).fetchone()
        if pref["credential_source"] == "agent_key":
            rows = db.execute("SELECT * FROM llm_credentials WHERE owner_id=? AND purpose='agent' AND character_id=? AND enabled=1", (owner,pref["source_character_id"])).fetchall()
        else:
            rows = db.execute("SELECT * FROM llm_credentials WHERE owner_id=? AND purpose='message' AND enabled=1", (owner,)).fetchall()
        if len(rows) != 1: raise ValueError("evaluation_message_credential_unavailable")
        material = CredentialResolver.resolve_llm_credential(SimpleNamespace(**dict(rows[0])), purpose=CredentialPurpose.MESSAGE_LLM, owner_id=owner)
    return replace(material, model="gemini-3.1-flash-lite", thinking_level=pref["default_thinking_level"]), dict(pref)


def load_baseline(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


async def main(args):
    material, current_preference = read_material()
    cases = json.loads(args.inputs.read_text(encoding="utf-8"))
    assert len(cases) == 32 and sum(c["language"] == "ko" for c in cases) == 20
    assert sum(c["split"] == "development" for c in cases) == 8
    b0 = load_baseline(args.baseline, "evaluation_b0")
    b1 = load_baseline(args.baseline, "evaluation_b1")
    b1._ROUTER_SYSTEM_PROMPT = SUPERVISOR_SYSTEM_PROMPT + "\nCANONICAL: " + CANONICAL_DESCRIPTION + "\nGRAPH: " + GRAPH_DESCRIPTION + (
        "\nIn this JSON-only evaluation, represent the tool selection as the route in the response schema. "
        "CANONICAL/GRAPH/BOTH have decision RETRIEVAL; CURRENT_CONTEXT and CLARIFICATION use the matching decision. "
        "Use one coordination_hint only for BOTH. Use opaque entity refs such as entity-1 and responding_character/requester_character endpoints. "
        "For greetings use intent current_context, empty entities, null relationship/time_scope/aggregation/coordination_hint/clarification_slot. "
        "Use clarification_required with a valid clarification_slot when clarification is needed. Return JSON only."
    )
    providers = {"B0": b0.DirectLlmRetrievalRouterProvider(material), "B1": b1.DirectLlmRetrievalRouterProvider(material), "B2": DirectLlmSupervisorSelectionProvider(material)}
    args.output.mkdir(parents=True, exist_ok=True)
    destination = args.output / "results.jsonl"
    if destination.exists():
        raise ValueError("evaluation_output_already_exists")
    meta = {"started_at": datetime.now(UTC).isoformat(), "model": material.model, "thinking": material.thinking_level,
        "current_default_model":current_preference["default_model"], "current_default_thinking":current_preference["default_thinking_level"],
        "sdk": importlib.metadata.version("google-genai"), "langgraph": importlib.metadata.version("langgraph"),
        "input_sha256": hashlib.sha256(args.inputs.read_bytes()).hexdigest(), "max_initial_calls":args.max_calls,"max_repair_calls":args.max_calls,"max_physical_attempts":args.max_calls*4,
        "development_repeats":args.development_repeats or args.repeats,"heldout_repeats":args.repeats,
        "prompt_hashes": {k: hashlib.sha256(v.encode()).hexdigest() for k,v in {"B0":b0._ROUTER_SYSTEM_PROMPT,"B1":b1._ROUTER_SYSTEM_PROMPT,"B2":selection_system_prompt()}.items()},
        "tool_schema_hash": hashlib.sha256(repr(selection_tools()).encode()).hexdigest(),
        "native_adapter_sha256":hashlib.sha256(Path(sys.modules['app.providers.gemini'].__file__).read_bytes()).hexdigest(),
        "notes": "Synthetic resolver, no retrieval or production writes. No temperature/seed fixed. B0/B1 use legacy JSON transport; B2 native."}
    (args.output/"metadata.json").write_text(json.dumps(meta,indent=2),encoding="utf-8")
    budget_file=args.output/"initial-call-budget.json"
    budget_file.write_text(json.dumps({"maximum":args.max_calls}),encoding="utf-8")
    semaphore = asyncio.Semaphore(2)
    completed = [] if args.resume is None else [json.loads(line) for line in args.resume.read_text(encoding="utf-8").splitlines()]
    resumed = {(r["case"],r["variant"],r["repeat"]) for r in completed}
    known_cases={case["id"]:case for case in cases}
    if len(resumed)!=len(completed):
        raise ValueError("evaluation_duplicate_resume_cell")
    for row in completed:
        case=known_cases.get(row["case"])
        if case is None or row["variant"] not in providers or row.get("provenance",{}).get("prompt_hash")!=meta["prompt_hashes"][row["variant"]]:
            raise ValueError("evaluation_resume_provenance_mismatch")
        if any(row[key]!=case[key] for key in ("split","language","expected")):
            raise ValueError("evaluation_resume_case_mismatch")
    if completed:
        destination.write_text("".join(json.dumps(r,ensure_ascii=False)+"\n" for r in completed),encoding="utf-8")
    usage_context = ContextVar("evaluation_usage",default=None)
    original_generate = direct_llm.generate_text
    async def measured_generate(**kwargs):
        try:
            return await original_generate(**kwargs)
        finally:
            samples=usage_context.get()
            if samples is not None:
                summary=kwargs["tracker"].summary()
                samples.append({"physical":summary["call_order_in_run"] if "call_order_in_run" in summary else len(summary["calls"]),
                    "prompt_tokens":summary["total_prompt_tokens"],"output_tokens":summary["total_output_tokens"],
                    "thought_tokens":summary["total_thought_tokens"],
                    "latency_ms":sum(int(c.get("duration_ms") or 0) for c in summary["calls"])})
    direct_llm.generate_text=measured_generate
    started_calls = 0
    async def evaluate(case, variant, repeat):
        nonlocal started_calls
        if (case["id"],variant,repeat) in resumed: return
        async with semaphore:
            maximum=int(json.loads(budget_file.read_text())["maximum"])
            if not 0<=maximum<=312: raise ValueError("evaluation_budget_invalid")
            if started_calls>=maximum: return
            if args.ledger is not None:
                ledger=json.loads(args.ledger.read_text(encoding="utf-8"))
                if not 0<=ledger["started"]<ledger["maximum"]<=312:
                    raise ValueError("evaluation_global_budget_exhausted")
                ledger["started"]+=1
                args.ledger.write_text(json.dumps(ledger),encoding="utf-8")
            started_calls+=1
            start = monotonic()
            row = {"case":case["id"],"split":case["split"],"language":case["language"],"variant":variant,"repeat":repeat,"expected":case["expected"]}
            command = RetrievalPreflightCommand(request_id=f'{variant}-{case["id"]}-{repeat}',owner_id="synthetic-owner",world_id="synthetic-world",thread_id="synthetic-thread",requester_world_character_id="synthetic-requester",responding_world_character_id="synthetic-responder",user_message=case["question"])
            context = () if not case["context"] else (RetrievalRouterContextMessage("assistant",case["context"]),)
            usage=[]
            usage_token=usage_context.set(usage)
            try:
                now = datetime.now(UTC)
                class ObservedProvider:
                    async def route(self, request):
                        try: return await providers[variant].route(request)
                        except Exception as exc:
                            row.setdefault("attempt_errors",[]).append({"type":type(exc).__name__,"code":getattr(exc,"validation_code",None),"physical":getattr(exc,"physical_attempt_count",None),"shape":getattr(exc,"selection_shape",None)})
                            raise
                result = await RetrievalRoutingService(router=ObservedProvider(),policy=SyntheticPolicy(case)).route(command, recent_context=context,today_sns_context=case["today_sns"],now=now,deadline_at=now+timedelta(seconds=95))
                m = result.metrics
                row.update(status="ok",proposed=m.router_proposed_route.value,effective=result.intent.route.value,correct=result.intent.route.value==case["expected"],first_pass_valid=m.first_pass_valid,repair=m.repair_used,logical=m.router_logical_calls,physical=m.router_physical_attempts,prompt_tokens=m.prompt_token_count,output_tokens=m.output_token_count,thought_tokens=m.thought_token_count,provider_latency_ms=m.latency_ms,guard=m.sufficiency_guard_reason,tools=[c.name for c in result.proposed_tool_calls])
            except Exception as exc:
                diagnostic = getattr(exc,"router_diagnostic",None)
                row.update(status="failed",correct=False,error_type=type(exc).__name__,validation_code=getattr(diagnostic,"router_validation_code",None))
                # Diagnostic contains counts only, never serialize exception text.
                if diagnostic is not None: row["physical"] = getattr(diagnostic,"physical_attempts",None)
            usage_context.reset(usage_token)
            row["usage_attempts"] = usage
            row["elapsed_ms"] = round((monotonic()-start)*1000)
            with destination.open("a",encoding="utf-8") as output: output.write(json.dumps(row,ensure_ascii=False)+"\n")
            completed.append(row)
            print(json.dumps({"completed":len(completed),"case":row["case"],"variant":variant,"status":row["status"],"correct":row["correct"]}),flush=True)
    for split in ("development","heldout"):
        work=[]
        for repeat in range((args.development_repeats or args.repeats) if split=="development" else args.repeats):
            for index,case in enumerate(c for c in cases if c["split"]==split and (not args.case_id or c["id"]==args.case_id)):
                order=tuple(args.variants.split(","))
                rotation=(repeat+index)%len(order)
                for variant in order[rotation:]+order[:rotation]: work.append(evaluate(case,variant,repeat))
        await asyncio.gather(*work)
        failed=[r for r in completed if r["variant"]=="B2" and (r["status"]!="ok" or not r["correct"])]
        if split=="development" and failed:
            print(json.dumps({"heldout":"STOPPED","reason":"development_native_selection_failure","failures":len(failed)}),flush=True)
            break
    print(json.dumps({"finished":len(completed),"correct":sum(r["correct"] for r in completed)}),flush=True)
    return 2 if failed else 0


if __name__ == "__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inputs",type=Path,required=True)
    parser.add_argument("--baseline",type=Path,required=True)
    parser.add_argument("--output",type=Path,required=True)
    parser.add_argument("--case-id")
    parser.add_argument("--variants",default="B0,B1,B2")
    parser.add_argument("--repeats",type=int,choices=[1,2,3],default=3)
    parser.add_argument("--max-calls",type=int,default=288)
    parser.add_argument("--development-repeats",type=int,choices=[1,2,3])
    parser.add_argument("--resume",type=Path)
    parser.add_argument("--ledger",type=Path)
    options=parser.parse_args()
    try: raise SystemExit(asyncio.run(main(options)))
    except Exception as exc:
        safe = str(exc) if str(exc) in {"evaluation_message_credential_unavailable", "evaluation_baseline_model_differs", "evaluation_output_already_exists", "evaluation_database_path_invalid"} else None
        print(json.dumps({"evaluation":"blocked","error_type":type(exc).__name__,"code":safe}),flush=True)
        raise SystemExit(1)
